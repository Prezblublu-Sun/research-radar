"""ADR-0030 §11: a DeepSeek "Insufficient Balance" (HTTP 402) must stop the
run's API calls, be reported honestly, park backfill months, and never crash
the site build through odd scorer output.

Run with:
    pytest tests/test_scorer_budget.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import llm_scorer  # noqa: E402  (conftest sets OPENAI_API_KEY)
from pipeline import run_daily as rd  # noqa: E402
from pipeline import run_historical as rh  # noqa: E402
from render import build_pages  # noqa: E402


class _InsufficientBalance(Exception):
    status_code = 402

    def __str__(self):
        return ("Error code: 402 - {'error': {'message': 'Insufficient Balance', "
                "'type': 'unknown_error'}}")


_GOOD = json.dumps({"priority": "High", "relevance_to_user": "yes", "tags": ["t"],
                    "summary_zh": {"motivation": "动机"}})
_DIRECTIONS = {"hip_implant": {"llm_prompt_focus": "focus"}}


def _paper(doi: str, date: str = "2026-09-16") -> dict:
    return {
        "source": "openalex", "id": doi, "doi": doi, "arxiv_id": "",
        "title": "AI bioprinting bioink study",
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"], "first_author_affiliation": "",
        "corresponding_authors": [], "venue": "V", "year": int(date[:4]),
        "date": date, "url": f"https://example.org/{doi}", "cited_by_count": 0,
        "concepts": [], "categories": [], "direction": "hip_implant",
        "direction_name": "Hip Implant",
    }


def _fake_resp(content):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                           model="test-model")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    llm_scorer.reset_budget_state()
    monkeypatch.setattr(llm_scorer, "_log_scoring_failure", lambda *a, **k: None)
    monkeypatch.setattr(llm_scorer, "_LLM_CONCURRENCY", 1)  # deterministic order
    yield
    llm_scorer.reset_budget_state()


def _install_create(monkeypatch, responses):
    calls: list = []
    it = iter(responses)

    def fake_create(**kwargs):
        calls.append(kwargs)
        item = next(it)
        if isinstance(item, BaseException):
            raise item
        return _fake_resp(item)

    monkeypatch.setattr(llm_scorer.client.chat.completions, "create", fake_create)
    return calls


# ---------------------------------------------------------------------------
# llm_scorer
# ---------------------------------------------------------------------------

def test_first_402_stops_all_further_api_calls(monkeypatch):
    calls = _install_create(monkeypatch, [_GOOD, _InsufficientBalance(), _GOOD, _GOOD])
    papers = [_paper("10.1/a"), _paper("10.1/b"), _paper("10.1/c"), _paper("10.1/d")]

    out, _ = llm_scorer.score_batch(papers, _DIRECTIONS)

    assert len(calls) == 2  # one success, one 402, then nothing
    assert out[0]["llm"]["priority"] == "High"
    assert out[1]["llm"]["scorer_failed"] is True
    assert "402" in out[1]["llm"]["scorer_failed_reason"]
    assert out[1]["llm"]["scorer_failed_attempts"] == llm_scorer._MAX_SCORE_ATTEMPTS
    for p in out[2:]:
        assert p["llm"]["scorer_failed"] is True
        assert p["llm"]["scorer_failed_reason"].startswith("skipped:")
        assert p["llm"]["scorer_failed_attempts"] == 0
    assert "Insufficient Balance" in llm_scorer.budget_exhausted()


def test_402_is_not_retried(monkeypatch):
    calls = _install_create(monkeypatch, [_InsufficientBalance(), _GOOD, _GOOD])
    llm_scorer.score_batch([_paper("10.1/a")], _DIRECTIONS)
    assert len(calls) == 1


def test_ordinary_errors_keep_the_retry_contract(monkeypatch):
    calls = _install_create(monkeypatch, [ValueError("bad json"), _GOOD])
    out, _ = llm_scorer.score_batch([_paper("10.1/a")], _DIRECTIONS)
    assert len(calls) == 2
    assert out[0]["llm"]["priority"] == "High"
    assert llm_scorer.budget_exhausted() is None


def test_reset_clears_the_flag(monkeypatch):
    _install_create(monkeypatch, [_InsufficientBalance()])
    llm_scorer.score_batch([_paper("10.1/a")], _DIRECTIONS)
    assert llm_scorer.budget_exhausted()
    llm_scorer.reset_budget_state()
    assert llm_scorer.budget_exhausted() is None


# ---------------------------------------------------------------------------
# run_daily
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_daily(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "daily").mkdir(parents=True)
    monkeypatch.setattr(rd, "DATA_DIR", data_dir)
    monkeypatch.setattr(rd, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(rd, "SEEN_STATE", data_dir / "seen_dois.json")
    monkeypatch.setattr(rd, "MANIFESTS_DIR", data_dir / "manifests")
    monkeypatch.setattr(rd, "SNAPSHOTS_DIR", data_dir / "config_snapshots")
    monkeypatch.setattr(rd, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(rd.mf, "build_manifest", lambda **kw: {
        "run_id": "t", "git_commit": "d", "config": {"scorer_prompt": "h"}})
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)
    monkeypatch.setattr(rd.doi_aliases, "resolve_zenodo",
                        lambda dois, path, **kw: ({}, {"looked_up": 0, "resolved": 0,
                                                       "failed": 0, "skipped_cap": 0}))
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [])
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: [])
    return data_dir


def test_daily_raises_budget_flag_and_keeps_papers_for_rescore(monkeypatch, isolated_daily):
    _install_create(monkeypatch, [_InsufficientBalance()])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [
        {**_paper("10.1/a"), "direction": None}, {**_paper("10.1/b"), "direction": None}])

    report = rd.run(days_back=1, skip_zotero=True)

    assert "scorer_budget_exhausted" in report["quality_flags"]
    assert "scorer_failed" in report["quality_flags"]
    assert report["counts"]["scorer_failed"] == 2
    bucket = json.loads((isolated_daily / "daily" / "2026-09-16.json").read_text(encoding="utf-8"))
    assert all(p["llm"]["scorer_failed"] for p in bucket["papers"])  # rescorable later


def test_daily_without_402_has_no_budget_flag(monkeypatch, isolated_daily):
    _install_create(monkeypatch, [_GOOD])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [
        {**_paper("10.1/a"), "direction": None}])
    report = rd.run(days_back=1, skip_zotero=True)
    assert "scorer_budget_exhausted" not in report["quality_flags"]


# ---------------------------------------------------------------------------
# run_historical
# ---------------------------------------------------------------------------

@pytest.fixture
def quiet_backfill(monkeypatch):
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.doi_aliases, "resolve_zenodo",
                        lambda dois, path, **kw: ({}, {"looked_up": 0, "resolved": 0,
                                                       "failed": 0, "skipped_cap": 0}))


def _openalex_month(monkeypatch, papers_by_window: dict):
    def fetch(concepts, keywords, from_date=None, to_date=None, **kw):
        return [dict(p) for p in papers_by_window.get(from_date, [])]
    monkeypatch.setattr(rh.openalex_fetcher, "fetch", fetch)


def test_backfill_parks_month_persists_scored_only_and_resumes(monkeypatch, tmp_path, quiet_backfill):
    _openalex_month(monkeypatch, {
        "2026-02-01": [_paper("10.1/ok", "2026-02-10"), _paper("10.1/dead", "2026-02-11")],
        "2026-03-01": [_paper("10.1/mar", "2026-03-10")],
    })
    _install_create(monkeypatch, [_GOOD, _InsufficientBalance()])
    out = tmp_path / "runs" / "2026-02-01_2026-03-31"
    out.mkdir(parents=True)

    report = rh.run(from_date="2026-02-01", to_date="2026-03-31", dry_run=False,
                    output_dir=out, data_root=tmp_path, no_resume=True, sources={"openalex"})

    assert report["months_completed"] == 0
    assert report["stopped_early"]["month"] == "2026-02"
    assert "DeepSeek balance exhausted" in report["stopped_early"]["reason"]
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    assert progress["months"]["2026-02"]["status"] == "pending"
    assert progress["months"]["2026-03"]["status"] == "pending"
    assert (tmp_path / "daily" / "2026-02-10.json").exists()        # scored one kept
    assert not (tmp_path / "daily" / "2026-02-11.json").exists()    # unscored not persisted
    assert "doi:10.1/dead" not in progress["dois_seen"]

    # Topped up: the same range resumes, scores the unscored paper only.
    llm_scorer.reset_budget_state()
    calls = _install_create(monkeypatch, [_GOOD, _GOOD])
    report = rh.run(from_date="2026-02-01", to_date="2026-03-31", dry_run=False,
                    output_dir=out, data_root=tmp_path, no_resume=False, sources={"openalex"})

    assert report["months_completed"] == 2 and report["stopped_early"] is None
    assert len(calls) == 2  # 10.1/dead and 10.1/mar; 10.1/ok was skipped as in-corpus
    assert (tmp_path / "daily" / "2026-02-11.json").exists()
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    assert progress["months"]["2026-02"]["counts"]["scorer_failed"] == 0
    assert progress["months"]["2026-02"]["counts"]["scored"] == 1


def test_backfill_counts_report_failures_honestly(monkeypatch, tmp_path, quiet_backfill):
    _openalex_month(monkeypatch, {"2026-02-01": [_paper("10.1/a", "2026-02-10"),
                                                 _paper("10.1/b", "2026-02-11")]})
    # Ordinary failure (3 attempts) for the second paper, no 402.
    _install_create(monkeypatch, [_GOOD, ValueError("x"), ValueError("x"), ValueError("x")])
    out = tmp_path / "runs" / "r"
    out.mkdir(parents=True)
    report = rh.run(from_date="2026-02-01", to_date="2026-02-28", dry_run=False,
                    output_dir=out, data_root=tmp_path, no_resume=True, sources={"openalex"})
    progress = json.loads((out / "_progress.json").read_text(encoding="utf-8"))
    counts = progress["months"]["2026-02"]["counts"]
    assert report["months_completed"] == 1
    assert counts["scored"] == 1 and counts["scorer_failed"] == 1
    # The ordinary failure is persisted (ADR-0017: null + flag, rescorable).
    assert (tmp_path / "daily" / "2026-02-11.json").exists()


# ---------------------------------------------------------------------------
# build_pages
# ---------------------------------------------------------------------------

def test_flatten_text_handles_every_scorer_shape():
    assert build_pages._flatten_text(None) == ""
    assert build_pages._flatten_text("a") == "a"
    assert build_pages._flatten_text({"m": "动机", "r": {"x": "结果", "y": ""}}) == "动机 结果"
    assert build_pages._flatten_text(["a", {"b": "c"}, 3]) == "a c 3"


def test_search_index_survives_nested_summary(tmp_path):
    data_dir = tmp_path / "data"
    daily = data_dir / "daily"
    daily.mkdir(parents=True)
    paper = {**_paper("10.1/nested", "2026-04-27"),
             "llm": {"priority": "Low", "relevance_to_user": {"zh": "相关"},
                     "why_not_core": ["a", "b"],
                     "summary_zh": {"motivation": {"text": "嵌套"}, "method": "方法"},
                     "key_terms": [{"en": "x", "zh": "y"}], "tags": ["t"]},
             "schema_version": "v2", "date_precision": "day",
             "first_seen_at": "2026-09-15T05:00:00Z"}
    (daily / "2026-04-27.json").write_text(json.dumps({
        "schema_version": "v2", "date": "2026-04-27", "date_precision": "day",
        "papers": [paper], "counts": {}}), encoding="utf-8")
    docs = tmp_path / "site"
    docs.mkdir()

    n = build_pages._build_search_index(docs, data_dir)

    assert n == 1
    deep = json.loads((docs / "search-deep-2026.json").read_text(encoding="utf-8"))
    text = json.dumps(deep, ensure_ascii=False)
    assert "嵌套" in text and "方法" in text and "相关" in text
