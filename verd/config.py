import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

VERSION = "0.2.1"

# Token budgets — reasoning models use these for thinking + output combined
# Keep high enough that reasoning models don't run out of thinking space
DEBATER_MAX_TOKENS = {
    "verdl": 2048,   # fast, concise
    "verd": 4096,    # balanced
    "verdh": 4096,   # deep analysis
}
JUDGE_MAX_TOKENS = 8192

TIMEOUTS = {
    "verdl": 30,
    "verd": 45,
    "verdh": 90,
}

JSON_MODE_MODELS = {
    "o3", "o3-mini", "o4-mini", "gpt-4.1", "gpt-5-mini", "gpt-5", "gpt-5.4"
}

# Pricing per 1M tokens (input, output) in USD
MODEL_PRICING = {
    "gpt-4.1":                  (2.00, 8.00),
    "gpt-5-mini":               (0.25, 2.00),
    "gpt-5.4":                  (2.50, 15.00),
    "claude-sonnet-4-6":        (3.00, 15.00),
    "claude-opus-4-6":          (5.00, 25.00),
    "gemini-2.5-flash":         (0.30, 2.50),
    "gemini-3.1-pro-preview":   (2.00, 12.00),
    "deepseek-r1":              (1.35, 5.40),
    "sonar-pro":                (3.00, 15.00),
    "o3":                       (2.00, 8.00),
    "o4-mini":                  (1.10, 4.40),
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
