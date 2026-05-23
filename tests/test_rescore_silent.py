"""Tests for ADR-0017 §Decision 2 — scripts.rescore_silent.

Each test builds a synthetic v2 corpus in ``tmp_path`` and exercises the
CLI/library through ``rs.main``. The scorer itself is monkeypatched at
``rs.llm_scorer.score_batch`` so no real network calls happen and the
canned outputs let tests assert what landed in each paper.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import rescore_silent as rs  # noqa: E402


@pytest.fixture(autouse=True)
def _bind_lazy_scorer():
    """rescore_silent defers ``from pipeline import llm_scorer`` so that
    --dry-run is usable without OPENAI_API_KEY. The conftest fixture sets
    a stub key, so we can safely force-bind ``rs.llm_scorer`` here — tests
    that monkeypatch ``rs.llm_scorer.score_batch`` then have a real module
    to patch on, and the script's own ``_ensure_llm_scorer()`` returns the
    same cached object."""
    rs._ensure_llm_scorer()


# ============================== fixtures =================================

DIRECTIONS_YAML = """
version: 1
directions:
  hip_implant:
    display_name: "Hip Implant"
    llm_prompt_focus: |
      focus
"""


def _silent_paper(doi: str, priority: str = "Low") -> dict:
    """ADR-0017 silent-Low shape: priority set, reasoning empty,
    priority_reason populated with the legacy exception trace."""
    return {
        "doi": doi,
        "title": f"Silent {doi}",
        "abstract": "abs",
        "direction": "hip_implant",
        "direction_name": "Hip Implant",
        "llm": {
            "priority": priority,
            "priority_reason": "scoring failed: JSONDecodeError(...)",
            "relevance_to_user": "",
            "tags": [],
            "summary_zh": {"motivation": ""},
        },
    }


def _healthy_paper(doi: str, priority: str = "High") -> dict:
    return {
        "doi": doi,
        "title": f"Healthy {doi}",
        "abstract": "abs",
        "direction": "hip_implant",
        "direction_name": "Hip Implant",
        "llm": {
            "priority": priority,
            "relevance_to_user": "Looks relevant.",
            "tags": ["t1"],
            "summary_zh": {"motivation": "动机"},
        },
    }


def _failed_paper(doi: str) -> dict:
    """A paper that previously exhausted its 3 retries."""
    return {
        "doi": doi,
        "title": f"Failed {doi}",
        "abstract": "abs",
        "direction": "hip_implant",
        "direction_name": "Hip Implant",
        "llm": {
            "priority": None,
            "scorer_failed": True,
            "scorer_failed_reason": "JSONDecodeError(...)",
            "scorer_failed_attempts": 3,
        },
    }


def _write_bucket(daily: pathlib.Path, date: str, papers: list[dict]) -> None:
    daily.mkdir(parents=True, exist_ok=True)
    (daily / f"{date}.json").write_text(
        json.dumps({
            "schema_version": "v2",
            "date": date,
            "date_precision": "day",
            "papers": papers,
            "counts": {"fetched_total": len(papers), "scored": len(papers)},
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.fixture()
def env(tmp_path: pathlib.Path):
    daily = tmp_path / "data" / "daily"
    _write_bucket(daily, "2024-05-10", [
        _silent_paper("10.1/s1"),
        _silent_paper("10.1/s2"),
        _healthy_paper("10.1/h1"),
    ])
    _write_bucket(daily, "2024-05-11", [
        _silent_paper("10.1/s3"),
        _healthy_paper("10.1/h2"),
    ])
    cfg = tmp_path / "directions.yaml"
    cfg.write_text(DIRECTIONS_YAML, encoding="utf-8")
    return tmp_path, daily, cfg


def _fake_score_batch(papers, dirs):
    """Stub scorer: always returns a valid-looking rescored result."""
    for p in papers:
        p["llm"] = {
            "priority": "Medium",
            "relevance_to_user": "rescored OK",
            "summary_zh": {"motivation": "rescored 动机"},
            "tags": ["rescored"],
        }
    return papers, [{} for _ in papers]


# ============================== tests ====================================

def test_dry_run_reports_count_and_writes_nothing(env, capsys):
    _, daily, cfg = env
    files = list(daily.glob("*.json"))
    before_mtimes = {f: f.stat().st_mtime_ns for f in files}
    before_bytes = {f: f.read_bytes() for f in files}

    rc = rs.main([
        "--dry-run",
        "--corpus-root", str(daily),
        "--directions-yaml", str(cfg),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "total silent: 3" in out
    assert "2024-05: 3" in out

    # Nothing on disk changed.
    after_mtimes = {f: f.stat().st_mtime_ns for f in files}
    after_bytes = {f: f.read_bytes() for f in files}
    assert before_mtimes == after_mtimes
    assert before_bytes == after_bytes


def test_real_rescore_updates_silent_only_and_preserves_metadata(env, monkeypatch):
    _, daily, cfg = env
    monkeypatch.setattr(rs.llm_scorer, "score_batch", _fake_score_batch)

    rc = rs.main([
        "--corpus-root", str(daily), "--directions-yaml", str(cfg),
    ])
    assert rc == 0

    data10 = json.loads((daily / "2024-05-10.json").read_text(encoding="utf-8"))
    data11 = json.loads((daily / "2024-05-11.json").read_text(encoding="utf-8"))

    # Schema/counts metadata around papers[] preserved exactly.
    assert data10["schema_version"] == "v2"
    assert data10["date"] == "2024-05-10"
    assert data10["date_precision"] == "day"
    assert data10["counts"] == {"fetched_total": 3, "scored": 3}
    assert data11["counts"] == {"fetched_total": 2, "scored": 2}

    # Silent papers rescored, healthy ones untouched.
    by_doi = {p["doi"]: p for p in (data10["papers"] + data11["papers"])}
    for doi in ("10.1/s1", "10.1/s2", "10.1/s3"):
        assert by_doi[doi]["llm"]["priority"] == "Medium"
        assert by_doi[doi]["llm"]["relevance_to_user"] == "rescored OK"
    for doi in ("10.1/h1", "10.1/h2"):
        assert by_doi[doi]["llm"]["priority"] == "High"  # unchanged
        assert by_doi[doi]["llm"]["relevance_to_user"] == "Looks relevant."


def test_limit_stops_after_n_papers(env, monkeypatch):
    _, daily, cfg = env
    monkeypatch.setattr(rs.llm_scorer, "score_batch", _fake_score_batch)

    rc = rs.main([
        "--limit", "1",
        "--corpus-root", str(daily), "--directions-yaml", str(cfg),
    ])
    assert rc == 0

    all_papers = []
    for f in sorted(daily.glob("*.json")):
        all_papers.extend(json.loads(f.read_text(encoding="utf-8"))["papers"])
    rescored = [p for p in all_papers
                if p["llm"].get("relevance_to_user") == "rescored OK"]
    silent_remaining = [p for p in all_papers if rs.is_silent(p["llm"])]
    assert len(rescored) == 1
    assert len(silent_remaining) == 2  # 3 silent originally, 1 done → 2 left


def test_resume_skips_scorer_failed_papers(env, monkeypatch):
    """A paper that previously exhausted its 3 retries (scorer_failed=True)
    is NOT re-attempted under --resume; remaining silent papers still are."""
    _, daily, cfg = env
    _write_bucket(daily, "2024-05-12", [
        _failed_paper("10.1/sf"),
        _silent_paper("10.1/s4"),
    ])
    monkeypatch.setattr(rs.llm_scorer, "score_batch", _fake_score_batch)

    rc = rs.main([
        "--resume",
        "--corpus-root", str(daily), "--directions-yaml", str(cfg),
    ])
    assert rc == 0

    data12 = json.loads((daily / "2024-05-12.json").read_text(encoding="utf-8"))
    sf = next(p for p in data12["papers"] if p["doi"] == "10.1/sf")
    s4 = next(p for p in data12["papers"] if p["doi"] == "10.1/s4")
    # The previously-failed paper is preserved unchanged.
    assert sf["llm"]["scorer_failed"] is True
    assert sf["llm"]["priority"] is None
    # The truly-silent neighbour got rescored.
    assert s4["llm"]["priority"] == "Medium"
    assert s4["llm"]["relevance_to_user"] == "rescored OK"


def test_score_batch_called_once_per_bucket_with_all_candidates(env, monkeypatch):
    """ADR-0019: rescore must hand each bucket's candidates to score_batch
    in a single call so its ThreadPoolExecutor actually engages. The env
    fixture has 2 silent papers in 2024-05-10 and 1 silent paper in
    2024-05-11, so we expect exactly 2 score_batch calls with batch
    sizes [2, 1] (not 3 single-paper calls)."""
    _, daily, cfg = env
    calls: list[list[str]] = []

    def recording_score_batch(papers, dirs):
        calls.append([p["doi"] for p in papers])
        return _fake_score_batch(papers, dirs)

    monkeypatch.setattr(rs.llm_scorer, "score_batch", recording_score_batch)

    rc = rs.main([
        "--corpus-root", str(daily), "--directions-yaml", str(cfg),
    ])
    assert rc == 0

    # Exactly one call per bucket-that-had-candidates.
    assert len(calls) == 2, f"expected 2 batched calls, got {len(calls)}: {calls}"
    # Batches contain ALL silent papers from that bucket — not one-at-a-time.
    assert sorted(calls[0]) == ["10.1/s1", "10.1/s2"]
    assert calls[1] == ["10.1/s3"]


def test_limit_slices_candidates_within_a_bucket(tmp_path, monkeypatch):
    """When --limit caps below a bucket's candidate count, the bucket's
    batch must be sliced to fit the remaining budget — not the whole
    bucket, and not one paper at a time."""
    daily = tmp_path / "data" / "daily"
    _write_bucket(daily, "2024-06-01", [
        _silent_paper(f"10.1/b{i}") for i in range(5)
    ])
    cfg = tmp_path / "directions.yaml"
    cfg.write_text(DIRECTIONS_YAML, encoding="utf-8")

    calls: list[list[str]] = []

    def recording_score_batch(papers, dirs):
        calls.append([p["doi"] for p in papers])
        return _fake_score_batch(papers, dirs)

    monkeypatch.setattr(rs.llm_scorer, "score_batch", recording_score_batch)

    rc = rs.main([
        "--limit", "2",
        "--corpus-root", str(daily), "--directions-yaml", str(cfg),
    ])
    assert rc == 0

    # One batched call, sized to the budget (2 of 5), not 5 and not 1+1.
    assert len(calls) == 1
    assert len(calls[0]) == 2

    # Of the 5 silent papers, exactly 2 are now rescored on disk.
    data = json.loads((daily / "2024-06-01.json").read_text(encoding="utf-8"))
    rescored = [p for p in data["papers"]
                if p["llm"].get("relevance_to_user") == "rescored OK"]
    silent_remaining = [p for p in data["papers"] if rs.is_silent(p["llm"])]
    assert len(rescored) == 2
    assert len(silent_remaining) == 3


def test_atomic_write_failure_preserves_original(env, monkeypatch):
    """Simulate a mid-flush rename failure: the original daily file
    content must be byte-for-byte intact."""
    _, daily, cfg = env
    target = daily / "2024-05-10.json"
    original = target.read_bytes()

    def explode(src, dst):
        raise OSError("simulated rename failure")
    monkeypatch.setattr(rs.os, "replace", explode)
    monkeypatch.setattr(rs.llm_scorer, "score_batch", _fake_score_batch)

    with pytest.raises(OSError, match="simulated rename failure"):
        rs.main([
            "--corpus-root", str(daily), "--directions-yaml", str(cfg),
        ])

    # Original bucket bytes unchanged.
    assert target.read_bytes() == original
    # The orphaned .tmp was cleaned up by atomic_write_json's finally path.
    assert not (target.with_suffix(target.suffix + ".tmp")).exists()
