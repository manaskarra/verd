"""Tests for CLI argument parsing and helpers."""

from verd.__main__ import make_parser, _estimate_debate_cost, _apply_model_overrides
from verd.models import MODELS
import copy


def test_parser_has_model_overrides():
    parser = make_parser()
    args = parser.parse_args(["test claim", "--judge", "gpt-5.4"])
    assert args.judge == "gpt-5.4"


def test_parser_has_budget():
    parser = make_parser()
    args = parser.parse_args(["test claim", "--budget", "0.50"])
    assert args.budget == 0.50


def test_parser_debaters_override():
    parser = make_parser()
    args = parser.parse_args(["test claim", "--debaters", "model-a", "model-b"])
    assert args.debaters == ["model-a", "model-b"]


def test_estimate_cost_returns_positive():
    for mode in ("verdl", "verd", "verdh"):
        cost = _estimate_debate_cost(mode)
        assert cost > 0, f"{mode} cost estimate should be positive"


def test_estimate_verdh_costs_more_than_verdl():
    assert _estimate_debate_cost("verdh") > _estimate_debate_cost("verdl")


def test_apply_judge_override():
    # Work on a copy so we don't mutate global state
    original = copy.deepcopy(MODELS["verd"])
    try:
        class Args:
            judge = "custom-judge"
            debaters = None
        _apply_model_overrides("verd", Args())
        assert MODELS["verd"]["judge"] == "custom-judge"
    finally:
        MODELS["verd"] = original


def test_apply_debaters_override():
    original = copy.deepcopy(MODELS["verd"])
    try:
        class Args:
            judge = None
            debaters = ["model-a", "model-b"]
        _apply_model_overrides("verd", Args())
        assert len(MODELS["verd"]["debaters"]) == 2
        assert MODELS["verd"]["debaters"][0]["model"] == "model-a"
        assert MODELS["verd"]["debaters"][1]["model"] == "model-b"
    finally:
        MODELS["verd"] = original
