"""User config file + env var support.

Precedence (highest wins):
  1. CLI flags (--judge, --debaters, --budget, --timeout)
  2. Environment variables (VERD_JUDGE, VERD_DEBATERS, VERD_BUDGET, VERD_TIMEOUT)
  3. Config file (~/.verd.yaml or ~/.config/verd/config.yaml)
  4. Built-in defaults (models.py)
"""

import logging
import os
from pathlib import Path

log = logging.getLogger("verd.config")

_CONFIG_PATHS = [
    Path.home() / ".verd.yaml",
    Path.home() / ".config" / "verd" / "config.yaml",
]


def _load_yaml_config() -> dict:
    """Load the first config file found. Returns empty dict if none."""
    for path in _CONFIG_PATHS:
        if path.is_file():
            try:
                import yaml
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                log.info("loaded config from %s", path)
                return data
            except ImportError:
                # PyYAML not installed — try simple key: value parsing
                return _parse_simple_yaml(path)
            except Exception as e:
                log.warning("failed to load %s: %s", path, e)
    return {}


def _parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML-like parser for flat key: value configs (no PyYAML needed)."""
    data = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not value:
                continue
            # Handle lists written as "a, b, c" or "a b c"
            if "," in value:
                data[key] = [v.strip() for v in value.split(",") if v.strip()]
            else:
                data[key] = value
    except Exception as e:
        log.warning("failed to parse %s: %s", path, e)
    return data


def load_user_config() -> dict:
    """Load user config from file + env vars. Returns merged dict.

    Keys: judge, debaters (list), budget (float), timeout (int)
    """
    cfg = _load_yaml_config()

    # Env vars override file config
    if os.getenv("VERD_JUDGE"):
        cfg["judge"] = os.environ["VERD_JUDGE"]
    if os.getenv("VERD_DEBATERS"):
        cfg["debaters"] = os.environ["VERD_DEBATERS"].split(",")
    if os.getenv("VERD_BUDGET"):
        try:
            cfg["budget"] = float(os.environ["VERD_BUDGET"])
        except ValueError:
            pass
    if os.getenv("VERD_TIMEOUT"):
        try:
            cfg["timeout"] = int(os.environ["VERD_TIMEOUT"])
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
