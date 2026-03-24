"""Tests for judge response parsing."""

from verd.judge import parse_judge_response


def test_valid_json():
    raw = '{"verdict": "PASS", "confidence": 0.8, "headline": "All good", "strengths": ["a"], "issues": [], "fixes": [], "model_votes": {"gpt": "PASS"}, "consensus": "FULL", "dissent": null}'
    result = parse_judge_response(raw)
    assert result["verdict"] == "PASS"
    assert result["confidence"] == 0.8
    assert result["headline"] == "All good"
    assert result["model_votes"] == {"gpt": "PASS"}


def test_json_with_code_fences():
    raw = '```json\n{"verdict": "FAIL", "confidence": 0.6, "headline": "Bug found", "strengths": [], "issues": ["race condition"], "fixes": ["add lock"], "model_votes": {}, "consensus": "MAJORITY", "dissent": "model X disagreed"}\n```'
    result = parse_judge_response(raw)
    assert result["verdict"] == "FAIL"
    assert result["issues"] == ["race condition"]
    assert result["dissent"] == "model X disagreed"


def test_unparseable_returns_uncertain():
    result = parse_judge_response("This is not JSON at all, just rambling text.")
    assert result["verdict"] == "UNCERTAIN"
    assert result["confidence"] == 0.0
    assert "unparseable" in result["issues"][0].lower() or "parse" in result["issues"][0].lower()


def test_empty_string():
    result = parse_judge_response("")
    assert result["verdict"] == "UNCERTAIN"
    assert result["confidence"] == 0.0


def test_partial_json():
    raw = '{"verdict": "PASS", "confidence": 0.9'
    result = parse_judge_response(raw)
    assert result["verdict"] == "UNCERTAIN"


def test_json_with_extra_whitespace():
    raw = '  \n\n  {"verdict": "UNCERTAIN", "confidence": 0.3, "headline": "Unclear", "strengths": [], "issues": [], "fixes": [], "model_votes": {}, "consensus": "SPLIT", "dissent": null}  \n'
    result = parse_judge_response(raw)
    assert result["verdict"] == "UNCERTAIN"
    assert result["confidence"] == 0.3
