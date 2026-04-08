import asyncio
import json
import re

from verd.config import get_client, JUDGE_MAX_TOKENS, JSON_MODE_MODELS
from verd.models import MODEL_PARAMS


def _serialize_transcript(transcript: list[dict], model_roles: dict[str, str] | None = None,
                          model_titles: dict[str, str] | None = None) -> str:
    rounds: dict[int, list[tuple[str, str]]] = {}
    for entry in transcript:
        r = entry["round"]
        rounds.setdefault(r, []).append((entry["model"], entry["response"]))

    parts = []
    for r in sorted(rounds):
        parts.append(f"--- Round {r} ---")
        for model, response in rounds[r]:
            # Use human title if available, else role, else model name
            label = (model_titles or {}).get(model) or (model_roles or {}).get(model) or model
            parts.append(f"[{label}]: {response}")
        parts.append("")
    return "\n".join(parts).strip()


def _build_role_context(model_roles: dict[str, str] | None, domain: str = "technical",
                        model_titles: dict[str, str] | None = None) -> str:
    """Build a description of reviewer roles for the judge."""
    if not model_roles:
        return ""
    from verd.models import get_roles
    roles_dict = get_roles(domain)
    label = "Advisor" if domain == "business" else "Reviewer"
    lines = [f"{label} roles and their specializations:"]
    for model, role_key in model_roles.items():
        if role_key in roles_dict:
            _, weight_hint = roles_dict[role_key]
            display = (model_titles or {}).get(model) or role_key
            lines.append(f"- {display}: specializes in {weight_hint}")
    if domain == "business":
        lines.append(
            "\nWeight each advisor's input according to their specialization — "
            "e.g. trust the fact_checker on market data, the assumption_checker on financial projections, "
            "the devils_advocate on risk identification, and the pragmatist on execution feasibility."
        )
    else:
        lines.append(
            "\nWeight each reviewer's input according to their role — "
            "e.g. trust the fact_checker on factual claims, the logic_checker on reasoning, "
            "the devils_advocate on edge cases, and the pragmatist on operational concerns."
        )
    return "\n".join(lines)


MAX_JUDGE_CONTENT_CHARS = 60_000  # ~15K tokens — leave room for transcript + output


