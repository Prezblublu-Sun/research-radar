"""ADR-0030 §10: a backfill that hits the OpenAlex daily budget parks the
month, keeps every completed month, reports `stopped_early`, and resumes on
the next run of the same range.

Run with:
    pytest tests/test_backfill_rate_limit.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import openalex_fetcher  # noqa: E402
from pipeline import run_historical as rh  # noqa: E402


def _paper(doi: str, date: str) -> dict:
    return {
        "source": "openalex", "id": doi, "doi": doi, "arxiv_id": "",
        "title": "AI bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"], "first_author_affiliation": "",
        "corresponding_authors": [], "venue": "V", "year": int(date[:4]),
        "date": date, "url": f"https://example.org/{doi}",
        "cited_by_count": 0, "concepts": [], "categories": [],
    }


@pytest.fixture
def quiet_pipeline(monkeypatch):
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (list(routed), []))
    monkeypatch.setattr(rh.doi_aliases, "resolve_zenodo",
                        lambda dois, path, **kw: ({}, {"looked_up": 0, "resolved": 0,
                                                       "failed": 0, "skipped_cap": 0}))


def _openalex_by_window(monkeypatch, behaviour: dict):
    """behaviour: window_from -> list[paper] | Exception instance."""
    calls: list[str] = []

    def fetch(concepts, keywords, from_date=None, to_date=None, **kw):
        calls.append(from_date)
        result = behaviour[from_date]
        if isinstance(result, Exception):
            raise result
        return list(result)

    monkeypatch.setattr(rh.openalex_fetcher, "fetch", fetch)
    return calls


def test_budget_exhaustion_parks_month_and_keeps_completed_ones(monkeypatch, tmp_path, quiet_pipeline):
    calls = _openalex_by_window(monkeypatch, {
        "2025-01-01": [_paper("10.1/jan", "2025-01-10")],
        "2025-02-01": openalex_fetcher.OpenAlexRateLimitError(
            "OpenAlex rate limited the request (retry_after=31731s)"),
        "2025-03-01": [_paper("10.1/mar", "2025-03-10")],
    })
    out = tmp_path / "runs" / "2025-01-01_2025-03-31"
    out.mkdir(parents=True)

    report = rh.run(from_date="2025-01-01", to_date="2025-03-31", dry_run=False,
                    output_dir=out, data_root=tmp_path, no_resume=True,
                    sources={"openalex"})

    assert report["months_completed"] == 1
    assert report["stopped_early"]["month"] == "2025-02"
    assert calls == ["2025-01-01", "2025-02-01"]  # March never attempted
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    assert progress["months"]["2025-01"]["status"] == "complete"
    assert progress["months"]["2025-02"]["status"] == "pending"
    assert "retry_after" in progress["months"]["2025-02"]["deferred_reason"]
    assert progress["months"]["2025-03"]["status"] == "pending"
    assert progress["stopped_early"]["month"] == "2025-02"
    # January's papers are on disk, ready to be committed.
    bucket = json.loads((tmp_path / "daily" / "2025-01-10.json").read_text(encoding="utf-8"))
    assert [p["doi"] for p in bucket["papers"]] == ["10.1/jan"]


def test_rerun_of_same_range_resumes_at_the_parked_month(monkeypatch, tmp_path, quiet_pipeline):
    out = tmp_path / "runs" / "2025-01-01_2025-03-31"
    out.mkdir(parents=True)
    _openalex_by_window(monkeypatch, {
        "2025-01-01": [_paper("10.1/jan", "2025-01-10")],
        "2025-02-01": openalex_fetcher.OpenAlexRateLimitError("budget"),
        "2025-03-01": [],
    })
    rh.run(from_date="2025-01-01", to_date="2025-03-31", dry_run=False,
           output_dir=out, data_root=tmp_path, no_resume=True, sources={"openalex"})

    # Next day: the budget is back.
    calls = _openalex_by_window(monkeypatch, {
        "2025-01-01": [_paper("10.1/jan-again", "2025-01-11")],
        "2025-02-01": [_paper("10.1/feb", "2025-02-10")],
        "2025-03-01": [_paper("10.1/mar", "2025-03-10")],
    })
    report = rh.run(from_date="2025-01-01", to_date="2025-03-31", dry_run=False,
                    output_dir=out, data_root=tmp_path, no_resume=False,
                    sources={"openalex"})

    assert calls == ["2025-02-01", "2025-03-01"]  # January skipped, not refetched
    assert report["months_completed"] == 3
    assert report["stopped_early"] is None
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    assert all(m["status"] == "complete" for m in progress["months"].values())
    assert (tmp_path / "daily" / "2025-02-10.json").exists()
    assert not (tmp_path / "daily" / "2025-01-11.json").exists()


def test_other_openalex_errors_still_fail_loudly(monkeypatch, tmp_path, quiet_pipeline):
    _openalex_by_window(monkeypatch, {
        "2025-01-01": RuntimeError("HTTP 500"),
    })
    out = tmp_path / "runs" / "r"
    out.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="openalex fetch failed"):
        rh.run(from_date="2025-01-01", to_date="2025-01-31", dry_run=False,
               output_dir=out, data_root=tmp_path, no_resume=True, sources={"openalex"})
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    assert progress["months"]["2025-01"]["status"] == "failed"


def test_cli_exits_zero_after_a_parked_month(monkeypatch, tmp_path, quiet_pipeline, capsys):
    _openalex_by_window(monkeypatch, {
        "2025-01-01": openalex_fetcher.OpenAlexRateLimitError("budget"),
    })
    out = tmp_path / "runs" / "r"
    out.mkdir(parents=True)
    code = rh.main(["--from-date", "2025-01-01", "--to-date", "2025-01-31",
                    "--sources", "openalex", "--output-dir", str(out),
                    "--data-root", str(tmp_path), "--no-resume"])
    captured = capsys.readouterr().out
    assert code == 0
    assert "::warning::Budget exhausted" in captured
    assert '"stopped_early"' in captured
