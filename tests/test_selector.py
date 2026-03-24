"""Tests for keyword-based file selection."""

from pathlib import Path

from verd.selector import select_by_keywords, _extract_keywords


def test_extract_keywords_filters_stopwords():
    kws = _extract_keywords("is this auth middleware secure?")
    assert "is" not in kws
    assert "this" not in kws
    assert "auth" in kws
    assert "middleware" in kws
    assert "secure" in kws


def test_extract_keywords_empty():
    assert _extract_keywords("is it?") == []


def test_select_by_filename_match():
    files = [
        (Path("auth.py"), "def check_token(): pass", ".py"),
        (Path("utils.py"), "def helper(): pass", ".py"),
        (Path("readme.md"), "# Hello", ".md"),
    ]
    indices = select_by_keywords(files, "is the auth module secure?")
    assert indices is not None
    assert 0 in indices  # auth.py should be selected


def test_select_by_content_match():
    files = [
        (Path("main.py"), "from db import connection\ndef run(): pass", ".py"),
        (Path("db.py"), "def connection(): return pg_pool", ".py"),
        (Path("views.py"), "def render(): return html", ".py"),
    ]
    indices = select_by_keywords(files, "is the database connection pooling correct?")
    assert indices is not None
    assert 1 in indices  # db.py has "connection"


def test_select_returns_none_for_no_matches():
    files = [
        (Path("alpha.py"), "def foo(): pass", ".py"),
        (Path("beta.py"), "def bar(): pass", ".py"),
    ]
    result = select_by_keywords(files, "is it?")
    assert result is None


def test_select_includes_dependencies():
    files = [
        (Path("auth.py"), "from tokens import verify\ndef check(): pass", ".py"),
        (Path("tokens.py"), "def verify(t): return True", ".py"),
        (Path("utils.py"), "def helper(): pass", ".py"),
    ]
    indices = select_by_keywords(files, "is auth secure?")
    assert indices is not None
    assert 0 in indices  # auth.py
    assert 1 in indices  # tokens.py (dependency)
