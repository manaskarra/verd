"""User config — env var support.

Precedence (highest wins):
  1. CLI flags (--judge, --debaters, --budget, --timeout)
  2. Per-tier env vars (VERDL_JUDGE, VERD_JUDGE, VERDH_JUDGE, etc.)
  3. Global env vars (VERD_JUDGE, VERD_DEBATERS, VERD_BUDGET, VERD_TIMEOUT)
  4. Built-in defaults (models.py)
"""

import os


def load_user_config(mode: str = "verd") -> dict:
    """Load user config from env vars. Returns dict.

    Keys: judge, debaters (list), budget (float), timeout (int)

    Per-tier env vars (e.g. VERDL_JUDGE, VERDH_DEBATERS) override
    global vars (VERD_JUDGE, VERD_DEBATERS).
    """
    cfg = {}

    # Tier prefix for per-tier env vars: VERDL_, VERD_, VERDH_
    tier_prefix = mode.upper() + "_"

    # Per-tier wins over global
    judge = os.getenv(tier_prefix + "JUDGE") or os.getenv("VERD_JUDGE")
    if judge:
        cfg["judge"] = judge

    debaters = os.getenv(tier_prefix + "DEBATERS") or os.getenv("VERD_DEBATERS")
    if debaters:
        cfg["debaters"] = [d.strip() for d in debaters.split(",") if d.strip()]

    budget = os.getenv(tier_prefix + "BUDGET") or os.getenv("VERD_BUDGET")
    if budget:
        try:
            cfg["budget"] = float(budget)
        except ValueError:
            pass

    timeout = os.getenv(tier_prefix + "TIMEOUT") or os.getenv("VERD_TIMEOUT")
    if timeout:
        try:
            cfg["timeout"] = int(timeout)
        except ValueError:
            pass

    return cfg


def apply_config_to_args(args, user_cfg: dict) -> None:
    """Apply user config as defaults — CLI flags take precedence."""
    if not args.judge and user_cfg.get("judge"):
        args.judge = user_cfg["judge"]

    if not args.debaters and user_cfg.get("debaters"):
        debaters = user_cfg["debaters"]
        if isinstance(debaters, str):
            debaters = [d.strip() for d in debaters.split(",") if d.strip()]
        args.debaters = debaters

    if args.budget is None and user_cfg.get("budget") is not None:
        args.budget = float(user_cfg["budget"])

    if args.timeout is None and user_cfg.get("timeout") is not None:
        args.timeout = int(user_cfg["timeout"])
