"""Tests for security utilities."""

from verd.security import validate_claim, validate_content, parse_last_n, check_rate_limit, is_safe_url


def test_validate_claim_truncates():
    long_claim = "x" * 3000
    result = validate_claim(long_claim)
    assert len(result) <= 2004  # MAX_CLAIM_LENGTH + "..."


def test_validate_claim_strips():
    assert validate_claim("  hello  ") == "hello"


def test_validate_claim_empty_gets_default():
    assert validate_claim("") == "Is this correct?"
    assert validate_claim("   ") == "Is this correct?"


def test_validate_content_truncates():
    long_content = "x" * 300_000
    result = validate_content(long_content)
    assert len(result) < 300_000
    assert "truncated" in result


def test_parse_last_n():
    assert parse_last_n("last 50 messages") == 50
    assert parse_last_n("no number here") is None
    assert parse_last_n("last 999") == 200  # capped at MAX_LAST_N


def test_rate_limit():
    # Fresh user should pass
    assert check_rate_limit("test_user_unique_12345") is None


def test_safe_url_blocks_private():
    assert is_safe_url("http://127.0.0.1/admin") is False
    assert is_safe_url("http://localhost/secret") is False
    assert is_safe_url("http://169.254.169.254/metadata") is False
    assert is_safe_url("ftp://example.com/file") is False
