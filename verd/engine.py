"""Debate engine — orchestrates multi-model debate and judge synthesis."""

import asyncio
import logging
import re
import time

from verd.config import get_client, DEBATER_MAX_TOKENS, TIMEOUTS, estimate_cost
from verd.context import files_to_content
from verd.models import MODELS, MODEL_PARAMS, MODEL_CONTEXT_WINDOWS, ROLES, get_roles
from verd.judge import run_judge
from verd.output import print_round
from verd.selector import select_relevant_files

log = logging.getLogger("verd.engine")

# Display titles for SSE / UI when domain is business
_BUSINESS_ADVISOR_TITLES = {
    "strategist": "Strategist",
    "devils_advocate": "Risk Hunter",
    "assumption_checker": "Assumption Auditor",
    "fact_checker": "Market Reality",
    "pragmatist": "Execution Realist",
}


# Matches a standalone verdict token (whole string or whole line)
_VERDICT_TOKEN = re.compile(
    r"PROCEED[\s_]?WITH[\s_]?CONDITIONS|DO[\s_]?NOT[\s_]?PROCEED"
    r"|PROCEEDWITHCONDITIONS|DONOTPROCEED",
    re.IGNORECASE,
)

# Matches lines that are purely a structural label (nothing real after the colon)
_LABEL_LINE = re.compile(
    r"^[\w\s&,/()]+?:\s*$",
    re.IGNORECASE,
)

# Matches lines whose entire content is a verdict token (possibly with punctuation)
_VERDICT_ONLY_LINE = re.compile(
    r"^\s*(PROCEED[\s_]?WITH[\s_]?CONDITIONS|DO[\s_]?NOT[\s_]?PROCEED"
    r"|PROCEEDWITHCONDITIONS|DONOTPROCEED|VERDICT\s*:\s*\w[\w\s]*"
    r"|ASSESSMENT\s*:\s*(PROCEED[\w\s]*|DO[\w\s]*))"
    r"[\s\d.:,\-–—]*$",
    re.IGNORECASE,
)


def _parse_bubbles(response: str) -> tuple[list[str], str]:
    """Extract all BUBBLE: lines the LLM appended.

    Returns (list_of_bubbles, response_without_bubble_lines).
    The LLM is asked to write 3 BUBBLE lines at the end.
    """
    lines = response.rstrip().splitlines()
    bubbles: list[str] = []
    keep: list[bool] = [True] * len(lines)

    for i, line in enumerate(lines):
        m = re.match(r"^BUBBLE:\s*(.+)$", line.strip(), re.IGNORECASE)
        if m:
            phrase = m.group(1).strip().rstrip(".,;:")
            if phrase:
                bubbles.append(phrase)
            keep[i] = False

    clean_lines = [l for l, k in zip(lines, keep) if k]
    clean_response = "\n".join(clean_lines).strip()
    return bubbles, clean_response