def _build_judge_prompt(content: str, claim: str, transcript: list[dict],
                        model_roles: dict[str, str] | None = None,
                        domain: str = "technical",
                        model_titles: dict[str, str] | None = None) -> str:
    from verd.engine import _is_question
    is_q = _is_question(claim)
    serialized = _serialize_transcript(transcript, model_roles, model_titles=model_titles)
    role_context = _build_role_context(model_roles, domain=domain, model_titles=model_titles)

    if domain == "business":
        intro = (
            "You are the final arbiter in a structured multi-advisor panel evaluating a business decision. "
            "Multiple independent expert advisors — strategists, risk analysts, market researchers, and "
            "execution specialists — have debated this decision across several rounds.\n\n"
            "Your role is to synthesize their analysis, weigh the quality of evidence and reasoning, "
            "and deliver a clear, actionable verdict that a business owner can act on immediately.\n\n"
            "QUALITY RULES — every sentence in your output must contain at least one of:\n"
            "- A specific number (revenue, cost, probability, timeframe)\n"
            "- A named entity (competitor, location, market segment)\n"
            "- A concrete action (what to do, when, how)\n"
            "If a sentence contains none of these, delete it. No filler.\n\n"
        )
        eval_criteria = (
            "Evaluation criteria:\n"
            "- Weight arguments by their specificity and market evidence, not by advisor headcount\n"
            "- A single advisor with real market data outweighs four advisors with opinions\n"
            "- If an advisor cites competitor pricing, customer data, or industry benchmarks, weight that heavily\n"
            "- Be suspicious of advisors who changed position without new data — that is groupthink\n"
            "- An advisor who held their ground with evidence against majority pressure deserves extra weight\n"
            "- Identify if any advisor spotted a risk or opportunity others missed\n"
            "- Flag unresolved genuine disagreements vs. superficial differences in framing"
        )
        json_schema = (
            '\nRespond with valid JSON only. No markdown, no code fences, no preamble:\n'
            '{\n'
            '  "verdict": "PROCEED" | "PROCEED_WITH_CONDITIONS" | "DO_NOT_PROCEED",\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "headline": "<2-sentence verdict — the key finding and recommended action>",\n'
            '  "opportunities": ["<opportunity 1 with specific number or entity>", ...],\n'
            '  "risks": ["<risk 1 with probability and impact>", ...],\n'
            '  "conditions": ["<what must be true for this to work>", ...],\n'
            '  "what_if_suggestions": ["<variable change that could improve outcome>", ...],\n'
            '  "model_votes": {"<advisor_role_title>": "PROCEED" | "PROCEED_WITH_CONDITIONS" | "DO_NOT_PROCEED"},\n'
            '  "consensus": "FULL" | "MAJORITY" | "SPLIT",\n'
            '  "dissent": "<which advisor role dissented, what they argued, and why it matters — or null. Use role titles like Strategist, Risk Hunter, etc., never model names>",\n'
            '  "unique_catches": ["<advisor role title e.g. Risk Hunter> identified <what> that others missed", ...]\n'
            '}\n\n'
            'Rules for the arrays:\n'
            '- opportunities: genuine strengths and market advantages — be specific with numbers\n'
            '- risks: specific threats with probability estimates and financial impact\n'
            '- conditions: prerequisites that must be met before proceeding — the "only if" list\n'
            '- what_if_suggestions: variables the user could change to improve the outcome\n'
            '- Keep each item to one clear sentence with a specific number or action\n'
            '- Empty arrays [] are fine if nothing applies\n'
            '- unique_catches: what did each advisor uniquely spot that others missed? '
            'This is the most valuable part — highlight it.'
        )
    elif is_q:
        intro = (
            "You are the final judge in a structured multi-model AI debate about a question. "
            "Multiple independent experts have analyzed the question and context across several rounds. "
            "Your role is to synthesize their recommendations, weigh the quality of evidence and reasoning, "
            "and deliver a clear, actionable answer.\n\n"
            "For the verdict field:\n"
            "- PASS = there is a clear recommended answer/approach\n"
            "- FAIL = the most discussed approach is wrong, recommend an alternative\n"
            "- UNCERTAIN = genuinely insufficient information to decide\n\n"
        )
        eval_criteria = (
            "Evaluation criteria:\n"
            "- Weight arguments by their specificity and evidence, not by how many models agree\n"
            "- A single well-reasoned dissent with concrete evidence outweighs vague consensus\n"
            "- If a reviewer cites web sources, documentation, or verifiable facts, weight that ABOVE pure reasoning\n"
            "- Be suspicious of reviewers who changed position without new evidence — that is groupthink, not insight\n"
            "- A reviewer who held their ground with evidence against majority pressure deserves extra weight\n"
            "- Note which reviewers changed their position and whether the reason was compelling\n"
            "- Identify if any reviewer spotted something others missed\n"
            "- Flag unresolved genuine disagreements vs. superficial differences in phrasing"
        )
        json_schema = (
            '\nRespond with valid JSON only. No markdown, no code fences, no preamble:\n'
            '{\n'
            '  "verdict": "PASS" | "FAIL" | "UNCERTAIN",\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "headline": "<short verdict headline — the key recommendation or finding>",\n'
            '  "strengths": ["<point 1>", "<point 2>", ...],\n'
            '  "issues": ["<issue 1>", "<issue 2>", ...],\n'
            '  "fixes": ["<recommendation 1>", "<recommendation 2>", ...],\n'
            '  "model_votes": {"<model_name>": "PASS" | "FAIL" | "UNCERTAIN"},\n'
            '  "consensus": "FULL" | "MAJORITY" | "SPLIT",\n'
            '  "dissent": "<which model dissented, what they argued, and why it matters — or null>",\n'
            '  "unique_catches": ["<model_name> caught <what> that others missed", ...]\n'
            '}\n\n'
            'Rules for the arrays:\n'
            '- strengths: strong points and arguments from the conversation that support the recommendation\n'
            '- issues: concerns, risks, or counterarguments that were raised\n'
            '- fixes: specific actionable next steps or recommendations\n'
            '- Keep each item to one clear sentence\n'
            '- Empty arrays [] are fine if nothing applies\n'
            '- unique_catches: what did each reviewer uniquely spot that others missed? '
            'Attribute by name. This is the most valuable part of the debate — highlight it.'
        )
    else:
        intro = (
            "You are the final judge and arbiter in a structured multi-model AI debate. "
            "Multiple independent expert reviewers have evaluated a claim across several rounds of debate. "
            "Your role is to synthesize their arguments, weigh the quality of evidence and reasoning, "
            "and deliver a definitive final verdict.\n\n"
        )
        eval_criteria = (
            "Evaluation criteria:\n"
            "- Weight arguments by their specificity and evidence, not by how many models agree\n"
            "- A single well-reasoned dissent with concrete evidence outweighs vague consensus\n"
            "- If a reviewer cites web sources, documentation, or verifiable facts, weight that ABOVE pure reasoning\n"
            "- Be suspicious of reviewers who changed position without new evidence — that is groupthink, not insight\n"
            "- A reviewer who held their ground with evidence against majority pressure deserves extra weight\n"
            "- Note which reviewers changed their position and whether the reason was compelling\n"
            "- Identify if any reviewer spotted something others missed\n"
            "- Flag unresolved genuine disagreements vs. superficial differences in phrasing"
        )
        json_schema = (
            '\nRespond with valid JSON only. No markdown, no code fences, no preamble:\n'
            '{\n'
            '  "verdict": "PASS" | "FAIL" | "UNCERTAIN",\n'
            '  "confidence": <float 0.0-1.0>,\n'
            '  "headline": "<short verdict headline — the key recommendation or finding>",\n'
            '  "strengths": ["<point 1>", "<point 2>", ...],\n'
            '  "issues": ["<issue 1>", "<issue 2>", ...],\n'
            '  "fixes": ["<recommendation 1>", "<recommendation 2>", ...],\n'
            '  "model_votes": {"<model_name>": "PASS" | "FAIL" | "UNCERTAIN"},\n'
            '  "consensus": "FULL" | "MAJORITY" | "SPLIT",\n'
            '  "dissent": "<which model dissented, what they argued, and why it matters — or null>",\n'
            '  "unique_catches": ["<model_name> caught <what> that others missed", ...]\n'
            '}\n\n'
            'Rules for the arrays:\n'
            '- strengths: what is genuinely good — give credit where due, even on a FAIL\n'
            '- issues: specific problems found — be concrete, reference file/function names\n'
            '- fixes: actionable suggestions to resolve each issue — what exactly to change\n'
            '- Keep each item to one clear sentence\n'
            '- Empty arrays [] are fine if nothing applies\n'
            '- unique_catches: what did each reviewer uniquely spot that others missed? '
            'Attribute by name. This is the most valuable part of the debate — highlight it.'
        )

    parts = [intro + eval_criteria]
    if content:
        if len(content) > MAX_JUDGE_CONTENT_CHARS:
            content = content[:MAX_JUDGE_CONTENT_CHARS] + "\n[... content truncated for judge — advisors saw the full context]"
        parts.append(f"\nContext:\n{content}")
    label = "Decision" if domain == "business" else "Question"
    parts.append(f'\n{label}: "{claim}"')
    if role_context:
        parts.append(f"\n{role_context}")
    parts.append(f"\nDebate Transcript:\n{serialized}")
    parts.append(
        "\nSynthesize the debate above and deliver your final verdict. "
        "Your confidence score should reflect the strength of evidence, not just agreement levels — "
        "high consensus with weak reasoning deserves lower confidence than partial consensus with strong evidence."
    )
    parts.append(json_schema)
    return "\n".join(parts)


