"""Tests for the date_precision field on normalized arxiv papers.

ADR-0015 §4.1 mandates a `date_precision` sibling next to `date`. arxiv
always emits day-precision dates because `result.published` is the v1
submission timestamp (verified empirically against multi-version papers,
closing ADR-0015 §7(i)).

Run with:
    pytest tests/test_arxiv_fetcher_date_precision.py
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
from types import SimpleNamespace

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import arxiv_fetcher  # noqa: E402


def _fake_result(published: dt.datetime) -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="http://arxiv.org/abs/2401.00001v1",
        doi="10.1/test",
        title="Test paper",
        summary="Test abstract",
        authors=[SimpleNamespace(name="A. Author")],
        categories=["cs.LG"],
        published=published,
    )


def _install_one_result(monkeypatch, result):
    """Same monkeypatch pattern as tests/test_run_historical.py
    (_install_arxiv_capture), but yields a single fake Result so we can
    assert against the normalized output."""
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def results(self, search):
            return iter([result])

    def fake_search(**kw):
        return SimpleNamespace(**kw)

    monkeypatch.setattr(arxiv_fetcher.arxiv, "Client", FakeClient)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", fake_search)


def test_arxiv_normalized_paper_has_date_precision_day(monkeypatch):
    result = _fake_result(dt.datetime(2024, 1, 15, 12, 0, 0))
    _install_one_result(monkeypatch, result)
    papers = arxiv_fetcher.fetch(
        ["cs.LG"], from_date="2024-01-01", to_date="2024-01-31"
    )
    assert len(papers) == 1
    assert papers[0]["date_precision"] == "day"


def test_arxiv_normalized_paper_date_is_yyyymmdd_string(monkeypatch):
    result = _fake_result(dt.datetime(2024, 1, 15, 12, 0, 0))
    _install_one_result(monkeypatch, result)
    papers = arxiv_fetcher.fetch(
        ["cs.LG"], from_date="2024-01-01", to_date="2024-01-31"
    )
    assert papers[0]["date"] == "2024-01-15"
    parsed = dt.date.fromisoformat(papers[0]["date"])
    assert parsed == dt.date(2024, 1, 15)
