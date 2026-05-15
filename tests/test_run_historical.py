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


def test_dry_run_writes_no_bucket_files_but_records_counts_in_progress(
    monkeypatch, tmp_path
):
    """Dry-run does not produce per-month or per-bucket output files; the
    only artifact is _progress.json with per-month counts populated."""
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-01-15", to_date="2024-01-20",
           dry_run=True, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    # No legacy month-level files, no v2 bucket files, no discovery_log.
    assert list((tmp_path / "daily").glob("*.json")) == [] \
        if (tmp_path / "daily").exists() else True
    assert not (tmp_path / "discovery_log").exists() \
        or list((tmp_path / "discovery_log").glob("*.json")) == []
    assert not (output_dir / "2024-01_dryrun.json").exists()
    assert not (output_dir / "2024-01.json").exists()

    # Counts surface via the progress file.
    p = json.loads((output_dir / "_progress.json").read_text())
    assert p["months"]["2024-01"]["status"] == "complete"
    assert "counts" in p["months"]["2024-01"]
    assert p["months"]["2024-01"]["counts"]["scored"] == 0


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


def test_per_month_counts_schema_in_progress_file(monkeypatch, tmp_path):
    """Under the v2 schema, per-month tallies live inside the progress
    file's `months[<key>].counts` block (no separate month-output file)."""
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_make_paper("10.1/a", "AI bioprinting")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-01-01", to_date="2024-01-31",
           dry_run=True, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)
    p = json.loads((output_dir / "_progress.json").read_text())
    month = p["months"]["2024-01"]
    assert month["status"] == "complete"
    assert "counts" in month
    for k in ("fetched_total", "by_source", "after_dedup", "after_routing",
              "by_direction", "scored", "priority_counts"):
        assert k in month["counts"]
    assert month["counts"]["scored"] == 0
    assert month["counts"]["priority_counts"] is None


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


def test_routed_by_source_present_and_sums_to_after_routing(monkeypatch, tmp_path):
    # Two papers from arxiv that route, one from openalex that routes, one
    # from pubmed that does not route (civil engineering exclusion).
    _mock_three_fetchers(monkeypatch, {
        "arxiv": [
            _make_paper("10.1/ax1", "AI bioprinting bioink", source="arxiv"),
            _make_paper("10.1/ax2", "AI bioprinting closed loop control",
                        source="arxiv"),
        ],
        "openalex": [
            _make_paper("10.1/oa1", "AI bioprinting", source="openalex"),
        ],
        "pubmed": [
            _make_paper("10.1/pm1", "civil",
                        "bridge structural civil engineering analysis",
                        source="pubmed"),
        ],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda *a, **kw: ([], []))
    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-01-15", to_date="2024-01-15",
           dry_run=True, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)
    p = json.loads((output_dir / "_progress.json").read_text())
    counts = p["months"]["2024-01"]["counts"]
    assert "routed_by_source" in counts
    rbs = counts["routed_by_source"]
    assert rbs.get("arxiv", 0) == 2
    assert rbs.get("openalex", 0) == 1
    assert rbs.get("pubmed", 0) == 0 or "pubmed" not in rbs
    assert sum(rbs.values()) == counts["after_routing"]


def test_arxiv_historical_default_max_results_is_10000(monkeypatch):
    captured: dict = {}
    _install_arxiv_capture(monkeypatch, captured)

    # Capture max_results from arxiv.Search via _arxiv_fake_search
    original_search = _arxiv_fake_search

    def capturing_search(**kw):
        captured["max_results"] = kw.get("max_results")
        return original_search(**kw)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", capturing_search)

    arxiv_fetcher.fetch(["cs.LG"], from_date="2024-01-01", to_date="2024-01-31")
    assert captured["max_results"] == 10000


def test_arxiv_daily_default_max_results_is_2000(monkeypatch):
    captured: dict = {}
    _install_arxiv_capture(monkeypatch, captured)

    def capturing_search(**kw):
        captured["max_results"] = kw.get("max_results")
        return SimpleNamespace(**kw)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", capturing_search)

    arxiv_fetcher.fetch(["cs.LG"], days_back=1)
    assert captured["max_results"] == 2000


def test_arxiv_explicit_max_results_override_respected(monkeypatch):
    captured: dict = {}
    _install_arxiv_capture(monkeypatch, captured)

    def capturing_search(**kw):
        captured["max_results"] = kw.get("max_results")
        return SimpleNamespace(**kw)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", capturing_search)

    arxiv_fetcher.fetch(["cs.LG"], from_date="2024-01-01", to_date="2024-01-31",
                        max_results=500)
    assert captured["max_results"] == 500


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

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-01-01", to_date="2024-02-29",
           dry_run=True, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)
    p = json.loads((output_dir / "_progress.json").read_text())
    assert p["months"]["2024-01"]["counts"]["after_dedup"] == 1
    assert p["months"]["2024-02"]["counts"]["after_dedup"] == 0


# ============================================================================
# ADR-0015 Phase 4 Session 4.6: v2 bucket output
# ============================================================================

