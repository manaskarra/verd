"""Integration tests — run full debate flow with mocked API responses."""

import json
from unittest import mock

import pytest

from verd.engine import run_debate


def _make_mock_response(text: str, prompt_tokens: int = 100, completion_tokens: int = 200):
    """Create a mock OpenAI ChatCompletion response."""
    resp = mock.MagicMock()
    resp.choices = [mock.MagicMock()]
    resp.choices[0].message.content = text
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.completion_tokens_details = mock.MagicMock()
    resp.usage.completion_tokens_details.reasoning_tokens = 0
    return resp


DEBATER_RESPONSE = (
    "After careful analysis, I believe this claim is correct. "
    "The implementation follows standard patterns and handles edge cases properly. "
    "Verdict: PASS. The code is well-structured and follows best practices."
)

DEBATER_RESPONSE_DISSENT = (
    "I disagree with the other reviewers. There is a subtle race condition "
    "in the concurrent access path that could cause data corruption. "
    "Verdict: FAIL. The mutex is not held across the full critical section."
)

FOLLOWUP_RESPONSE = (
    "Having reviewed the other arguments, I maintain my position. "
    "The evidence presented does not change my assessment. "
    "The core logic is sound. Verdict: PASS."
)

JUDGE_RESPONSE = json.dumps({
    "verdict": "PASS",
    "confidence": 0.85,
    "headline": "Code is correct with minor concerns",
    "strengths": ["Clean implementation", "Good error handling"],
    "issues": ["Could add more input validation"],
    "fixes": ["Add bounds checking on line 42"],
    "model_votes": {"gpt-5-mini": "PASS", "gemini-2.5-flash": "PASS"},
    "consensus": "FULL",
    "dissent": None,
    "unique_catches": ["gemini-2.5-flash caught potential overflow"],
})


def _mock_create_side_effect():
    """Return different responses based on prompt content."""

    async def side_effect(**kwargs):
        msgs = kwargs.get("messages", [])
        content = msgs[0]["content"] if msgs else ""

        # Judge call — has "final judge" or JSON format instructions in prompt
        if "final judge" in content.lower() or "respond with valid json" in content.lower():
            return _make_mock_response(JUDGE_RESPONSE, 500, 400)

        # Follow-up round — has "other reviewers said" in prompt
        if "other reviewers said" in content.lower():
            return _make_mock_response(FOLLOWUP_RESPONSE)

        # Round 0 — initial analysis
        return _make_mock_response(DEBATER_RESPONSE)

    return side_effect


@pytest.mark.asyncio
async def test_verdl_full_debate():
    """Run a full verdl debate with mocked API."""
    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(
        side_effect=_mock_create_side_effect()
    )

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        result = await run_debate(
            content="def add(a, b): return a + b",
            claim="is this function correct?",
            mode="verdl",
        )

    assert result["verdict"] == "PASS"
    assert result["mode"] == "verdl"
    assert "confidence" in result
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["elapsed"] > 0
    assert result["cost"] >= 0
    assert len(result["transcript"]) >= 2  # at least 2 debaters in round 0
    assert result["models_used"]  # at least one model responded
    assert result["judge"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_verd_full_debate():
    """Run a full verd debate (4 models, 2 rounds) with mocked API."""
    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(
        side_effect=_mock_create_side_effect()
    )

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        result = await run_debate(
            content="def divide(a, b): return a / b",
            claim="any bugs in this code?",
            mode="verd",
        )

    assert result["verdict"] in ("PASS", "FAIL", "UNCERTAIN")
    assert result["mode"] == "verd"
    assert result["judge"] == "o3"
    # verd has 4 debaters, round 0 should have all 4
    assert len(result["transcript"]) >= 4
    # Should have follow-up round entries too
    rounds_seen = {e["round"] for e in result["transcript"]}
    assert 0 in rounds_seen
    assert 1 in rounds_seen  # at least one follow-up round


@pytest.mark.asyncio
async def test_debate_with_empty_content():
    """Debate should work with empty content (claim-only)."""
    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(
        side_effect=_mock_create_side_effect()
    )

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        result = await run_debate(
            content="",
            claim="is the sky blue?",
            mode="verdl",
        )

    assert result["verdict"] in ("PASS", "FAIL", "UNCERTAIN")
    assert result["transcript"]


@pytest.mark.asyncio
async def test_debate_handles_model_failure():
    """If one model fails, debate should continue with remaining models."""
    call_count = {"n": 0}

    async def flaky_side_effect(**kwargs):
        call_count["n"] += 1
        content = kwargs.get("messages", [{}])[0].get("content", "")

        # Judge call
        if "final judge" in content.lower() or "respond with valid json" in content.lower():
            return _make_mock_response(JUDGE_RESPONSE, 500, 400)

        # Followup
        if "other reviewers said" in content.lower():
            return _make_mock_response(FOLLOWUP_RESPONSE)

        # Fail the first debater, succeed the rest
        if call_count["n"] == 1:
            raise Exception("Model temporarily unavailable")
        return _make_mock_response(DEBATER_RESPONSE)

    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(side_effect=flaky_side_effect)

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        result = await run_debate(
            content="some code",
            claim="is this correct?",
            mode="verdl",
        )

    # Should still produce a verdict even with one model down
    assert result["verdict"] in ("PASS", "FAIL", "UNCERTAIN")


@pytest.mark.asyncio
async def test_debate_result_structure():
    """Verify the result dict has all expected keys."""
    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(
        side_effect=_mock_create_side_effect()
    )

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        result = await run_debate(
            content="x = 1",
            claim="is this valid python?",
            mode="verdl",
        )

    expected_keys = {
        "verdict", "confidence", "headline", "strengths", "issues", "fixes",
        "model_votes", "consensus", "dissent", "elapsed", "mode",
        "models_used", "judge", "transcript", "usage", "cost",
    }
    assert expected_keys.issubset(result.keys()), f"Missing keys: {expected_keys - result.keys()}"


@pytest.mark.asyncio
async def test_debate_judge_fallback():
    """If primary judge fails, should fall back to another judge."""
    async def judge_fails_once(**kwargs):
        content = kwargs.get("messages", [{}])[0].get("content", "")

        if "final judge" in content.lower() or "respond with valid json" in content.lower():
            if not hasattr(judge_fails_once, "_judge_attempts"):
                judge_fails_once._judge_attempts = 0
            judge_fails_once._judge_attempts += 1
            if judge_fails_once._judge_attempts <= 2:
                raise Exception("Judge overloaded")
            return _make_mock_response(JUDGE_RESPONSE, 500, 400)

        if "other reviewers said" in content.lower():
            return _make_mock_response(FOLLOWUP_RESPONSE)

        return _make_mock_response(DEBATER_RESPONSE)

    mock_client = mock.MagicMock()
    mock_client.chat.completions.create = mock.AsyncMock(side_effect=judge_fails_once)

    with mock.patch("verd.engine.get_client", return_value=mock_client):
        with mock.patch("verd.judge.get_client", return_value=mock_client):
            result = await run_debate(
                content="code here",
                claim="check this",
                mode="verdl",
            )

    # Should get a result even after judge failures
    assert result["verdict"] in ("PASS", "FAIL", "UNCERTAIN")
