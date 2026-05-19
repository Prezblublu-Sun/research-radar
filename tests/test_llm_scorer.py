"""Tests for ADR-0017 §Decision 1 — pipeline.llm_scorer retry contract.

The scorer's `score_batch` now gives each paper up to 3 attempts:
  attempt 1: historical prompt verbatim (transient hiccup tolerance)
  attempts 2 & 3: prepend the strict-JSON nudge
  all 3 fail: priority=None + scorer_failed=True (NOT the silent "Low"
              fallback the old code wrote).

These tests stub the OpenAI client at the lowest reasonable layer
(`llm_scorer.client.chat.completions.create`) so the real ``score()``
JSON parser is exercised, but no network calls happen. The failures
logger is no-op'd so tests don't pollute ``data/llm_cache/failures``.

Run with:
    pytest tests/test_llm_scorer.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import llm_scorer  # noqa: E402  (conftest sets OPENAI_API_KEY)


# ---------------------------------------------------------------- helpers

def _fake_resp(content: str, model: str = "test-model"):
    """Minimal stand-in for the OpenAI ChatCompletion response object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model=model,
    )


def _paper(doi: str = "10.1/x") -> dict:
    return {
        "doi": doi,
        "title": "Test paper",
        "abstract": "Test abstract.",
        "direction": "hip_implant",
        "direction_name": "Hip Implant",
        "venue": "Test J",
        "year": 2024,
        "cited_by_count": 0,
    }


_DIRECTIONS = {"hip_implant": {"llm_prompt_focus": "focus text"}}


@pytest.fixture(autouse=True)
def _silence_failure_logger(monkeypatch):
    """Tests assert behaviour, not failure-log filesystem side effects."""
    monkeypatch.setattr(llm_scorer, "_log_scoring_failure",
                        lambda *a, **k: None)


def _install_create_sequence(monkeypatch, responses):
    """Return a list of captured ``messages`` dicts; one entry per create()."""
    captured: list[list[dict]] = []
    it = iter(responses)

    def fake_create(**kwargs):
        captured.append(kwargs.get("messages", []))
        item = next(it)
        if isinstance(item, BaseException):
            raise item
        return _fake_resp(item)

    monkeypatch.setattr(llm_scorer.client.chat.completions, "create",
                        fake_create)
    return captured


_GOOD_JSON = json.dumps({
    "priority": "High", "relevance_to_user": "yes", "tags": ["t"],
    "summary_zh": {"motivation": "动机"},
})


# ---------------------------------------------------------------- tests

def test_happy_path_no_retry(monkeypatch):
    captured = _install_create_sequence(monkeypatch, [_GOOD_JSON])
    out, raws = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert len(captured) == 1  # LLM hit exactly once
    assert out[0]["llm"]["priority"] == "High"
    assert "scorer_failed" not in out[0]["llm"]
    # First-attempt system prompt is the bare prompt, no strict-JSON nudge.
    sys_msg = captured[0][0]["content"]
    assert "CRITICAL: Output ONLY valid JSON" not in sys_msg


def test_retry_succeeds_on_second_attempt(monkeypatch):
    captured = _install_create_sequence(monkeypatch, ["not json at all", _GOOD_JSON])
    out, _ = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert len(captured) == 2
    assert out[0]["llm"]["priority"] == "High"
    assert "scorer_failed" not in out[0]["llm"]
    # Attempt 2 prepends the strict-JSON nudge to the system prompt.
    assert "CRITICAL: Output ONLY valid JSON" not in captured[0][0]["content"]
    assert "CRITICAL: Output ONLY valid JSON" in captured[1][0]["content"]


def test_retry_succeeds_on_third_attempt(monkeypatch):
    captured = _install_create_sequence(
        monkeypatch, ["nope", "still nope", _GOOD_JSON]
    )
    out, _ = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert len(captured) == 3
    assert out[0]["llm"]["priority"] == "High"
    assert "scorer_failed" not in out[0]["llm"]
    # Attempts 2 and 3 both carry the nudge.
    for i in (1, 2):
        assert "CRITICAL: Output ONLY valid JSON" in captured[i][0]["content"]


def test_all_three_attempts_fail(monkeypatch):
    captured = _install_create_sequence(
        monkeypatch, ["nope1", "nope2", "nope3"]
    )
    out, raws = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert len(captured) == 3
    llm = out[0]["llm"]
    # ADR-0017 contract: priority is Python None (not "Low"), with flag set.
    assert llm["priority"] is None
    assert llm["scorer_failed"] is True
    assert llm["scorer_failed_attempts"] == 3
    # scorer_failed_reason is a string carrying the last exception message
    assert isinstance(llm["scorer_failed_reason"], str)
    assert llm["scorer_failed_reason"]  # non-empty
    # No silent Low contamination
    assert llm["priority"] != "Low"
    assert raws[0] == {}


def test_non_json_exception_also_retries(monkeypatch):
    """Network-level errors (simulated 429 / ConnectionError) trigger
    the same retry path as JSON-parse failures — the loop catches any
    Exception, not just json.JSONDecodeError."""
    captured = _install_create_sequence(
        monkeypatch, [ConnectionError("simulated 429"), _GOOD_JSON]
    )
    out, _ = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert len(captured) == 2  # retry actually fired
    assert out[0]["llm"]["priority"] == "High"
    assert "scorer_failed" not in out[0]["llm"]
