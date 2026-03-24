"""Debate engine — orchestrates multi-model debate and judge synthesis."""

import asyncio
import sys
import time

from verd.config import get_client, DEBATER_MAX_TOKENS, TIMEOUTS, estimate_cost
from verd.context import files_to_content
from verd.models import MODELS, MODEL_PARAMS, ROLES
from verd.judge import run_judge
from verd.output import print_round
from verd.selector import select_relevant_files


# --- Model calling with retry ---

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]


async def call_model(
    model: str,
    messages: list[dict],
    max_tokens: int,
    timeout: int,
) -> tuple[str, dict]:
    """Call a model with retries and backoff. Returns (text, usage_dict)."""
    extra = MODEL_PARAMS.get(model, {})
    last_error = None

    for attempt in range(MAX_RETRIES):
        budget = max_tokens if attempt == 0 else max_tokens * 2
        try:
            response = await asyncio.wait_for(
                get_client().chat.completions.create(
                    model=model,
                    messages=messages,
                    max_completion_tokens=budget,
                    **extra,
                ),
                timeout=timeout,
            )
            text = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "reasoning_tokens": getattr(
                    response.usage.completion_tokens_details, "reasoning_tokens", 0
                ) or 0,
            }
            if text and text.strip():
                return text.strip(), usage
            last_error = ValueError(f"{model} returned empty response")
        except Exception as e:
            last_error = e

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"⚠ {model} failed (attempt {attempt+1}/{MAX_RETRIES}), retrying in {delay}s", file=sys.stderr)
            await asyncio.sleep(delay)

    raise last_error or ValueError(f"{model} failed after {MAX_RETRIES} attempts")


# --- Question detection ---

def _is_question(text: str) -> bool:
    """Detect open-ended questions vs claims.

    "Is this secure?" → claim (PASS/FAIL)
    "What's the best approach?" → question (recommendation)
    """
    text = text.strip().lower()

    yes_no_patterns = (
        "is this", "is it", "are there", "does this", "can this",
        "is the", "are the", "does the", "has this", "have the",
    )
    if any(text.startswith(p) for p in yes_no_patterns):
        return False

    if text.startswith("any "):
        return False

    if text.endswith("?"):
        return True

    question_starters = (
        "what", "which", "how", "should", "can we", "would", "could",
        "where", "when", "why", "who", "do we", "are we", "will",
    )
    return any(text.startswith(w) for w in question_starters)


# --- Prompt building ---

def _build_round0_prompt(content: str, claim: str, role_desc: str | None = None) -> str:
    role_line = f"{role_desc}\n\n" if role_desc else ""
    is_q = _is_question(claim)

    if is_q:
        preamble = (
            f"{role_line}"
            "You are participating in a structured multi-model debate with other AI reviewers. "
            "You've been given a question along with context. "
            "Analyze the context, weigh different perspectives, and give your clear recommendation.\n\n"
            "Be specific and actionable. If there are trade-offs, state them clearly and pick a side. "
            "Don't just summarize — take a position and defend it."
        )
        verdict_instruction = (
            "Deliver your verdict:\n"
            "- PASS if there's a clear best answer/approach\n"
            "- FAIL if the proposed direction is wrong and you recommend something else\n"
            "- UNCERTAIN if genuinely insufficient information to decide\n"
            "Then give your recommendation with specific reasoning."
        )
    else:
        preamble = (
            f"{role_line}"
            "You are participating in a structured multi-model debate with other AI reviewers. "
            "Your job is to rigorously evaluate whether a claim is correct, incorrect, or uncertain. "
            "You must be intellectually honest — do not hedge or give vague answers. "
            "If the claim is wrong, say so clearly and explain why. If it's right, identify the "
            "strongest possible objection.\n\n"
            "Think step by step. Consider edge cases, hidden assumptions, and common pitfalls. "
            "Ground your reasoning in specifics, not generalities."
        )
        verdict_instruction = (
            "Deliver your assessment: PASS (claim is correct), FAIL (claim is incorrect), "
            "or UNCERTAIN. Then explain your key reasoning. Be concise and specific."
        )

    context_block = f"Context:\n{content}\n\n" if content else ""
    return f"{preamble}\n\n{context_block}Question: \"{claim}\"\n\n{verdict_instruction}"