def _clean_for_transcript(text: str, max_chars: int = 280) -> str:
    """Return a readable excerpt suitable for the transcript card.

    Strategy:
    1. Strip markdown formatting.
    2. Remove verdict tokens and structural labels anywhere they appear.
    3. Split into sentences, skip junk sentences, return the first real ones.
    """
    t = text

    # --- Strip markdown ---
    t = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", t)
    t = re.sub(r"(?<![A-Z_])_{1,3}([^_]+)_{1,3}(?![A-Z_])", r"\1", t)
    t = re.sub(r"`[^`]+`", "", t)
    t = re.sub(r"^>\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"#{1,6}\s*", "", t)
    t = re.sub(r"[-=]{3,}", " ", t)
    t = re.sub(r"^[\s]*[-*+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^[\s]*\d+\.\s+", "", t, flags=re.MULTILINE)

    # --- Remove verdict tokens inline (e.g. "VERDICT: PROCEEDWITHCONDITIONS") ---
    t = re.sub(
        r"(VERDICT|ASSESSMENT)\s*:\s*(PROCEED[\s\w]*|DO[\s\w]*NOT[\s\w]*|PASS|FAIL|UNCERTAIN)\b",
        "", t, flags=re.IGNORECASE,
    )
    # Remove bare verdict tokens that appear at start of a segment
    t = re.sub(
        r"(?<![A-Za-z])(PROCEED[\s_]?WITH[\s_]?CONDITIONS|DO[\s_]?NOT[\s_]?PROCEED"
        r"|PROCEEDWITHCONDITIONS|DONOTPROCEED)(?![A-Za-z])",
        "", t, flags=re.IGNORECASE,
    )

    # --- Remove title/header preamble lines ---
    # e.g. "Business Strategy Analysis: Kenyan Cold-Brew ... — UAE Market"
    # These are lines that are ALL caps-words / title-cased with colons and dashes, no verb
    lines_raw = t.splitlines()
    content_lines: list[str] = []
    for raw in lines_raw:
        line = raw.strip()
        if not line:
            continue
        # Skip lines that are purely a verdict token after cleanup
        if _VERDICT_ONLY_LINE.match(line):
            continue
        # Skip lines that are purely a label (e.g. "Fatal flaw:", "Assessment:")
        if _LABEL_LINE.match(line) and len(line) < 60:
            continue
        # Skip lines that look like document titles/headers:
        # heuristic — no sentence-ending punctuation, mostly title-case, has "—" or ":" + long noun phrase
        if (
            len(line) < 120
            and not re.search(r"[.?!]", line)
            and re.search(r"[:\-–—]", line)
            and re.match(r"^[A-Z]", line)
            and not re.search(r"\b(we|our|you|your|this|the deal|minimum|units|month|risk|unless)\b", line, re.IGNORECASE)
        ):
            continue
        # Strip any residual leading label "Xxx Xxx:" at the very start of a kept line
        line = re.sub(r"^[A-Z][a-zA-Z\s&/()]{2,30}:\s+", "", line).strip()
        # Clean up extra spaces left by removals
        line = re.sub(r"\s{2,}", " ", line).strip()
        if len(line) < 10:
            continue
        content_lines.append(line)

    combined = " ".join(content_lines)
    combined = re.sub(r"\s+", " ", combined).strip()

    # Cut to max_chars on a sentence boundary
    if len(combined) <= max_chars:
        return combined
    cut = combined[:max_chars]
    for sep in (". ", "? ", "! "):
        idx = cut.rfind(sep)
        if idx > 60:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


def _advisor_stream_payload(role: str | None, model: str, round_num: int, response: str, domain: str) -> dict:
    if domain == "business":
        title = _BUSINESS_ADVISOR_TITLES.get(role or "", role or model.split("/")[-1])
    else:
        title = role or model.split("/")[-1]

    bubbles, clean_response = _parse_bubbles(response)

    return {
        "type": "advisor",
        "role": role,
        "title": title,
        "model": model,
        "round": round_num,
        "text": _clean_for_transcript(clean_response),
        "quips": bubbles,  # list of 1-3 phrases
    }


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
            # Surface model-not-found errors immediately instead of retrying
            err_str = str(e).lower()
            if any(s in err_str for s in ("not found", "does not exist", "invalid model", "no endpoints")):
                raise ValueError(
                    f"Model '{model}' not found. Check that your OPENAI_BASE_URL provider "
                    f"supports this model, or customize models in verd/models.py. "
                    f"Original error: {e}"
                ) from e
            last_error = e

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            log.warning("%s failed (attempt %d/%d), retrying in %ds", model, attempt + 1, MAX_RETRIES, delay)
            await asyncio.sleep(delay)

    raise last_error or ValueError(f"{model} failed after {MAX_RETRIES} attempts")


# --- Response validation ---

_MIN_RESPONSE_LENGTH = 20
_MAX_RESPONSE_LENGTH = 50_000


def _validate_response(model: str, text: str) -> str | None:
    """Validate a debater response. Returns cleaned text or None if unusable."""
    if not text or len(text.strip()) < _MIN_RESPONSE_LENGTH:
        log.warning("%s returned too-short response (%d chars), dropping", model, len(text or ""))
        return None
    text = text.strip()
    if len(text) > _MAX_RESPONSE_LENGTH:
        log.warning("%s response truncated from %d to %d chars", model, len(text), _MAX_RESPONSE_LENGTH)
        text = text[:_MAX_RESPONSE_LENGTH] + "\n[response truncated]"
    return text


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

def _build_round0_prompt(
    content: str, claim: str, role_desc: str | None = None, domain: str = "technical",
) -> str:
    role_line = f"{role_desc}\n\n" if role_desc else ""
    is_q = _is_question(claim)

    if domain == "business":
        preamble = (
            f"{role_line}"
            "You are an expert advisor in a structured multi-advisor panel evaluating a business decision. "
            "Other advisors with different specializations are also evaluating this decision independently. "
            "You will debate across multiple rounds before a final verdict is delivered.\n\n"
            "Be specific and quantitative. Every claim must include a number, a named entity, a timeframe, "
            "or a concrete action. Never say 'the market is competitive' — say how many competitors, "
            "their pricing, their market share. Never say 'there are risks' — name the exact risk, "
            "its probability, and its dollar impact.\n\n"
            "IMPORTANT FORMAT RULES:\n"
            "- Do NOT start with a title, header, or document name.\n"
            "- Do NOT start with a verdict token (PROCEED, DO NOT PROCEED, etc.).\n"
            "- Start directly with your most important substantive point as a plain sentence.\n"
            "- Write in plain prose paragraphs. Do not use numbered lists or section headers."
        )
        verdict_instruction = (
            "End your response by stating your verdict on one line:\n"
            "Verdict: PROCEED or Verdict: PROCEED_WITH_CONDITIONS or Verdict: DO_NOT_PROCEED\n"
            "Then one sentence explaining the single biggest reason."
        )
    elif is_q:
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

    bubble_instruction = (
        "\n\nFinally, at the very end of your response on separate lines, write exactly 3 BUBBLE lines — "
        "your 3 sharpest distinct points, each 8 words or fewer, plain English, no verdict tokens, no markdown:\n"
        "BUBBLE: <point 1>\n"
        "BUBBLE: <point 2>\n"
        "BUBBLE: <point 3>"
    )
    context_block = f"Context:\n{content}\n\n" if content else ""
    return f"{preamble}\n\n{context_block}Question: \"{claim}\"\n\n{verdict_instruction}{bubble_instruction}"


def _build_followup_prompt(
    claim: str,
    own_response: str,
    others: list[tuple[str, str, str | None]],
    own_role_desc: str | None = None,
    domain: str = "technical",
) -> str:
    role_reminder = f"Remember your role: {own_role_desc}\n\n" if own_role_desc else ""

    if domain == "business":
        anti_groupthink = (
            "CRITICAL: Do NOT change your position just because other advisors disagree. "
            "Only change if they present NEW MARKET DATA or identify a SPECIFIC FLAW in your analysis. "
            "Headcount is not due diligence — 4 optimistic advisors don't outweigh 1 advisor with real data. "
            "A skeptical investor's critique backed by numbers carries more weight than polite agreement. "
            "If you have concrete evidence that contradicts the majority, HOLD YOUR GROUND.\n\n"
        )
        conclude = (
            "\nCritically evaluate the other advisors' arguments. Consider their specializations — "
            "a fact_checker citing market data carries different weight than a devils_advocate pushing back. "
            "If you disagree, identify the specific flaw in their reasoning with numbers. "
            "If you agree, stress-test the consensus — what would make this wrong? "
            "If new evidence changed your mind, say exactly what and why.\n"
            "Write in plain prose. Do NOT start with a title, header, or verdict token. "
            "Start directly with your strongest substantive point as a sentence.\n"
            "End with: Verdict: PROCEED or Verdict: PROCEED_WITH_CONDITIONS or Verdict: DO_NOT_PROCEED"
        )
    else:
        anti_groupthink = (
            "CRITICAL: Do NOT change your position just because other reviewers disagree. "
            "Only change if they present NEW EVIDENCE or identify a SPECIFIC FLAW in your reasoning. "
            "Headcount is not evidence — 4 wrong reviewers don't outweigh 1 right one. "
            "If you have concrete evidence (especially from web search, documentation, or direct knowledge) "
            "that contradicts the majority, HOLD YOUR GROUND and explain why your evidence is stronger. "
            "Consensus without new evidence is groupthink, not truth.\n\n"
        )
        conclude = (
            "\nCritically evaluate the other reviewers' arguments. Consider their roles — "
            "a fact_checker citing sources carries different weight than a devils_advocate pushing back. "
            "If you disagree, identify the specific flaw in their reasoning. "
            "If you agree, stress-test the consensus by stating the strongest counter-argument. "
            "If new evidence changed your mind, say exactly what and why. "
            "Conclude with your updated verdict: PASS, FAIL, or UNCERTAIN."
        )

    bubble_instruction = (
        "\n\nFinally, at the very end of your response on separate lines, write exactly 3 BUBBLE lines — "
        "your 3 sharpest distinct rebuttals or insights, each 8 words or fewer, plain English, no verdict tokens:\n"
        "BUBBLE: <point 1>\n"
        "BUBBLE: <point 2>\n"
        "BUBBLE: <point 3>"
    )
    parts = [
        f"{role_reminder}"
        "You are in a structured multi-advisor debate. "
        "You gave an initial assessment and other advisors have now weighed in. "
        "Your goal is to converge on the truth, not to win the argument.\n\n"
        f"{anti_groupthink}"
        "IMPORTANT: Refer to other advisors by their role title only (e.g. 'the Risk Hunter', 'the Strategist'). "
        "Never mention model names like 'claude', 'gemini', 'gpt', 'deepseek', or 'sonar'.\n\n"
        "You already have the full content from the previous round — focus on the arguments.",
        f'\nDecision: "{claim}"',
        f"\nYour previous response:\n{own_response}",
        "\nOther advisors said:",
    ]
    for name, resp, role in others:
        parts.append(f"[{name}]: {resp}")
    parts.append(conclude + bubble_instruction)
    return "\n".join(parts)


# --- Confidence calculation ---

_ROLE_WEIGHTS = {
    "analyst": 1.0,
    "devils_advocate": 0.8,
    "logic_checker": 1.2,
    "fact_checker": 1.3,
    "pragmatist": 1.0,
    "strategist": 1.1,
    "assumption_checker": 1.2,
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

def _cap_content_for_model(content: str, model: str, max_output_tokens: int) -> str:
    """Truncate content to fit within a model's context window.

    Reserves space for prompt overhead (~2K tokens) and output tokens.
    """
    ctx_window = MODEL_CONTEXT_WINDOWS.get(model, 200_000)
    # Reasoning models (deepseek-r1, o3, etc.) use context for chain-of-thought
    reasoning_models = {"deepseek-r1", "o3", "o4-mini"}
    reasoning_reserve = 30_000 if model in reasoning_models else 0
    # Reserve tokens for: prompt template (~2K) + output + reasoning overhead
    usable_tokens = ctx_window - max_output_tokens - 4_000 - reasoning_reserve
    # Rough chars-per-token estimate (conservative: 3 chars/token)
    max_chars = max(usable_tokens * 3, 10_000)
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + f"\n[... content truncated to fit {model} context window]"


async def _run_round0(debaters, content, claim, debater_roles, debater_tokens, timeout, domain="technical"):
    """Run initial round — all models in parallel with role-specific prompts."""
    roles_dict = get_roles(domain)

    def get_role_desc(model):
        role_key = debater_roles.get(model)
        return roles_dict[role_key][0] if role_key and role_key in roles_dict else None

    results = await asyncio.gather(
        *[call_model(
            m,
            [{"role": "user", "content": _build_round0_prompt(
                _cap_content_for_model(content, m, debater_tokens), claim, get_role_desc(m),
                domain=domain,
            )}],
            max_tokens=debater_tokens,
            timeout=timeout,
        ) for m in debaters],
        return_exceptions=True,
    )

    valid = []
    for m, r in zip(debaters, results):
        if isinstance(r, Exception):
            log.warning("%s failed: %s", m, r)
        else:
            text, usage = r
            cleaned = _validate_response(m, text)
            if cleaned is not None:
                valid.append((m, (cleaned, usage)))
            else:
                log.warning("%s returned unusable response, dropping", m)

    if len(valid) < 1:
        raise RuntimeError("No models responded. Check your API key and model availability.")

    return valid, get_role_desc


async def _run_followup_round(
    round_num, valid_models, transcript, claim, debater_roles, debater_tokens, timeout, get_role_desc,
    domain="technical",
):
    """Run a cross-examination round — models see each other's previous responses."""
    tasks = []
    for model in valid_models:
        own = next(e["response"] for e in reversed(transcript) if e["model"] == model)
        others = [
            (
                _BUSINESS_ADVISOR_TITLES.get(debater_roles.get(e["model"], ""), debater_roles.get(e["model"], e["model"]))
                if domain == "business"
                else debater_roles.get(e["model"], e["model"]),
                e["response"],
                debater_roles.get(e["model"]),
            )
            for e in transcript
            if e["round"] == round_num - 1 and e["model"] != model
        ]
        prompt = _build_followup_prompt(claim, own, others, get_role_desc(model), domain=domain)
        tasks.append(
            call_model(model, [{"role": "user", "content": prompt}],
                       max_tokens=debater_tokens, timeout=timeout)
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    round_valid = []
    round_entries = []
    for m, r in zip(valid_models, results):
        if isinstance(r, Exception):
            log.warning("%s failed in round %d: %s", m, round_num, r)
        else:
            text, usage = r
            cleaned = _validate_response(m, text)
            if cleaned is not None:
                entry = {"round": round_num, "model": m, "role": debater_roles.get(m), "response": cleaned}
                round_entries.append(entry)
                round_valid.append((m, usage))
            else:
                log.warning("%s returned unusable response in round %d, dropping", m, round_num)

    return round_valid, round_entries


async def _run_judge(
    judge_model, content, claim, transcript, timeout, debater_roles, track_usage, status,
    domain="technical", model_titles=None,
):
    """Run judge with retry on primary, then fallback chain."""
    FALLBACK_JUDGES = ["o4-mini", "claude-sonnet-4-6", "gpt-4.1"]
    judge_timeout = max(timeout, 90)

    status(f"{judge_model} delivering verdict")

    # Try primary judge twice before falling back
    judges_tried = [judge_model]
    judge_sequence = [judge_model, judge_model] + [j for j in FALLBACK_JUDGES if j != judge_model]
    for i, attempt_judge in enumerate(judge_sequence):
        try:
            result, judge_usage = await run_judge(
                attempt_judge, content, claim, transcript, judge_timeout,
                model_roles=debater_roles, domain=domain, model_titles=model_titles,
            )
            track_usage(attempt_judge, judge_usage)
            if attempt_judge != judge_model:
                log.warning("primary judge (%s) failed, used %s", judge_model, attempt_judge)
            elif i == 1:
                log.info("primary judge (%s) succeeded on retry", judge_model)
            return result
        except Exception as e:
            log.warning("judge (%s) failed: %s", attempt_judge, e)
            if attempt_judge != judge_model:
                judges_tried.append(attempt_judge)
            if i == 0:
                status(f"judge {attempt_judge} failed, retrying...")
            else:
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
    stream_callback=None,
) -> dict:
    """Orchestrate a multi-model debate and return the verdict.

    stream_callback: optional async callable receiving JSON-serializable dicts
    for rich UI (narration, per-advisor excerpts). When set, status lines are
    sent as {"type": "status", "message": "..."} instead of using status_callback.
    """
    cfg = MODELS[mode]
    domain = cfg.get("domain", "technical")
    debater_configs = cfg["debaters"]
    debaters = [d["model"] for d in debater_configs]
    debater_roles = {d["model"]: d.get("role") for d in debater_configs}
    judge_model = cfg["judge"]
    num_rounds = cfg["rounds"]
    timeout = timeout_override or TIMEOUTS.get(mode, TIMEOUTS.get("verdh", 120))
    debater_tokens = DEBATER_MAX_TOKENS.get(mode, DEBATER_MAX_TOKENS.get("verdh", 8192))
    transcript: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
    total_cost = 0.0
    start = time.time()

    def status(msg):
        if status_display:
            status_display.update(msg)
        if stream_callback:
            asyncio.ensure_future(stream_callback({"type": "status", "message": msg}))
        elif status_callback:
            asyncio.ensure_future(status_callback(msg))

    def emit_stream(payload: dict):
        if stream_callback:
            asyncio.ensure_future(stream_callback(payload))

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
    advisor_label = "advisors" if domain == "business" else "models"
    if stream_callback:
        if domain == "business":
            emit_stream(
                {
                    "type": "narration",
                    "text": "The council is reading your brief. Each advisor forms an independent opening position — no one sees the others’ answers yet.",
                }
            )
        else:
            emit_stream(
                {
                    "type": "narration",
                    "text": "Reviewers are analyzing the question in parallel before cross-examination.",
                }
            )
    status(f"spawning {len(debaters)} {advisor_label}: {' + '.join(debaters)}")
    valid, get_role_desc = await _run_round0(
        debaters, content, claim, debater_roles, debater_tokens, timeout, domain=domain,
    )

    for model, (response, usage) in valid:
        transcript.append({"round": 0, "model": model, "role": debater_roles.get(model), "response": response})
        track_usage(model, usage)
        emit_stream(_advisor_stream_payload(debater_roles.get(model), model, 0, response, domain))

    valid_models = [m for m, _ in valid]

    if verbose:
        if status_display:
            status_display.pause()
        print_round(0, [e for e in transcript if e["round"] == 0])

    status(f"{len(valid)} {advisor_label} responded, initial positions locked in")
    if stream_callback and domain == "business":
        emit_stream(
            {
                "type": "narration",
                "text": "Opening statements are on the record. The next rounds are adversarial — advisors read each other’s arguments and respond.",
            }
        )

    # Follow-up rounds
    round_labels = (
        ["advisors challenging each other", "pressure-testing assumptions", "final positions"]
        if domain == "business"
        else ["models challenging each other", "pressure-testing arguments", "final rebuttals"]
    )
    for round_num in range(1, num_rounds):
        label = round_labels[min(round_num - 1, len(round_labels) - 1)]
        if stream_callback:
            emit_stream(
                {
                    "type": "narration",
                    "text": f"Round {round_num + 1} of {num_rounds}: {label.replace('—', ' — ')}.",
                }
            )
        status(f"round {round_num + 1}/{num_rounds} — {label}")

        round_valid, round_entries = await _run_followup_round(
            round_num, valid_models, transcript, claim, debater_roles, debater_tokens, timeout, get_role_desc,
            domain=domain,
        )

        for entry in round_entries:
            transcript.append(entry)
            emit_stream(
                _advisor_stream_payload(
                    entry.get("role"), entry["model"], round_num, entry["response"], domain
                )
            )
        for m, usage in round_valid:
            track_usage(m, usage)

        if not round_valid:
            log.warning("No models responded in round %d, stopping early.", round_num)
            break
        valid_models = [m for m, _ in round_valid]

        if verbose:
            if status_display:
                status_display.pause()
            print_round(round_num, round_entries)

    # Judge
    if stream_callback:
        emit_stream(
            {
                "type": "narration",
                "text": "Live debate closed. The chair is synthesizing a verdict from the full transcript.",
            }
        )
    # Build model_titles before judge so judge can use them in transcript/prompts
    model_titles: dict[str, str] | None = None
    if domain == "business":
        model_titles = {
            m: _BUSINESS_ADVISOR_TITLES.get(debater_roles.get(m, ""), m)
            for m in debater_roles
        }

    result = await _run_judge(
        judge_model, content, claim, transcript, timeout, debater_roles, track_usage, status,
        domain=domain, model_titles=model_titles,
    )

    # Confidence from vote math
    result["confidence"] = _calculate_confidence(result, debater_roles)

    # Metadata
    result["elapsed"] = round(time.time() - start, 1)
    result["mode"] = mode
    result["domain"] = domain
    result["models_used"] = valid_models
    result["judge"] = judge_model
    result["transcript"] = transcript
    result["usage"] = total_usage
    result["cost"] = round(total_cost, 4)
    # Expose model_titles for UI display
    if model_titles:
        result["model_titles"] = model_titles
    else:
        result["model_titles"] = {m: role for m, role in debater_roles.items()}
    return result
