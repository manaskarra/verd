"""Model tiers and role assignments for debate.

Each model has a role that shapes its prompt and the judge's weighting.
Users can customize models and roles for their provider.
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

MODELS = {
    "verdl": {
        "debaters": [
            {"model": "openai/gpt-4.1-mini", "role": "analyst"},
            {"model": "google/gemini-3.1-flash-lite-preview", "role": "devils_advocate"},
        ],
        "judge": "openai/o4-mini",
        "rounds": 1,
    },
    "verd": {
        "debaters": [
            {"model": "anthropic/claude-sonnet-4.6", "role": "analyst"},
            {"model": "openai/gpt-4.1", "role": "devils_advocate"},
            {"model": "google/gemini-3.1-pro-preview", "role": "logic_checker"},
            {"model": "openai/gpt-4.1-mini", "role": "pragmatist"},
        ],
        "judge": "openai/o3",
        "rounds": 2,
    },
    "verdh": {
        "debaters": [
            {"model": "anthropic/claude-opus-4.6", "role": "analyst"},
            {"model": "deepseek/deepseek-r1", "role": "devils_advocate"},
            {"model": "google/gemini-3.1-pro-preview", "role": "logic_checker"},
            {"model": "perplexity/sonar-pro", "role": "fact_checker"},
            {"model": "openai/gpt-4.1", "role": "pragmatist"},
        ],
        "judge": "openai/o3",
        "rounds": 3,
    },
}

MODEL_PARAMS = {
    "perplexity/sonar-pro": {
        "web_search_options": {"search_context_size": "high"},
    },
}

# Context window sizes in tokens — used to cap content for smaller models
MODEL_CONTEXT_WINDOWS = {
    "openai/gpt-4.1-mini":          1_000_000,
    "openai/gpt-4.1":               1_000_000,
    "openai/o3":                     200_000,
    "openai/o4-mini":                200_000,
    "anthropic/claude-opus-4.6":     1_000_000,
    "anthropic/claude-sonnet-4.6":   1_000_000,
    "google/gemini-3.1-flash-lite-preview": 1_000_000,
    "google/gemini-3.1-pro-preview":        1_000_000,
    "deepseek/deepseek-r1":           64_000,
    "perplexity/sonar-pro":          200_000,
}

