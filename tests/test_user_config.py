"""Tests for user config env var support."""

import os
from unittest import mock

from verd.user_config import load_user_config, apply_config_to_args


def test_env_vars_override():
    with mock.patch.dict(os.environ, {
        "VERD_JUDGE": "my-judge",
        "VERD_DEBATERS": "model-x,model-y",
        "VERD_BUDGET": "2.00",
        "VERD_TIMEOUT": "30",
    }):
        cfg = load_user_config()
        assert cfg["judge"] == "my-judge"
        assert cfg["debaters"] == ["model-x", "model-y"]
        assert cfg["budget"] == 2.00
        assert cfg["timeout"] == 30


def test_per_tier_env_vars_override_global():
    with mock.patch.dict(os.environ, {
        "VERD_JUDGE": "global-judge",
        "VERDL_JUDGE": "light-judge",
        "VERD_DEBATERS": "global-a,global-b",
        "VERDL_DEBATERS": "light-a,light-b",
    }):
        cfg = load_user_config("verdl")
        assert cfg["judge"] == "light-judge"
        assert cfg["debaters"] == ["light-a", "light-b"]


def test_per_tier_falls_back_to_global():
    with mock.patch.dict(os.environ, {
        "VERD_JUDGE": "global-judge",
    }, clear=False):
        # Remove any tier-specific var
        os.environ.pop("VERDH_JUDGE", None)
        cfg = load_user_config("verdh")
        assert cfg["judge"] == "global-judge"


def test_apply_config_cli_wins():
    """CLI flags should take precedence over config."""
    class Args:
        judge = "cli-judge"
        debaters = ["cli-model"]
        budget = 0.50
        timeout = 10

    user_cfg = {
        "judge": "config-judge",
        "debaters": ["config-model-a", "config-model-b"],
        "budget": 5.00,
        "timeout": 120,
    }
    apply_config_to_args(Args(), user_cfg)
    assert Args.judge == "cli-judge"


def test_apply_config_fills_gaps():
    """Config should fill in values not set by CLI."""
    class Args:
        judge = None
        debaters = None
        budget = None
        timeout = None

    user_cfg = {
        "judge": "config-judge",
        "debaters": "model-a, model-b",
        "budget": "1.50",
        "timeout": "45",
    }
    args = Args()
    apply_config_to_args(args, user_cfg)
    assert args.judge == "config-judge"
    assert args.debaters == ["model-a", "model-b"]
    assert args.budget == 1.50
    assert args.timeout == 45


def test_apply_config_empty():
    """Empty config should not modify args."""
    class Args:
        judge = None
        debaters = None
        budget = None
        timeout = None

    args = Args()
    apply_config_to_args(args, {})
    assert args.judge is None
    assert args.debaters is None