def _build_followup_prompt(
    claim: str,
    own_response: str,
    others: list[tuple[str, str, str | None]],
    own_role_desc: str | None = None,
) -> str:
    role_reminder = f"Remember your role: {own_role_desc}\n\n" if own_role_desc else ""

    parts = [
        f"{role_reminder}"
        "You are in a structured multi-model debate. "
        "You gave an initial assessment and other reviewers have now weighed in. "
        "Your goal is to converge on the truth, not to win the argument.\n\n"
        "CRITICAL: Do NOT change your position just because other reviewers disagree. "
        "Only change if they present NEW EVIDENCE or identify a SPECIFIC FLAW in your reasoning. "
        "Headcount is not evidence — 4 wrong reviewers don't outweigh 1 right one. "
        "If you have concrete evidence (especially from web search, documentation, or direct knowledge) "
        "that contradicts the majority, HOLD YOUR GROUND and explain why your evidence is stronger. "
        "Consensus without new evidence is groupthink, not truth.\n\n"
        "You already have the full content from the previous round — focus on the arguments.",
        f'\nClaim: "{claim}"',
        f"\nYour previous response:\n{own_response}",
        "\nOther reviewers said:",
    ]
    for name, resp, role in others:
        role_tag = f" ({role})" if role else ""
        parts.append(f"[{name}{role_tag}]: {resp}")
    parts.append(
        "\nCritically evaluate the other reviewers' arguments. Consider their roles — "
        "a fact_checker citing sources carries different weight than a devils_advocate pushing back. "
        "If you disagree, identify the specific flaw in their reasoning. "
        "If you agree, stress-test the consensus by stating the strongest counter-argument. "
        "If new evidence changed your mind, say exactly what and why. "
        "Conclude with your updated verdict: PASS, FAIL, or UNCERTAIN."
    )
    return "\n".join(parts)


# --- Confidence calculation ---

_ROLE_WEIGHTS = {
    "analyst": 1.0,
    "devils_advocate": 0.8,
    "logic_checker": 1.2,
    "fact_checker": 1.3,
    "pragmatist": 1.0,
}


def _calculate_confidence(result: dict, debater_roles: dict[str, str]) -> float:
    """Calculate confidence from vote distribution weighted by roles.

    Key novelty: disagreement from a fact_checker (web-grounded) lowers
    confidence more than disagreement from a devils_advocate (expected to push back).
    """
    model_votes = result.get("model_votes", {})
    judge_conf = result.get("confidence", 0.5)
    verdict = result.get("verdict", "UNCERTAIN")

    if not model_votes or verdict == "UNCERTAIN":
        return min(judge_conf, 0.5)

    agree_weight = 0.0
    total_weight = 0.0

    for model, vote in model_votes.items():
        weight = _ROLE_WEIGHTS.get(debater_roles.get(model), 1.0)
        total_weight += weight
        if vote == verdict:
            agree_weight += weight

    if total_weight == 0:
        return judge_conf

    agreement = agree_weight / total_weight
    calculated = 0.5 + (agreement - 0.5) * 0.9
    calculated = max(0.1, min(0.95, calculated))

    # 70% from vote math, 30% from judge's reasoning assessment
    blended = 0.7 * calculated + 0.3 * judge_conf
    return round(max(0.1, min(0.95, blended)), 2)


# --- Round execution ---

async def _run_round0(debaters, content, claim, debater_roles, debater_tokens, timeout):
    """Run initial round — all models in parallel with role-specific prompts."""
    def get_role_desc(model):
        role_key = debater_roles.get(model)
        return ROLES[role_key][0] if role_key and role_key in ROLES else None

    results = await asyncio.gather(
        *[call_model(
            m,
            [{"role": "user", "content": _build_round0_prompt(content, claim, get_role_desc(m))}],
            max_tokens=debater_tokens,
            timeout=timeout,
        ) for m in debaters],
        return_exceptions=True,
    )

    valid = [(m, r) for m, r in zip(debaters, results) if not isinstance(r, Exception)]
    failed = [(m, r) for m, r in zip(debaters, results) if isinstance(r, Exception)]

    for m, e in failed:
        print(f"⚠ {m} failed: {e}", file=sys.stderr)
    if len(valid) < 1:
        raise RuntimeError("No models responded. Check your API key and model availability.")

    return valid, get_role_desc


