"""Tests for ADR-0015 v2 producer behaviour in pipeline/run_daily.py.

Covers the per-publication-date bucketing, first-seen-wins merge against
existing v2 files on disk, atomic write via .tmp + rename, and the v2-or-v1
loader added to render/build_pages.py.

All tests use tmp_path and never hit real fetchers, LLM, or filesystem
state outside the test root.

Run with:
    pytest tests/test_run_daily_v2.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import run_daily as rd  # noqa: E402
from render import build_pages  # noqa: E402


# ============================================================================
# Fixtures
# ============================================================================

def _paper(doi: str, *, source: str = "arxiv", date: str = "2026-05-15",
           arxiv_id: str = "") -> dict:
    return {
        "source": source,
        "id": doi or arxiv_id,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": "bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"],
        "first_author_affiliation": "",
        "corresponding_authors": [],
        "venue": "V",
        "year": int(date[:4]) if date else 2026,
        "date": date,
        "url": f"https://doi.org/{doi}" if doi else "",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
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

    monkeypatch.setattr(
        rd.llm_scorer, "score_batch", lambda routed, dirs: (routed, [])
    )
    monkeypatch.setattr(
        rd.mf, "build_manifest",
        lambda **kw: {
            "run_id": "test-run", "git_commit": "deadbeef",
            "config": {"scorer_prompt": "test-hash"},
        },
    )
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)
    return tmp_path


def _install_fetchers(monkeypatch, *, arxiv=(), openalex=(), pubmed=()):
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: list(arxiv))
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: list(openalex))
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: list(pubmed))


def _read_v2(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# (i) Papers spanning multiple publication dates -> one file per date
# ============================================================================

def test_run_buckets_papers_into_separate_publication_date_files(
    monkeypatch, isolated_run
):
    _install_fetchers(monkeypatch, arxiv=[
        _paper("10.1/a", date="2024-03-15"),
        _paper("10.1/b", date="2024-04-20"),
        _paper("10.1/c", date="2024-05-25"),
    ])
    report = rd.run(days_back=1, skip_zotero=True)
    daily_dir = isolated_run / "data" / "daily"

    assert (daily_dir / "2024-03-15.json").exists()
    assert (daily_dir / "2024-04-20.json").exists()
    assert (daily_dir / "2024-05-25.json").exists()
    assert not (daily_dir / "2026-05-15.json").exists()  # run date != pub date

    for date, doi in [("2024-03-15", "10.1/a"),
                      ("2024-04-20", "10.1/b"),
                      ("2024-05-25", "10.1/c")]:
        f = _read_v2(daily_dir / f"{date}.json")
        assert f["schema_version"] == "v2"
        assert f["date"] == date
        assert len(f["papers"]) == 1
        assert f["papers"][0]["doi"] == doi
        assert f["papers"][0]["scorer_version"] == "v3"
        assert f["papers"][0]["first_seen_at"].endswith("Z")

    touched = report["counts"]["touched_dates"]
    assert set(touched) == {"2024-03-15", "2024-04-20", "2024-05-25"}
    assert all(n == 1 for n in touched.values())


# ============================================================================
# (ii) Same DOI re-observed: existing first_seen_at is preserved
# ============================================================================

def test_merge_preserves_existing_first_seen_at_for_duplicate_doi(
    monkeypatch, isolated_run
):
    daily_dir = isolated_run / "data" / "daily"
    pre_existing = {
        "schema_version": "v2",
        "date": "2024-03-15",
        "date_precision": "day",
        "papers": [{
            "source": "openalex",
            "doi": "10.1/shared",
            "arxiv_id": "",
            "title": "ORIGINAL title",
            "date": "2024-03-15",
            "schema_version": "v2",
            "date_precision": "day",
            "scorer_version": "v1",
            "first_seen_at": "2024-04-01T00:00:00Z",
            "direction": "ai_bioprinting",
            "direction_name": "AI bioprinting",
        }],
        "counts": {},
    }
    (daily_dir / "2024-03-15.json").write_text(
        json.dumps(pre_existing, ensure_ascii=False, indent=2)
    )

    _install_fetchers(monkeypatch, arxiv=[
        _paper("10.1/shared", date="2024-03-15"),
    ])
    rd.run(days_back=1, skip_zotero=True)

    f = _read_v2(daily_dir / "2024-03-15.json")
    assert len(f["papers"]) == 1
    p = f["papers"][0]
    # First-seen wins on every front: title, scorer_version, first_seen_at.
    assert p["title"] == "ORIGINAL title"
    assert p["scorer_version"] == "v1"
    assert p["first_seen_at"] == "2024-04-01T00:00:00Z"


def test_merge_adds_new_paper_alongside_existing_in_same_bucket(
    monkeypatch, isolated_run
):
    daily_dir = isolated_run / "data" / "daily"
    pre_existing = {
        "schema_version": "v2",
        "date": "2024-03-15",
        "date_precision": "day",
        "papers": [{
            "source": "openalex",
            "doi": "10.1/old",
            "arxiv_id": "",
            "title": "Old paper",
            "date": "2024-03-15",
            "schema_version": "v2",
            "date_precision": "day",
            "scorer_version": "v1",
            "first_seen_at": "2024-04-01T00:00:00Z",
        }],
        "counts": {},
    }
    (daily_dir / "2024-03-15.json").write_text(json.dumps(pre_existing))

    _install_fetchers(monkeypatch, arxiv=[
        _paper("10.1/new", date="2024-03-15"),
    ])
    rd.run(days_back=1, skip_zotero=True)

    f = _read_v2(daily_dir / "2024-03-15.json")
    assert len(f["papers"]) == 2
    dois = sorted(p["doi"] for p in f["papers"])
    assert dois == ["10.1/new", "10.1/old"]


# ============================================================================
# (iii) Atomic write: no stale .tmp files left after run
# ============================================================================

def test_no_tmp_files_remain_after_successful_run(monkeypatch, isolated_run):
    _install_fetchers(monkeypatch, arxiv=[
        _paper("10.1/a", date="2024-03-15"),
        _paper("10.1/b", date="2024-04-20"),
    ])
    rd.run(days_back=1, skip_zotero=True)
    daily_dir = isolated_run / "data" / "daily"
    log_dir = isolated_run / "data" / "discovery_log"

    leftover_tmp = list(daily_dir.glob("*.tmp")) + list(log_dir.glob("*.tmp"))
    assert leftover_tmp == [], f"stale temp files: {leftover_tmp}"

    final = sorted(p.name for p in daily_dir.glob("*.json"))
    assert final == ["2024-03-15.json", "2024-04-20.json"]


# ============================================================================
# Bonus: discovery log records every observation, even duplicates
# ============================================================================

def test_discovery_log_records_every_scored_paper(monkeypatch, isolated_run):
    _install_fetchers(monkeypatch, arxiv=[
        _paper("10.1/a", date="2024-03-15"),
        _paper("10.1/b", date="2024-04-20"),
    ])
    rd.run(days_back=1, skip_zotero=True)

    today = rd.dt.date.today().isoformat()
    log = json.loads(
        (isolated_run / "data" / "discovery_log" / f"{today}.json").read_text()
    )
    assert isinstance(log, list)
    assert len(log) == 2
    assert {r["doi_or_arxiv_id"] for r in log} == {"doi:10.1/a", "doi:10.1/b"}
    assert all(r["run_type"] == "daily" for r in log)


# ============================================================================
# Bonus: fetched_total == 0 path still produces a SKIPPED marker, no buckets
# ============================================================================

def test_fetched_zero_writes_skip_marker_and_no_bucket_files(
    monkeypatch, isolated_run
):
    _install_fetchers(monkeypatch)  # all three fetchers return []
    report = rd.run(days_back=1, skip_zotero=True)
    daily_dir = isolated_run / "data" / "daily"

    assert report["run_status"] == "failed"
    assert "fetched_zero" in report["quality_flags"]
    today = rd.dt.date.today().isoformat()
    assert (daily_dir / f"{today}.SKIPPED.json").exists()
    # No bucket files (filename pattern YYYY-MM-DD.json without suffix).
    import re
    buckets = [p for p in daily_dir.glob("20*.json")
               if re.match(r"^\d{4}-\d{2}-\d{2}\.json$", p.name)]
    assert buckets == []


# ============================================================================
# build_pages helper: _load_papers_v2_or_v1 tolerates both shapes
# ============================================================================

def test_load_papers_v2_or_v1_unwraps_v2_dict(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({
        "schema_version": "v2",
        "date": "2024-03-15",
        "date_precision": "day",
        "papers": [{"doi": "10.1/x"}],
        "counts": {"fetched_total": 1},
    }))
    papers, meta = build_pages._load_papers_v2_or_v1(p)
    assert papers == [{"doi": "10.1/x"}]
    assert meta["schema_version"] == "v2"
    assert meta["date"] == "2024-03-15"
    assert "papers" not in meta


def test_load_papers_v2_or_v1_accepts_v1_list(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps([{"doi": "10.1/x"}, {"doi": "10.1/y"}]))
    papers, meta = build_pages._load_papers_v2_or_v1(p)
    assert len(papers) == 2
    assert meta == {}


def test_load_papers_v2_or_v1_returns_empty_on_garbage(tmp_path):
    p = tmp_path / "f.json"
    p.write_text("not json at all")
    papers, meta = build_pages._load_papers_v2_or_v1(p)
    assert papers == []
    assert meta == {}
