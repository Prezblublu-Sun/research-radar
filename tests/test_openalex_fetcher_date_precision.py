"""Tests for the date_precision heuristic in fetchers/openalex_fetcher._normalize.

Per ADR-0015 §4.1, OpenAlex always emits publication_date as YYYY-MM-DD even
when the underlying record is month-only or year-only. Precision is inferred
from the trailing suffix:
  - "-01-01"  -> year
  - "-01"  (and not "-01-01")  -> month
  - otherwise  -> day
  - empty/missing  -> date="", precision="year" (defensive default)

Run with:
    pytest tests/test_openalex_fetcher_date_precision.py
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import openalex_fetcher  # noqa: E402


def _install_single_work(monkeypatch, work: dict):
    """Fake requests.get to return a single-work OpenAlex payload."""
    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [work], "meta": {"next_cursor": None}}

    def fake_get(url, params=None, **kw):
        return FakeResp()

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)


def _bare_work(publication_date) -> dict:
    """Minimal OpenAlex work dict; only publication_date varies."""
    w = {
        "id": "https://openalex.org/W1",
        "doi": "https://doi.org/10.1/test",
        "title": "test paper",
        "publication_year": 2024,
        "type": "article",
    }
    if publication_date is not None:
        w["publication_date"] = publication_date
    return w


def test_full_date_produces_day_precision(monkeypatch):
    _install_single_work(monkeypatch, _bare_work("2024-03-15"))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == "2024-03-15"
    assert p["date_precision"] == "day"


def test_first_of_non_january_month_produces_month_precision(monkeypatch):
    _install_single_work(monkeypatch, _bare_work("2024-03-01"))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == "2024-03-01"
    assert p["date_precision"] == "month"


def test_january_first_produces_year_precision(monkeypatch):
    _install_single_work(monkeypatch, _bare_work("2024-01-01"))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == "2024-01-01"
    assert p["date_precision"] == "year"


def test_december_first_is_month_not_year(monkeypatch):
    # Guard against an over-eager rule that fires on "-01" alone.
    _install_single_work(monkeypatch, _bare_work("2024-12-01"))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == "2024-12-01"
    assert p["date_precision"] == "month"


def test_missing_publication_date_defaults_to_empty_and_year(monkeypatch):
    _install_single_work(monkeypatch, _bare_work(None))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == ""
    assert p["date_precision"] == "year"


def test_empty_publication_date_defaults_to_empty_and_year(monkeypatch):
    _install_single_work(monkeypatch, _bare_work(""))
    [p] = openalex_fetcher.fetch(concepts=[], keywords=["x"],
                                 from_date="2024-01-01", to_date="2024-12-31")
    assert p["date"] == ""
    assert p["date_precision"] == "year"
