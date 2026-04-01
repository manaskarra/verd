import os
from pathlib import Path
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Search for .env: cwd first, then walk up parents, finally verd's own dir.
def _find_dotenv() -> Path | None:
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents]:
        candidate = d / ".env"
        if candidate.is_file():
            return candidate
    # Fallback: verd package's own .env
    pkg = Path(__file__).resolve().parent.parent / ".env"
    return pkg if pkg.is_file() else None

_env_path = _find_dotenv()
if _env_path:
    load_dotenv(_env_path)

VERSION = "0.4.0"

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
    "o3", "o3-mini", "o4-mini",
    "gpt-4.1", "gpt-4.1-mini",
}

# Pricing per 1M tokens (input, output) in USD
MODEL_PRICING = {
    "gpt-4.1":                       (1.46,  8.00),
    "gpt-4.1-mini":                  (0.307, 1.60),
    "o3":                            (1.65,  8.00),
    "o4-mini":                       (1.03,  4.40),
    "claude-sonnet-4-6":             (1.13, 15.00),
    "claude-opus-4-6":               (2.16, 25.00),
    "gemini-3.1-flash-lite-preview": (0.16,  1.50),
    "gemini-3.1-pro-preview":        (1.13, 12.07),
    "deepseek-r1":                   (0.723, 2.55),
    "sonar-pro":                     (3.00, 28.69),
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
