"""Tests for pipeline/run_historical.py and the additive date-range kwargs
on the three fetchers.

Run with:
    pytest tests/test_run_historical.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import run_historical as rh  # noqa: E402
from fetchers import arxiv_fetcher, openalex_fetcher, pubmed_fetcher  # noqa: E402


# ============================================================================
# Fetcher kwargs -- arxiv
# ============================================================================

def _arxiv_fake_search(**kw):
    return SimpleNamespace(**kw)


def _install_arxiv_capture(monkeypatch, captured: dict):
    """Replace arxiv.Client + arxiv.Search to record the issued query."""
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def results(self, search):
            captured["query"] = search.query
            return iter([])
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Client", FakeClient)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", _arxiv_fake_search)


def test_arxiv_query_contains_submitted_date_range_when_dates_set(monkeypatch):
    captured: dict = {}
    _install_arxiv_capture(monkeypatch, captured)
    arxiv_fetcher.fetch(["cs.LG"], from_date="2024-01-01", to_date="2024-01-31")
    q = captured["query"]
    assert "submittedDate:" in q
    assert "202401010000" in q
    assert "202401312359" in q
    assert "cat:cs.LG" in q


def test_arxiv_backcompat_days_back(monkeypatch):
    captured: dict = {}
    _install_arxiv_capture(monkeypatch, captured)
    arxiv_fetcher.fetch(["cs.LG"], days_back=7)
    assert "submittedDate:" not in captured["query"]
    assert captured["query"] == "cat:cs.LG"


# ============================================================================
# Fetcher kwargs -- openalex
# ============================================================================

def _install_openalex_pagination(monkeypatch, want_pages: int):
    """Always returns a next_cursor so pagination runs until max_pages."""
    counter = {"n": 0}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            counter["n"] += 1
            if counter["n"] < want_pages + 5:
                return {"results": [], "meta": {"next_cursor": "next"}}
            return {"results": [], "meta": {"next_cursor": None}}

    def fake_get(url, params=None, **kw):
        return FakeResp()

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)
    return counter


def test_openalex_filter_contains_to_publication_date(monkeypatch):
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self):
            return {"results": [], "meta": {"next_cursor": None}}

    def fake_get(url, params=None, **kw):
        captured["params"] = params
        return FakeResp()

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)
    openalex_fetcher.fetch(concepts=[], keywords=["x"],
                           from_date="2024-01-01", to_date="2024-01-31")
    flt = captured["params"]["filter"]
    assert "from_publication_date:2024-01-01" in flt
    assert "to_publication_date:2024-01-31" in flt


def test_openalex_historical_bumps_max_pages_to_40(monkeypatch):
    counter = _install_openalex_pagination(monkeypatch, want_pages=50)
    openalex_fetcher.fetch(concepts=[], keywords=["x"],
                           from_date="2024-01-01", to_date="2024-01-31")
    assert counter["n"] == 40


def test_openalex_daily_max_pages_stays_4(monkeypatch):
    counter = _install_openalex_pagination(monkeypatch, want_pages=50)
    openalex_fetcher.fetch(concepts=[], keywords=["x"], days_back=7)
    assert counter["n"] == 4


def test_openalex_explicit_max_pages_override_respected(monkeypatch):
    counter = _install_openalex_pagination(monkeypatch, want_pages=50)
    openalex_fetcher.fetch(concepts=[], keywords=["x"],
                           from_date="2024-01-01", to_date="2024-01-31",
                           max_pages=10)
    assert counter["n"] == 10


# ============================================================================
# Fetcher kwargs -- pubmed
# ============================================================================

def _install_pubmed_capture(monkeypatch, captured: dict):
    class FakeResp:
        def __init__(self, text=""): self.text = text
        def raise_for_status(self): pass
        def json(self):
            return {"esearchresult": {"idlist": []}}

    def fake_get(url, params=None, **kw):
        captured.setdefault("calls", []).append(params)
        return FakeResp()

    monkeypatch.setattr(pubmed_fetcher.requests, "get", fake_get)


def test_pubmed_query_uses_edat_range(monkeypatch):
    captured: dict = {}
    _install_pubmed_capture(monkeypatch, captured)
    pubmed_fetcher.fetch(["femoral stem"],
                         from_date="2024-01-01", to_date="2024-01-31")
    q = captured["calls"][0]["term"]
    assert "2024/01/01" in q
    assert "2024/01/31" in q
    assert "[EDAT]" in q


def test_pubmed_backcompat_uses_last_n_days(monkeypatch):
    captured: dict = {}
    _install_pubmed_capture(monkeypatch, captured)
    pubmed_fetcher.fetch(["x"], days_back=14)
    assert "last 14 days" in captured["calls"][0]["term"]


def test_pubmed_historical_retmax_bumps_to_500(monkeypatch):
    captured: dict = {}
    _install_pubmed_capture(monkeypatch, captured)
    pubmed_fetcher.fetch(["x"], from_date="2024-01-01", to_date="2024-01-31")
    assert captured["calls"][0]["retmax"] == 500


def test_pubmed_daily_retmax_stays_200(monkeypatch):
    captured: dict = {}
    _install_pubmed_capture(monkeypatch, captured)
    pubmed_fetcher.fetch(["x"], days_back=7)
    assert captured["calls"][0]["retmax"] == 200


# ============================================================================
# iterate_months
# ============================================================================

def test_iterate_months_single_partial_month():
    months = rh.iterate_months(dt.date(2024, 1, 5), dt.date(2024, 1, 20))
    assert months == [("2024-01", dt.date(2024, 1, 5), dt.date(2024, 1, 20))]


def test_iterate_months_partial_start_and_end():
    months = rh.iterate_months(dt.date(2024, 1, 15), dt.date(2024, 3, 15))
    assert len(months) == 3
    assert months[0] == ("2024-01", dt.date(2024, 1, 15), dt.date(2024, 1, 31))
    assert months[1] == ("2024-02", dt.date(2024, 2, 1), dt.date(2024, 2, 29))
    assert months[2] == ("2024-03", dt.date(2024, 3, 1), dt.date(2024, 3, 15))


def test_iterate_months_spans_year_boundary():
    months = rh.iterate_months(dt.date(2023, 12, 15), dt.date(2024, 2, 5))
    assert [m[0] for m in months] == ["2023-12", "2024-01", "2024-02"]


def test_iterate_months_inverted_range_raises():
    with pytest.raises(ValueError):
        rh.iterate_months(dt.date(2024, 2, 1), dt.date(2024, 1, 1))


# ============================================================================
# run_historical end-to-end with mocked fetchers
# ============================================================================

def _make_paper(doi: str, title: str, abstract: str | None = None,
                source: str = "openalex") -> dict:
    return {
        "source": source,
        "id": doi,
        "doi": doi,
        "title": title,
        "abstract": abstract if abstract is not None else f"{title} bioprinting bioink",
        "authors": ["A. Author"],
        "first_author_affiliation": "",
        "corresponding_authors": [],
        "venue": "V",
        "year": 2024,
        "date": "2024-01-15",
        "url": f"https://doi.org/{doi}",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
    }


def _mock_three_fetchers(monkeypatch, papers_per_source: dict):
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch",
                        lambda **kw: papers_per_source.get("arxiv", []))
    monkeypatch.setattr(rh.openalex_fetcher, "fetch",
                        lambda **kw: papers_per_source.get("openalex", []))
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch",
                        lambda **kw: papers_per_source.get("pubmed", []))


def test_dry_run_does_not_call_llm_scorer(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting bioink")],
    })
    called = {"score_batch": False}

    def fake_score(*a, **kw):
        called["score_batch"] = True
        return [], []
    monkeypatch.setattr(rh.llm_scorer, "score_batch", fake_score)

    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    assert called["score_batch"] is False


def test_dry_run_writes_dryrun_suffixed_filename(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-15", to_date="2024-01-20",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    assert (tmp_path / "2024-01_dryrun.json").exists()
    assert not (tmp_path / "2024-01.json").exists()


def test_resume_skips_complete_months(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))

    # First run completes both months
    rh.run(from_date="2024-01-01", to_date="2024-02-29",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    progress = json.loads((tmp_path / "_progress.json").read_text())
    assert progress["months"]["2024-01"]["status"] == "complete"
    assert progress["months"]["2024-02"]["status"] == "complete"

    # Second run: count fetcher invocations -- should be zero
    fetch_calls = {"n": 0}

    def counted(**kw):
        fetch_calls["n"] += 1
        return []
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", counted)
    monkeypatch.setattr(rh.openalex_fetcher, "fetch", counted)
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", counted)

    rh.run(from_date="2024-01-01", to_date="2024-02-29",
           dry_run=True, output_dir=tmp_path, no_resume=False)
    assert fetch_calls["n"] == 0


def test_mismatched_date_range_errors(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {})
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    with pytest.raises(SystemExit):
        rh.run(from_date="2024-02-01", to_date="2024-02-29",
               dry_run=True, output_dir=tmp_path, no_resume=False)


def test_mismatched_dry_run_errors(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {})
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    with pytest.raises(SystemExit, match="dry_run mismatch"):
        rh.run(from_date="2024-01-01", to_date="2024-01-31",
               dry_run=False, output_dir=tmp_path, no_resume=False)


def test_no_resume_flag_starts_fresh(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)

    # Re-run with --no-resume: should re-fetch everything (no skip)
    fetch_calls = {"n": 0}

    def counted(**kw):
        fetch_calls["n"] += 1
        return []
    monkeypatch.setattr(rh.openalex_fetcher, "fetch", counted)
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", lambda **kw: [])

    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    assert fetch_calls["n"] >= 1


def test_routing_filters_before_scoring(monkeypatch, tmp_path):
    # Real direction_router will route the bioprinting paper, drop the
    # civil-engineering paper via the exclusion list.
    _mock_three_fetchers(monkeypatch, {
        "openalex": [
            _make_paper("10.1/match", "AI bioprinting",
                        "AI bioprinting bioink optimization study"),
            _make_paper("10.1/skip", "civil",
                        "bridge structural civil engineering analysis"),
        ],
    })
    seen_routed: list[dict] = []

    def fake_score(routed, dirs):
        seen_routed.extend(routed)
        return [], []
    monkeypatch.setattr(rh.llm_scorer, "score_batch", fake_score)

    rh.run(from_date="2024-01-15", to_date="2024-01-15",
           dry_run=False, output_dir=tmp_path, no_resume=True)
    assert len(seen_routed) == 1
    assert seen_routed[0]["doi"] == "10.1/match"


def test_zotero_sync_module_not_imported():
    assert not hasattr(rh, "zotero_sync"), \
        "run_historical must not import zotero_sync"
    mod_src = pathlib.Path(rh.__file__).read_text(encoding="utf-8")
    assert "import zotero_sync" not in mod_src
    assert "from pipeline.zotero_sync" not in mod_src


def test_per_month_output_schema(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    out = json.loads((tmp_path / "2024-01_dryrun.json").read_text())
    for k in ("schema_version", "month", "window", "dry_run",
              "completed_at", "counts"):
        assert k in out
    for k in ("fetched_total", "by_source", "after_dedup", "after_routing",
              "by_direction", "scored", "priority_counts"):
        assert k in out["counts"]
    assert out["counts"]["scored"] == 0
    assert out["counts"]["priority_counts"] is None
    assert "papers" not in out  # papers list suppressed in dry-run


def test_progress_file_schema(monkeypatch, tmp_path):
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    rh.run(from_date="2024-01-15", to_date="2024-01-15",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    p = json.loads((tmp_path / "_progress.json").read_text())
    for k in ("schema_version", "tool", "date_range", "dry_run",
              "started_at", "last_updated_at", "months", "dois_seen"):
        assert k in p
    assert p["tool"] == "run_historical"
    assert p["dry_run"] is True


def test_dois_seen_dedups_across_months(monkeypatch, tmp_path):
    # Same DOI appears in both January and February fetches.
    def fake_fetch(**kw):
        f = kw.get("from_date", "")
        if f.startswith("2024-01"):
            return [_make_paper("10.1/shared", "AI bioprinting")]
        if f.startswith("2024-02"):
            return [_make_paper("10.1/shared", "AI bioprinting")]
        return []

    monkeypatch.setattr(rh.openalex_fetcher, "fetch", fake_fetch)
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))

    rh.run(from_date="2024-01-01", to_date="2024-02-29",
           dry_run=True, output_dir=tmp_path, no_resume=True)
    jan = json.loads((tmp_path / "2024-01_dryrun.json").read_text())
    feb = json.loads((tmp_path / "2024-02_dryrun.json").read_text())
    assert jan["counts"]["after_dedup"] == 1
    assert feb["counts"]["after_dedup"] == 0
