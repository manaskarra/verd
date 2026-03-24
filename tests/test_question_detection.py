"""Tests for question vs claim detection."""

from verd.engine import _is_question


def test_open_questions():
    assert _is_question("What's the best approach for caching?") is True
    assert _is_question("How should we handle authentication?") is True
    assert _is_question("Which database should we use?") is True
    assert _is_question("Should we migrate to gRPC?") is True
    assert _is_question("Where is the bottleneck?") is True
    assert _is_question("Why is this slow?") is True


def test_yes_no_claims():
    assert _is_question("Is this secure?") is False
    assert _is_question("Is it correct?") is False
    assert _is_question("Are there any bugs?") is False
    assert _is_question("Does this handle edge cases?") is False
    assert _is_question("Can this be bypassed?") is False


def test_statements():
    assert _is_question("any race conditions in this code") is False


def test_question_mark_fallback():
    assert _is_question("Kafka or RabbitMQ?") is True
    assert _is_question("monolith or microservices?") is True