async def _run_followup_round(
    round_num, valid_models, transcript, claim, debater_roles, debater_tokens, timeout, get_role_desc,
):
    """Run a cross-examination round — models see each other's previous responses."""
    tasks = []
    for model in valid_models:
        own = next(e["response"] for e in reversed(transcript) if e["model"] == model)
        others = [
            (e["model"], e["response"], debater_roles.get(e["model"]))
            for e in transcript
            if e["round"] == round_num - 1 and e["model"] != model
        ]
        prompt = _build_followup_prompt(claim, own, others, get_role_desc(model))
        tasks.append(
            call_model(model, [{"role": "user", "content": prompt}],
                       max_tokens=debater_tokens, timeout=timeout)
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    round_valid = []
    round_entries = []
    for m, r in zip(valid_models, results):
        if isinstance(r, Exception):
            print(f"⚠ {m} failed in round {round_num}", file=sys.stderr)
        else:
            text, usage = r
            entry = {"round": round_num, "model": m, "role": debater_roles.get(m), "response": text}
            round_entries.append(entry)
            round_valid.append((m, usage))

    return round_valid, round_entries


async def _run_judge(judge_model, content, claim, transcript, timeout, debater_roles, track_usage, status, mode=None):
    """Run judge with fallback chain."""
    FALLBACK_JUDGES = ["claude-sonnet-4-6", "gpt-5.4", "gpt-4.1"]
    judge_timeout = max(timeout, 90)

    status(f"{judge_model} delivering verdict")

    judges_tried = [judge_model]
    for attempt_judge in [judge_model] + [j for j in FALLBACK_JUDGES if j != judge_model]:
        try:
            result, judge_usage = await run_judge(
                attempt_judge, content, claim, transcript, judge_timeout,
                model_roles=debater_roles, mode=mode,
            )
            track_usage(attempt_judge, judge_usage)
            if attempt_judge != judge_model:
                print(f"⚠ primary judge ({judge_model}) failed, used {attempt_judge}", file=sys.stderr)
            return result
        except Exception as e:
            print(f"⚠ judge ({attempt_judge}) failed: {e}", file=sys.stderr)
            if attempt_judge != judge_model:
                judges_tried.append(attempt_judge)
            status(f"judge {attempt_judge} failed, trying fallback...")

    return {
        "verdict": "UNCERTAIN",
        "confidence": 0.0,
        "headline": f"All judges failed ({', '.join(judges_tried)}).",
        "strengths": [],
        "issues": ["No judge could synthesize the debate."],
        "fixes": [],
        "model_votes": {},
        "consensus": "SPLIT",
        "dissent": None,
    }


# --- Main entry point ---

async def run_debate(
    content: str,
    claim: str,
    mode: str,
    timeout_override: int | None = None,
    status_display=None,
    files: list | None = None,
    verbose: bool = False,
    status_callback=None,
) -> dict:
    """Orchestrate a multi-model debate and return the verdict."""
    cfg = MODELS[mode]
    debater_configs = cfg["debaters"]
    debaters = [d["model"] for d in debater_configs]
    debater_roles = {d["model"]: d.get("role") for d in debater_configs}
    judge_model = cfg["judge"]
    num_rounds = cfg["rounds"]
    timeout = timeout_override or TIMEOUTS[mode]
    debater_tokens = DEBATER_MAX_TOKENS.get(mode, 4096)
    transcript: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    total_cost = 0.0
    start = time.time()

    def status(msg):
        if status_display:
            status_display.update(msg)
        if status_callback:
            asyncio.ensure_future(status_callback(msg))

    def track_usage(model, usage):
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)
        nonlocal total_cost
        total_cost += estimate_cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))

    # Smart context selection
    if files is not None and len(files) > 0:
        selected = await select_relevant_files(files, claim, status_callback=status)
        content = files_to_content(selected)

    # Round 0
    status(f"spawning {len(debaters)} models: {' + '.join(debaters)}")
    valid, get_role_desc = await _run_round0(debaters, content, claim, debater_roles, debater_tokens, timeout)

    for model, (response, usage) in valid:
        transcript.append({"round": 0, "model": model, "role": debater_roles.get(model), "response": response})
        track_usage(model, usage)

    valid_models = [m for m, _ in valid]

    if verbose:
        if status_display:
            status_display.pause()
        print_round(0, [e for e in transcript if e["round"] == 0])

    status(f"{len(valid)} models responded, initial positions locked in")

    # Follow-up rounds
    round_labels = ["models challenging each other", "pressure-testing arguments", "final rebuttals"]
    for round_num in range(1, num_rounds):
        label = round_labels[min(round_num - 1, len(round_labels) - 1)]
        status(f"round {round_num + 1}/{num_rounds + 1} — {label}")

        round_valid, round_entries = await _run_followup_round(
            round_num, valid_models, transcript, claim, debater_roles, debater_tokens, timeout, get_role_desc,
        )

        for entry in round_entries:
            transcript.append(entry)
        for m, usage in round_valid:
            track_usage(m, usage)

        if not round_valid:
            print(f"⚠ No models responded in round {round_num}, stopping early.", file=sys.stderr)
            break
        valid_models = [m for m, _ in round_valid]

        if verbose:
            if status_display:
                status_display.pause()
            print_round(round_num, round_entries)

    # Judge
    result = await _run_judge(judge_model, content, claim, transcript, timeout, debater_roles, track_usage, status, mode)

    # Confidence from vote math
    result["confidence"] = _calculate_confidence(result, debater_roles)

    # Metadata
    result["elapsed"] = round(time.time() - start, 1)
    result["mode"] = mode
    result["models_used"] = valid_models
    result["judge"] = judge_model
    result["transcript"] = transcript
    result["usage"] = total_usage
    result["cost"] = round(total_cost, 4)
    return result
