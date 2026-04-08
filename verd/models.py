"""Model tiers and role assignments for debate.

Each model has a role that shapes its prompt and the judge's weighting.
Users can customize models and roles for their provider.

Supports two domains:
- "technical" (default) — code review, architecture, technical decisions
- "business" — business decisions, market analysis, strategy
"""

ROLES = {
    # Role name → (description for prompt, weight hint for judge)
    "analyst": (
        "You are the primary analyst. Give a thorough, balanced initial assessment. "
        "Cover the main arguments for and against. Be specific and evidence-based.",
        "general assessment",
    ),
    "devils_advocate": (
        "You are the devil's advocate. Your job is to find what others miss — "
        "edge cases, hidden assumptions, failure modes, and contrarian perspectives. "
        "If everyone agrees, find the strongest counterargument. "
        "If there's an obvious answer, question why it might be wrong.",
        "contrarian analysis and edge cases",
    ),
    "logic_checker": (
        "You are the logic checker. Focus on reasoning quality — "
        "are the arguments logically sound? Are there fallacies, circular reasoning, "
        "or unsupported leaps? Verify that conclusions follow from premises. "
        "If code is involved, trace execution paths and check for off-by-one, "
        "race conditions, and boundary errors.",
        "logical reasoning and formal analysis",
    ),
    "fact_checker": (
        "You are the fact checker with web search capabilities. "
        "Verify claims against real-world sources. Check if APIs, libraries, "
        "or approaches mentioned actually exist and work as described. "
        "Ground the discussion in documented facts, not assumptions.",
        "web-grounded factual verification",
    ),
    "pragmatist": (
        "You are the pragmatist. Focus on real-world practicality — "
        "will this actually work in production? What are the operational costs, "
        "maintenance burden, team skill requirements, and deployment complexity? "
        "Theory is nice but what matters is shipping.",
        "practical and operational assessment",
    ),
}

BUSINESS_ROLES = {
    "strategist": (
        "You are a business strategy analyst. Evaluate market viability, unit economics, "
        "competitive positioning, and revenue potential. Use specific numbers — TAM, CAC, "
        "LTV, break-even timelines, margin analysis. Never say 'the market is competitive' "
        "without stating how many competitors, their pricing, and their market share.",
        "business strategy and financial analysis",
    ),
    "devils_advocate": (
        "You are the risk hunter. Your job is to find the fatal flaw in this plan. "
        "What kills this business? What assumption is dangerously wrong? What competitor "
        "move would make this irrelevant? If the founder is excited, find the reason they "
        "shouldn't be. Be specific — name the exact scenario that causes failure.",
        "risk identification and contrarian analysis",
    ),
    "assumption_checker": (
        "You are the assumption auditor. Every business plan rests on assumptions — "
        "'customers will pay X', 'we can acquire users for Y', 'the market is growing at Z%'. "
        "Identify every assumption, rate its reliability, and challenge each one with market "
        "evidence. If a number isn't backed by data, flag it.",
        "assumption validation and evidence audit",
    ),
    "fact_checker": (
        "You are the market reality checker. Verify claims with real data — competitor counts, "
        "actual pricing in the market, demographic data, regulatory requirements, industry "
        "benchmarks. If the plan says 'no competitors', find the competitors. If it says "
        "'high demand', check if that demand is documented. Ground everything in verifiable facts.",
        "market data verification and competitive intelligence",
    ),
    "pragmatist": (
        "You are the execution realist. Can this team, with this budget, in this timeline, "
        "actually pull this off? What operational bottlenecks will they hit? What hires are "
        "needed that aren't budgeted? What regulatory or compliance steps are they missing? "
        "Focus on the gap between the plan on paper and what it takes to execute in reality.",
        "operational feasibility and execution assessment",
    ),
}

def get_roles(domain: str = "technical") -> dict:
    """Return the role definitions for the given domain."""
    if domain == "business":
        return BUSINESS_ROLES
    return ROLES

MODELS = {
    "verdl": {
        "debaters": [
            {"model": "gpt-4.1-mini", "role": "analyst"},
            {"model": "gemini-3.1-flash-lite-preview", "role": "devils_advocate"},
        ],
        "judge": "o4-mini",
        "rounds": 1,
    },
    "verd": {
        "debaters": [
            {"model": "claude-sonnet-4-6", "role": "analyst"},
            {"model": "gpt-4.1", "role": "devils_advocate"},
            {"model": "gemini-3.1-pro-preview", "role": "logic_checker"},
            {"model": "gpt-4.1-mini", "role": "pragmatist"},
        ],
        "judge": "o3",
        "rounds": 2,
    },
    "verdh": {
        "debaters": [
            {"model": "claude-opus-4-6", "role": "analyst"},
            {"model": "deepseek-r1", "role": "devils_advocate"},
            {"model": "gemini-3.1-pro-preview", "role": "logic_checker"},
            {"model": "sonar-pro", "role": "fact_checker"},
            {"model": "gpt-4.1", "role": "pragmatist"},
        ],
        "judge": "o3",
        "rounds": 3,
    },
    "business": {
        "debaters": [
            {"model": "claude-sonnet-4-6", "role": "strategist"},
            {"model": "gpt-4.1-mini", "role": "devils_advocate"},
            {"model": "gemini-3.1-pro-preview", "role": "assumption_checker"},
            {"model": "deepseek-r1", "role": "fact_checker"},
            {"model": "sonar-pro", "role": "pragmatist"},
        ],
        "judge": "o3",
        "rounds": 2,
        "domain": "business",
    },
}

MODEL_PARAMS = {}

# Context window sizes in tokens — used to cap content for smaller models
MODEL_CONTEXT_WINDOWS = {
    "gpt-4.1-mini":                  1_000_000,
    "gpt-4.1":                       1_000_000,
    "o3":                             200_000,
    "o4-mini":                        200_000,
    "claude-opus-4-6":               1_000_000,
    "claude-sonnet-4-6":             1_000_000,
    "gemini-3.1-flash-lite-preview": 1_000_000,
    "gemini-3.1-pro-preview":        1_000_000,
    "deepseek-r1":                    64_000,
    "sonar-pro":                     200_000,
}

