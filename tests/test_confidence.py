"""Tests for confidence calculation."""

from verd.engine import _calculate_confidence


def test_full_consensus_pass():
    result = {
        "model_votes": {"a": "PASS", "b": "PASS", "c": "PASS"},
        "confidence": 0.8,
        "verdict": "PASS",
    }
    roles = {"a": "analyst", "b": "devils_advocate", "c": "logic_checker"}
    conf = _calculate_confidence(result, roles)
    assert conf > 0.7


def test_full_consensus_fail():
    result = {
        "model_votes": {"a": "FAIL", "b": "FAIL", "c": "FAIL"},
        "confidence": 0.8,
        "verdict": "FAIL",
    }
    roles = {"a": "analyst", "b": "logic_checker", "c": "pragmatist"}
    conf = _calculate_confidence(result, roles)
    assert conf > 0.7


def test_split_vote_lowers_confidence():
    result = {
        "model_votes": {"a": "PASS", "b": "FAIL", "c": "PASS", "d": "FAIL"},
        "confidence": 0.5,
        "verdict": "PASS",
    }
    roles = {"a": "analyst", "b": "devils_advocate", "c": "logic_checker", "d": "pragmatist"}
    conf = _calculate_confidence(result, roles)
    assert conf < 0.7


def test_fact_checker_dissent_lowers_more():
    """A fact_checker disagreeing should lower confidence more than a devils_advocate."""
    base = {
        "model_votes": {"a": "PASS", "b": "PASS", "c": "FAIL"},
        "confidence": 0.7,
        "verdict": "PASS",
    }
    # Dissenter is devils_advocate (weight 0.8)
    roles_da = {"a": "analyst", "b": "logic_checker", "c": "devils_advocate"}
    conf_da = _calculate_confidence(base, roles_da)

    # Dissenter is fact_checker (weight 1.3)
    roles_fc = {"a": "analyst", "b": "logic_checker", "c": "fact_checker"}
    conf_fc = _calculate_confidence(base, roles_fc)

    assert conf_fc < conf_da, "fact_checker dissent should lower confidence more than devils_advocate"


def test_uncertain_verdict_caps_confidence():
    result = {
        "model_votes": {"a": "PASS", "b": "PASS"},
        "confidence": 0.9,
        "verdict": "UNCERTAIN",
    }
    roles = {"a": "analyst", "b": "logic_checker"}
    conf = _calculate_confidence(result, roles)
    assert conf <= 0.5


def test_empty_votes():
    result = {"model_votes": {}, "confidence": 0.5, "verdict": "PASS"}
    roles = {}
    conf = _calculate_confidence(result, roles)
    assert conf <= 0.5


def test_confidence_bounded():
    """Confidence should always be between 0.1 and 0.95."""
    result = {
        "model_votes": {"a": "PASS", "b": "PASS", "c": "PASS", "d": "PASS", "e": "PASS"},
        "confidence": 1.0,
        "verdict": "PASS",
    }
    roles = {"a": "analyst", "b": "analyst", "c": "analyst", "d": "analyst", "e": "analyst"}
    conf = _calculate_confidence(result, roles)
    assert 0.1 <= conf <= 0.95
