"""Tests for engine utilities."""

from verd.engine import _validate_response


def test_validate_normal_response():
    result = _validate_response("gpt-4.1", "This is a valid analysis with enough content to pass validation checks.")
    assert result is not None
    assert "valid analysis" in result


def test_validate_empty_response():
    assert _validate_response("gpt-4.1", "") is None
    assert _validate_response("gpt-4.1", None) is None


def test_validate_too_short_response():
    assert _validate_response("gpt-4.1", "OK") is None
    assert _validate_response("gpt-4.1", "   short   ") is None


def test_validate_strips_whitespace():
    result = _validate_response("gpt-4.1", "   This is a valid response with padding.   ")
    assert result is not None
    assert not result.startswith(" ")
    assert not result.endswith(" ")


def test_validate_truncates_very_long():
    long = "x" * 60_000
    result = _validate_response("gpt-4.1", long)
    assert result is not None
    assert len(result) < 60_000
    assert "[response truncated]" in result
