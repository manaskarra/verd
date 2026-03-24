"""Tests for user config file + env var support."""

import os
import tempfile
from pathlib import Path
from unittest import mock

from verd.user_config import _parse_simple_yaml, load_user_config, apply_config_to_args


def test_parse_simple_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("judge: gpt-5.4\n")
        f.write("budget: 1.50\n")
        f.write("timeout: 60\n")
        f.write("# this is a comment\n")
        f.write("\n")
        f.write("debaters: model-a, model-b, model-c\n")
        f.name
    try:
        data = _parse_simple_yaml(Path(f.name))
        assert data["judge"] == "gpt-5.4"
        assert data["budget"] == "1.50"
        assert data["timeout"] == "60"
        assert data["debaters"] == ["model-a", "model-b", "model-c"]
    finally:
        os.unlink(f.name)


def test_parse_simple_yaml_handles_quotes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write('judge: "claude-sonnet-4-6"\n')
        f.name
    try:
        data = _parse_simple_yaml(Path(f.name))
        assert data["judge"] == "claude-sonnet-4-6"
    finally:
        os.unlink(f.name)


def test_parse_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("")
        f.name
    try:
        data = _parse_simple_yaml(Path(f.name))
        assert data == {}
    finally:
        os.unlink(f.name)


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
    # CLI values should NOT be overwritten
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
