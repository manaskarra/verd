import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

VERSION = "0.3.5"

# Token budgets — reasoning models use these for thinking + output combined
# Keep high enough that reasoning models don't run out of thinking space
DEBATER_MAX_TOKENS = {
    "verdl": 2048,   # fast, concise
    "verd": 4096,    # balanced
    "verdh": 8192,   # deep analysis — reasoning models need headroom for chain-of-thought
}
JUDGE_MAX_TOKENS = 8192

TIMEOUTS = {
    "verdl": 30,
    "verd": 45,
    "verdh": 120,  # reasoning models (deepseek-r1, o3) regularly need 60-90s
}

JSON_MODE_MODELS = {
    "openai/o3", "openai/o3-mini", "openai/o4-mini",
    "openai/gpt-4.1", "openai/gpt-4.1-mini",
}

# Pricing per 1M tokens (input, output) in USD
MODEL_PRICING = {
    "openai/gpt-4.1":                       (1.46,  8.00),
    "openai/gpt-4.1-mini":                  (0.307, 1.60),
    "openai/o3":                            (1.65,  8.00),
    "openai/o4-mini":                       (1.03,  4.40),
    "anthropic/claude-sonnet-4.6":          (1.13, 15.00),
    "anthropic/claude-opus-4.6":            (2.16, 25.00),
    "google/gemini-3.1-flash-lite-preview": (0.16,  1.50),
    "google/gemini-3.1-pro-preview":        (1.13, 12.07),
    "deepseek/deepseek-r1":                 (0.723, 2.55),
    "perplexity/sonar-pro":                 (3.00, 28.69),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate cost in USD for a model call."""
    input_price, output_price = MODEL_PRICING.get(model, (5.00, 15.00))
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


_client = None


def get_client() -> AsyncOpenAI:
    """Lazy client init — only validates env vars on first actual API call."""
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Add it to your .env file or export it."
            )
        if not base_url:
            raise EnvironmentError(
                "OPENAI_BASE_URL is not set. Add it to your .env file or export it."
            )
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client
