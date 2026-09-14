"""ADR-0030: daily fetch windows, page caps, truncation reporting, and the
ordered dedup state.

Run with:
    pytest tests/test_daily_source_windows.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import arxiv_fetcher, openalex_fetcher  # noqa: E402
from pipeline import aggregator  # noqa: E402
from pipeline import run_daily as rd  # noqa: E402


# ============================================================================
# arXiv: max_results scales with the lookback
# ============================================================================

def _capture_arxiv_search(monkeypatch, captured: dict):
    class FakeClient:
        def __init__(self, *a, **kw): pass
        def results(self, search):
            return iter([])

    def fake_search(**kw):
        captured.update(kw)
        return SimpleNamespace(**kw)

    monkeypatch.setattr(arxiv_fetcher.arxiv, "Client", FakeClient)
    monkeypatch.setattr(arxiv_fetcher.arxiv, "Search", fake_search)


def test_arxiv_daily_max_results_scales_with_lookback(monkeypatch):
    captured: dict = {}
    _capture_arxiv_search(monkeypatch, captured)
    arxiv_fetcher.fetch(["cs.LG"], days_back=5)
    assert captured["max_results"] == 10000


def test_arxiv_daily_one_day_keeps_legacy_cap(monkeypatch):
    captured: dict = {}
    _capture_arxiv_search(monkeypatch, captured)
    arxiv_fetcher.fetch(["cs.LG"], days_back=1)
    assert captured["max_results"] == 2000


# ============================================================================
# OpenAlex: newest-first sort, page cap, truncation stats
# ============================================================================

def _install_openalex_pages(monkeypatch, pages_available: int, calls: list):
    """Serve `pages_available` pages, each with one work and a next_cursor
    on every page except the last."""
    counter = {"n": 0}

    class FakeResp:
        def raise_for_status(self): pass

        def json(self):
            counter["n"] += 1
            work = {
                "id": f"https://openalex.org/W{counter['n']}",
                "doi": f"https://doi.org/10.1/w{counter['n']}",
                "title": "t", "publication_year": 2026,
                "publication_date": "2026-09-01", "type": "article",
            }
            more = counter["n"] < pages_available
            return {"results": [work],
                    "meta": {"next_cursor": "next" if more else None}}

    def fake_get(url, params=None, **kw):
        calls.append(dict(params or {}))
        return FakeResp()

    monkeypatch.setattr(openalex_fetcher.requests, "get", fake_get)


def test_openalex_daily_sorts_newest_first_and_uses_daily_cap(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=1, calls=calls)
    stats: dict = {}
    openalex_fetcher.fetch(concepts=[], keywords=["x"], days_back=14,
                           stats=stats)
    assert calls[0]["sort"] == openalex_fetcher.DAILY_SORT
    assert stats["max_pages"] == openalex_fetcher.DAILY_MAX_PAGES
    assert openalex_fetcher.DAILY_MAX_PAGES >= 40  # window measured at ~3.9k works


def test_openalex_historical_mode_does_not_sort(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=1, calls=calls)
    openalex_fetcher.fetch(concepts=[], keywords=["x"],
                           from_date="2024-01-01", to_date="2024-01-31")
    assert "sort" not in calls[0]


def test_openalex_reports_truncation_when_cursor_outlives_cap(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=10, calls=calls)
    stats: dict = {}
    out = openalex_fetcher.fetch(concepts=[], keywords=["x"], days_back=14,
                                 max_pages=3, stats=stats)
    assert len(out) == 3
    assert stats["truncated"] is True
    assert stats["queries"][0] == {"query": "single", "pages": 3,
                                   "results": 3, "truncated": True}


def test_openalex_reports_no_truncation_when_window_exhausted(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=2, calls=calls)
    stats: dict = {}
    out = openalex_fetcher.fetch(concepts=[], keywords=["x"], days_back=14,
                                 max_pages=5, stats=stats)
    assert len(out) == 2
    assert stats["truncated"] is False
    assert stats["queries"][0]["pages"] == 2


def test_openalex_fan_out_reports_both_queries(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=1, calls=calls)
    stats: dict = {}
    openalex_fetcher.fetch(concepts=["C1"], keywords=["x"], days_back=14,
                           stats=stats)
    assert [q["query"] for q in stats["queries"]] == ["concepts", "search"]
    assert stats["truncated"] is False


def test_openalex_stats_optional_keeps_legacy_return(monkeypatch):
    calls: list[dict] = []
    _install_openalex_pages(monkeypatch, pages_available=1, calls=calls)
    out = openalex_fetcher.fetch(concepts=[], keywords=["x"], days_back=14)
    assert isinstance(out, list) and len(out) == 1


# ============================================================================
# run_daily: effective lookbacks and the openalex_truncated flag
# ============================================================================

def _paper(doi: str, source: str = "arxiv") -> dict:
    return {
        "source": source, "id": doi, "doi": doi,
        "title": "bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"], "first_author_affiliation": "",
        "corresponding_authors": [], "venue": "V", "year": 2026,
        "date": "2026-09-01", "url": f"https://doi.org/{doi}",
        "cited_by_count": 0, "concepts": [], "categories": [],
    }


@pytest.fixture
def isolated_run(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    (data_dir / "daily").mkdir(parents=True)
    docs_dir.mkdir()
    monkeypatch.setattr(rd, "DATA_DIR", data_dir)
    monkeypatch.setattr(rd, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(rd, "SEEN_STATE", data_dir / "seen_dois.json")
    monkeypatch.setattr(rd, "MANIFESTS_DIR", data_dir / "manifests")
    monkeypatch.setattr(rd, "SNAPSHOTS_DIR", data_dir / "config_snapshots")
    monkeypatch.setattr(rd, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(rd.llm_scorer, "score_batch",
                        lambda routed, dirs: (routed, []))
    captured: dict = {}

    def fake_build_manifest(**kw):
        captured.update(kw)
        return {"run_id": "test-run", "git_commit": "deadbeef",
                "config": {"scorer_prompt": "test-hash"}}

    monkeypatch.setattr(rd.mf, "build_manifest", fake_build_manifest)
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)
    return captured


def test_effective_lookbacks_are_recorded(monkeypatch, isolated_run):
    seen: dict = {}

    def fake_arxiv(cats, days_back=1, **kw):
        seen["arxiv"] = days_back
        return [_paper("10.1/ax")]

    def fake_openalex(concepts, keywords, days_back=1, stats=None, **kw):
        seen["openalex"] = days_back
        return [_paper("10.1/oa", source="openalex")]

    def fake_pubmed(terms, days_back=1, **kw):
        seen["pubmed"] = days_back
        return [_paper("10.1/pm", source="pubmed")]

    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", fake_arxiv)
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", fake_openalex)
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", fake_pubmed)

    rd.run(days_back=2, skip_zotero=True)

    assert seen["arxiv"] == rd.ARXIV_MIN_LOOKBACK_DAYS
    assert seen["openalex"] == rd.OPENALEX_MIN_LOOKBACK_DAYS
    assert seen["pubmed"] == 2
    used = isolated_run["sources_used"]
    assert used["arxiv"]["days_back"] == rd.ARXIV_MIN_LOOKBACK_DAYS
    assert used["arxiv"]["requested_days_back"] == 2
    assert used["openalex"]["days_back"] == rd.OPENALEX_MIN_LOOKBACK_DAYS


def test_arxiv_floor_covers_the_announcement_lag():
    # Friday-after-cutoff submissions are announced Monday 20:00 ET and are
    # first visible to the Tuesday run: Tue-4 = Fri must be inside the window.
    assert rd.ARXIV_MIN_LOOKBACK_DAYS >= 4


def test_openalex_truncation_sets_quality_flag(monkeypatch, isolated_run):
    def fake_openalex(concepts, keywords, days_back=1, stats=None, **kw):
        if stats is not None:
            stats.update({"truncated": True, "max_pages": 60,
                          "queries": [{"query": "search", "pages": 60,
                                       "results": 6000, "truncated": True}]})
        return [_paper("10.1/oa", source="openalex")]

    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [_paper("10.1/ax")])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", fake_openalex)
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: [])

    report = rd.run(days_back=2, skip_zotero=True)

    assert "openalex_truncated" in report["quality_flags"]
    assert report["source_status"]["openalex"]["fetch_stats"]["truncated"] is True
    assert report["run_status"] == "success"


def test_no_truncation_flag_when_window_exhausted(monkeypatch, isolated_run):
    def fake_openalex(concepts, keywords, days_back=1, stats=None, **kw):
        if stats is not None:
            stats.update({"truncated": False, "max_pages": 60, "queries": []})
        return [_paper("10.1/oa", source="openalex")]

    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [_paper("10.1/ax")])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", fake_openalex)
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: [])

    report = rd.run(days_back=2, skip_zotero=True)

    assert "openalex_truncated" not in report["quality_flags"]


# ============================================================================
# aggregator.save_state: ordered, deterministic, never forgets on --force
# ============================================================================

def test_save_state_keeps_first_seen_order_and_appends(tmp_path):
    path = tmp_path / "seen.json"
    aggregator.save_state({"doi:b", "doi:a"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["keys"] == ["doi:a", "doi:b"]

    aggregator.save_state({"doi:c", "doi:a"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["keys"] == ["doi:a", "doi:b", "doi:c"]


def test_save_state_truncates_oldest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(aggregator, "MAX_SEEN_KEYS", 3)
    path = tmp_path / "seen.json"
    aggregator.save_state({"doi:1"}, path)
    aggregator.save_state({"doi:2"}, path)
    aggregator.save_state({"doi:3"}, path)
    aggregator.save_state({"doi:4"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["keys"] == ["doi:2", "doi:3", "doi:4"]


def test_save_state_survives_corrupt_file(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{not json", encoding="utf-8")
    aggregator.save_state({"doi:x"}, path)
    assert json.loads(path.read_text(encoding="utf-8"))["keys"] == ["doi:x"]


def test_force_run_does_not_wipe_history(tmp_path):
    path = tmp_path / "seen.json"
    aggregator.save_state({"doi:old"}, path)
    # A --force run bypasses the state on read and returns only today's keys.
    papers, keys = aggregator.aggregate([[{"source": "arxiv", "id": "x", "doi": "10.1/new"}]],
                                        path, force=True)
    assert keys == {"doi:10.1/new"}
    aggregator.save_state(keys, path)
    assert json.loads(path.read_text(encoding="utf-8"))["keys"] == ["doi:old", "doi:10.1/new"]