def parse_judge_response(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r"```json|```", "", text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {
                "verdict": "UNCERTAIN",
                "confidence": 0.0,
                "headline": "Judge response could not be parsed.",
                "strengths": [],
                "issues": ["Judge returned unparseable response."],
                "fixes": [],
                "model_votes": {},
                "consensus": "SPLIT",
                "dissent": None,
            }


async def run_judge(
    model: str,
    content: str,
    claim: str,
    transcript: list[dict],
    timeout: int,
    model_roles: dict[str, str] | None = None,
    domain: str = "technical",
    model_titles: dict[str, str] | None = None,
) -> tuple[dict, dict]:
    """Returns (parsed_result, usage_dict)."""
    prompt = _build_judge_prompt(content, claim, transcript, model_roles, domain=domain, model_titles=model_titles)
    messages = [{"role": "user", "content": prompt}]

    extra = MODEL_PARAMS.get(model, {})
    kwargs = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": JUDGE_MAX_TOKENS,
        **extra,
    }

    if model in JSON_MODE_MODELS:
        kwargs["response_format"] = {"type": "json_object"}

    raw = await asyncio.wait_for(
        get_client().chat.completions.create(**kwargs),
        timeout=timeout,
    )
    text = raw.choices[0].message.content or ""
    text = text.strip()
    usage = {
        "prompt_tokens": raw.usage.prompt_tokens,
        "completion_tokens": raw.usage.completion_tokens,
        "reasoning_tokens": getattr(
            raw.usage.completion_tokens_details, "reasoning_tokens", 0
        ) or 0,
    }
    return parse_judge_response(text), usage
