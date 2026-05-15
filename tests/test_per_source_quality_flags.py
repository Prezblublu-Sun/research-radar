"""Tests for the per-source `<source>_returned_zero` quality flags added to
`pipeline.run_daily`.

Motivation: the 2026-05-15 daily run had fetched_total=540 (arxiv 534,
openalex 0, pubmed 6) but no quality_flag fired because OpenAlex's silent
zero return was masked by the other sources keeping aggregate metrics
healthy. These tests pin down the per-source detection so that regression
re-introduces a fail.

Run with:
    pytest tests/test_per_source_quality_flags.py
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import run_daily as rd  # noqa: E402


def _paper(doi: str, source: str = "arxiv") -> dict:
    return {
        "source": source,
        "id": doi,
        "doi": doi,
        "title": "bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"],
        "first_author_affiliation": "",
        "corresponding_authors": [],
        "venue": "V",
        "year": 2026,
        "date": "2026-05-15",
        "url": f"https://doi.org/{doi}",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
    }


@pytest.fixture
def isolated_run(monkeypatch, tmp_path):
    """Redirect all run_daily filesystem state into tmp_path and stub the
    side-effecting helpers (manifest write, changelog, HTML render). Tests
    populate fetchers and assert on the returned report."""
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

    # LLM scorer is mocked everywhere — never reach DeepSeek in tests.
    monkeypatch.setattr(
        rd.llm_scorer, "score_batch", lambda routed, dirs: (routed, [])
    )

    # Manifest / changelog / render side-effects are not under test here.
    monkeypatch.setattr(
        rd.mf, "build_manifest",
        lambda **kw: {
            "run_id": "test-run",
            "git_commit": "deadbeef",
            "config": {"scorer_prompt": "test-hash"},
        },
    )
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)

    return tmp_path


def _install_fetchers(monkeypatch, arxiv_papers, openalex_papers, pubmed_papers):
    monkeypatch.setattr(
        rd.arxiv_fetcher, "fetch", lambda *a, **kw: arxiv_papers
    )
    monkeypatch.setattr(
        rd.openalex_fetcher, "fetch", lambda *a, **kw: openalex_papers
    )
    monkeypatch.setattr(
        rd.pubmed_fetcher, "fetch", lambda *a, **kw: pubmed_papers
    )


# ============================================================================
# Per-source zero-return flag
# ============================================================================

def test_openalex_zero_returns_flag_even_when_aggregate_healthy(
    monkeypatch, isolated_run
):
    """Reproduces the 2026-05-15 incident: arxiv healthy, openalex silently
    returns 0, pubmed healthy. fetched_total stays high (>=50) so neither
    `fetched_zero` nor `low_fetch_count` fire, but the per-source flag must.
    """
    _install_fetchers(
        monkeypatch,
        arxiv_papers=[_paper(f"10.1/ax{i}", source="arxiv") for i in range(60)],
        openalex_papers=[],
        pubmed_papers=[_paper(f"10.1/pm{i}", source="pubmed") for i in range(6)],
    )

    report = rd.run(days_back=1, skip_zotero=True)

    flags = report["quality_flags"]
    assert "openalex_returned_zero" in flags
    assert "arxiv_returned_zero" not in flags
    assert "pubmed_returned_zero" not in flags
    # Aggregate flags should NOT have fired: total is well over 50.
    assert "fetched_zero" not in flags
    assert "low_fetch_count" not in flags


def test_no_per_source_flag_when_all_sources_return_papers(
    monkeypatch, isolated_run
):
    _install_fetchers(
        monkeypatch,
        arxiv_papers=[_paper("10.1/ax1", source="arxiv")],
        openalex_papers=[_paper("10.1/oa1", source="openalex")],
        pubmed_papers=[_paper("10.1/pm1", source="pubmed")],
    )

    report = rd.run(days_back=1, skip_zotero=True)

    flags = report["quality_flags"]
    assert "arxiv_returned_zero" not in flags
    assert "openalex_returned_zero" not in flags
    assert "pubmed_returned_zero" not in flags


def test_all_three_sources_zero_produces_all_three_flags(
    monkeypatch, isolated_run
):
    """All sources return empty — both the aggregate `fetched_zero` flag and
    every per-source flag must fire. fetched_total==0 triggers the abort
    path, so we additionally check run_status."""
    _install_fetchers(
        monkeypatch,
        arxiv_papers=[],
        openalex_papers=[],
        pubmed_papers=[],
    )

    report = rd.run(days_back=1, skip_zotero=True)

    flags = report["quality_flags"]
    assert "fetched_zero" in flags
    assert "arxiv_returned_zero" in flags
    assert "openalex_returned_zero" in flags
    assert "pubmed_returned_zero" in flags
    assert report["run_status"] == "failed"


def test_per_source_flag_format_is_self_describing(monkeypatch, isolated_run):
    """Flag values must follow the f"{source}_returned_zero" format so the
    flag is interpretable without consulting the manifest."""
    _install_fetchers(
        monkeypatch,
        arxiv_papers=[],
        openalex_papers=[_paper("10.1/oa1", source="openalex")],
        pubmed_papers=[_paper("10.1/pm1", source="pubmed")],
    )

    report = rd.run(days_back=1, skip_zotero=True)

    flags = report["quality_flags"]
    matching = [f for f in flags if f.endswith("_returned_zero")]
    assert matching == ["arxiv_returned_zero"]
