"""Tests for the AND→OR fan-out dispatch in fetchers/openalex_fetcher.fetch.

Added after the DOI verifier surfaced 4 must_read papers that were
concept-relevant but slipped past the narrow ``concepts.id`` clause when
combined with ``search=``. When both ``concepts`` AND ``keywords`` are
supplied, ``fetch()`` now issues two queries (concepts-only + search-only)
and unions their results. When only one signal is present, the original
single-query path is preserved (and the existing fetcher tests prove it).

Run with:
    pytest tests/test_openalex_fetcher_fanout.py
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import openalex_fetcher  # noqa: E402


def _install_branching_get(monkeypatch, calls: list[dict]):
    """Stub requests.get that records params and routes by query shape.

    Query A (concepts-only, no search) → returns a paper that the narrow
    concept clause catches.
    Query B (search-only, no concept filter) → returns the verifier-class
    paper that concept-only matching would miss.
    """
    paper_a = {
        "id": "https://openalex.org/W_AAA",
        "doi": "https://doi.org/10.1/concept-hit",
        "title": "Caught by concept clause",
        "publication_year": 2024,
        "publication_date": "2024-05-15",
        "type": "article",
    }
    paper_b = {
        "id": "https://openalex.org/W_BBB",
        "doi": "https://doi.org/10.1038/s41598-024-61305-x",
        "title": "Caught only by search-keyword clause",
        "publication_year": 2024,
        "publication_date": "2024-05-10",
        "type": "article",
    }
    # An overlap paper appears in BOTH responses so we can prove dedup.
    paper_overlap = {
        "id": "https://openalex.org/W_OVR",
        "doi": "https://doi.org/10.1/overlap",
        "title": "Hit by both query A and query B",
        "publication_year": 2024,
        "publication_date": "2024-05-20",
        "type": "article",
    }

    class FakeResp:
        def __init__(self, results):
            self._results = results

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": self._results, "meta": {"next_cursor": None}}

    def fake_get(url, params=None, **kw):
        calls.append(dict(params or {}))
        flt = (params or {}).get("filter", "")
        if "search" in (params or {}):
            return FakeResp([paper_b, paper_overlap])
        if "concepts.id:" in flt:
            return FakeResp([paper_a, paper_overlap])
        return FakeResp([])

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)


def test_fan_out_dispatches_two_queries_and_unions_results(monkeypatch):
    calls: list[dict] = []
    _install_branching_get(monkeypatch, calls)
    out = openalex_fetcher.fetch(
        concepts=["C3020736514", "C3019025420"],
        keywords=["femoral stem", "stress shielding"],
        from_date="2024-05-01",
        to_date="2024-05-31",
        max_pages=1,
    )
    # Two queries were issued — one concept-only, one search-only.
    assert len(calls) == 2
    concept_call = next(c for c in calls if "search" not in c)
    search_call = next(c for c in calls if "search" in c)
    assert "concepts.id:" in concept_call["filter"]
    assert "concepts.id:" not in search_call["filter"]
    assert "femoral stem" in search_call["search"]

    # Union dedup by OpenAlex id: A returned [paper_a, overlap],
    # B returned [paper_b, overlap] → 3 unique papers.
    dois = [p["doi"] for p in out]
    assert "10.1/concept-hit" in dois
    assert "10.1038/s41598-024-61305-x" in dois  # verifier-class catch
    assert "10.1/overlap" in dois
    assert len(out) == 3  # overlap deduped


def test_single_signal_keeps_single_query_path(monkeypatch):
    """Concepts-only (or keywords-only) keeps the original behaviour: one
    query, no fan-out — so direction configs that intentionally provide
    just one signal aren't double-charged for API calls."""
    calls: list[dict] = []

    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [], "meta": {"next_cursor": None}}

    def fake_get(url, params=None, **kw):
        calls.append(dict(params or {}))
        return FakeResp()

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)

    openalex_fetcher.fetch(concepts=["C123"], keywords=[],
                           from_date="2024-05-01", to_date="2024-05-31",
                           max_pages=1)
    openalex_fetcher.fetch(concepts=[], keywords=["x"],
                           from_date="2024-05-01", to_date="2024-05-31",
                           max_pages=1)
    # 2 calls total (one per fetch invocation), not 4 — no fan-out fired.
    assert len(calls) == 2