def _paper_with_date(doi: str, date: str, source: str = "openalex") -> dict:
    return {
        "source": source,
        "id": doi,
        "doi": doi,
        "arxiv_id": "",
        "title": "AI bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"],
        "first_author_affiliation": "",
        "corresponding_authors": [],
        "venue": "V",
        "year": int(date[:4]),
        "date": date,
        "url": f"https://doi.org/{doi}",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
    }


def test_historical_buckets_papers_into_per_publication_date_files(
    monkeypatch, tmp_path
):
    """5 papers across 3 distinct publication dates in 2024-03 -> 3 v2 files
    under data_root/daily/, each containing the right paper(s)."""
    papers = [
        _paper_with_date("10.1/a", "2024-03-05"),
        _paper_with_date("10.1/b", "2024-03-05"),
        _paper_with_date("10.1/c", "2024-03-15"),
        _paper_with_date("10.1/d", "2024-03-15"),
        _paper_with_date("10.1/e", "2024-03-25"),
    ]
    _mock_three_fetchers(monkeypatch, {"openalex": papers})
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (routed, []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-03-01", to_date="2024-03-31",
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    daily_dir = tmp_path / "daily"
    files = sorted(p.name for p in daily_dir.glob("*.json"))
    assert files == ["2024-03-05.json", "2024-03-15.json", "2024-03-25.json"]

    for date_str, expected_dois in [
        ("2024-03-05", {"10.1/a", "10.1/b"}),
        ("2024-03-15", {"10.1/c", "10.1/d"}),
        ("2024-03-25", {"10.1/e"}),
    ]:
        bucket = json.loads((daily_dir / f"{date_str}.json").read_text())
        assert bucket["schema_version"] == "v2"
        assert bucket["date"] == date_str
        assert {p["doi"] for p in bucket["papers"]} == expected_dois
        for p in bucket["papers"]:
            assert p["schema_version"] == "v2"
            assert p["scorer_version"] == "v3"
            assert p["first_seen_at"].endswith("Z")

    # Discovery log: one record per scored paper, all run_type=historical_backfill.
    log_dir = tmp_path / "discovery_log"
    log_files = list(log_dir.glob("*.json"))
    assert len(log_files) == 1
    records = json.loads(log_files[0].read_text())
    assert len(records) == 5
    assert all(r["run_type"] == "historical_backfill" for r in records)
    assert {r["doi_or_arxiv_id"] for r in records} == {
        f"doi:10.1/{c}" for c in "abcde"
    }


def test_historical_re_run_same_month_does_not_double_add_papers(
    monkeypatch, tmp_path
):
    """Re-running the same month with --no-resume re-fetches the papers, but
    the v2 bucket merge keeps first-seen-wins so bucket contents are stable
    and first_seen_at on existing papers is preserved."""
    papers = [
        _paper_with_date("10.1/x", "2024-03-10"),
        _paper_with_date("10.1/y", "2024-03-20"),
    ]
    _mock_three_fetchers(monkeypatch, {"openalex": papers})
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (routed, []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()

    # First run
    rh.run(from_date="2024-03-01", to_date="2024-03-31",
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)
    first_x = json.loads((tmp_path / "daily" / "2024-03-10.json").read_text())
    first_y = json.loads((tmp_path / "daily" / "2024-03-20.json").read_text())
    first_seen_x = first_x["papers"][0]["first_seen_at"]
    first_seen_y = first_y["papers"][0]["first_seen_at"]

    # Second run (no_resume=True forces re-fetch + re-score)
    rh.run(from_date="2024-03-01", to_date="2024-03-31",
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    second_x = json.loads((tmp_path / "daily" / "2024-03-10.json").read_text())
    second_y = json.loads((tmp_path / "daily" / "2024-03-20.json").read_text())

    assert len(second_x["papers"]) == 1
    assert len(second_y["papers"]) == 1
    assert second_x["papers"][0]["doi"] == "10.1/x"
    assert second_y["papers"][0]["doi"] == "10.1/y"
    # First-seen wins: original first_seen_at is preserved on the existing row.
    assert second_x["papers"][0]["first_seen_at"] == first_seen_x
    assert second_y["papers"][0]["first_seen_at"] == first_seen_y


def test_historical_scorer_version_parsed_from_active_prompt_file(
    monkeypatch, tmp_path
):
    """scorer_version on each v2 paper record reflects the live value of
    llm_scorer.ACTIVE_PROMPT_FILE, not a hardcoded 'v3'. Regression test for
    the v2_schema.scorer_version_from_active_prompt() wiring."""
    monkeypatch.setattr(rh.llm_scorer, "ACTIVE_PROMPT_FILE", "scorer_v9.txt")
    _mock_three_fetchers(monkeypatch, {
        "openalex": [_paper_with_date("10.1/z", "2024-04-10")],
    })
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (routed, []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date="2024-04-01", to_date="2024-04-30",
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    bucket = json.loads((tmp_path / "daily" / "2024-04-10.json").read_text())
    assert bucket["papers"][0]["scorer_version"] == "v9"
