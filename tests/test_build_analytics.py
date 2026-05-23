"""Tests for scripts/build_analytics.py (Phase A — A1 distribution stats).

Style mirrors tests/test_weekly_report.py: write synthetic v2 daily buckets
to tmp_path, run main() with --daily-dir <tmp>, assert artifacts + counts.

Run with:
    .venv/bin/pytest tests/test_build_analytics.py -x
"""
from __future__ import annotations

import builtins
import csv
import importlib.util
import json
import pathlib
import sys
from collections import Counter

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_analytics.py"

# Load the script as a module without polluting scripts/ with an __init__.
spec = importlib.util.spec_from_file_location("build_analytics", SCRIPT)
build_analytics = importlib.util.module_from_spec(spec)
sys.modules["build_analytics"] = build_analytics
assert spec.loader is not None
spec.loader.exec_module(build_analytics)


def _paper(*, doi: str = "10.1/x",
           direction: str = "ai_bioprinting",
           priority: str = "High",
           scorer_version: str = "v3") -> dict:
    return {
        "doi": doi,
        "title": f"Paper {doi}",
        "direction": direction,
        "scorer_version": scorer_version,
        "date": "2024-06-15",
        "date_precision": "day",
        "llm": {"priority": priority, "summary_zh": {}, "tags": []},
    }


def _write_bucket(daily_dir: pathlib.Path, date_str: str, papers: list[dict]) -> None:
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f"{date_str}.json").write_text(
        json.dumps(
            {
                "schema_version": "v2",
                "date": date_str,
                "date_precision": "day",
                "papers": papers,
                "counts": {"total": len(papers)},
            },
            ensure_ascii=False,
        )
    )


def _read_csv(path: pathlib.Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_loads_buckets(tmp_path):
    """Two years x two directions x mixed v1/v3 -> both CSVs and both PNGs exist."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2023-03-01", [
        _paper(doi="10.1/a", direction="ai_bioprinting", priority="High"),
        _paper(doi="10.1/b", direction="fea_surrogate", priority="Medium"),
    ])
    _write_bucket(daily, "2024-04-01", [
        _paper(doi="10.1/c", direction="ai_bioprinting", priority="Low"),
        _paper(doi="10.1/d", direction="fea_surrogate", priority="High",
               scorer_version="v1"),
    ])

    rc = build_analytics.main(["--daily-dir", str(daily), "--out-dir", str(out)])
    assert rc == 0

    yearly = _read_csv(out / "distribution_yearly.csv")
    monthly = _read_csv(out / "distribution_monthly.csv")
    # 4 distinct (year, direction, priority, scorer_version) rows: one per paper.
    assert len(yearly) == 4
    assert len(monthly) == 4
    # Yearly CSV bins by bucket-date year, not paper-date year.
    years = {r["year"] for r in yearly}
    assert years == {"2023", "2024"}
    months = {r["year_month"] for r in monthly}
    assert months == {"2023-03", "2024-04"}

    assert (out / "distribution_yearly.png").stat().st_size > 5_000
    assert (out / "distribution_priority_ratio.png").stat().st_size > 5_000


def test_v1_separated(tmp_path):
    """v1 papers appear as their own scorer_version rows, never folded into v3."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-01-01", [
        _paper(doi="10.1/v3", direction="hip_implant", priority="High",
               scorer_version="v3"),
        _paper(doi="10.1/v1", direction="hip_implant", priority="High",
               scorer_version="v1"),
    ])
    rc = build_analytics.main(["--daily-dir", str(daily), "--out-dir", str(out)])
    assert rc == 0
    rows = _read_csv(out / "distribution_yearly.csv")

    # Both versions present as separate rows with count=1.
    by_version = {(r["scorer_version"], int(r["count"])) for r in rows}
    assert ("v1", 1) in by_version
    assert ("v3", 1) in by_version

    # The v3 slice the PNG draws from has exactly one row (not silently 2).
    v3_rows = [r for r in rows if r["scorer_version"] == "v3"]
    assert len(v3_rows) == 1
    assert int(v3_rows[0]["count"]) == 1


def test_handles_malformed(tmp_path):
    """Missing llm.priority or missing direction -> skipped+counted, no crash."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-05-01", [
        _paper(doi="10.1/ok"),
        {
            "doi": "10.1/no-priority",
            "direction": "ai_bioprinting",
            "scorer_version": "v3",
            "llm": {},  # priority missing
        },
        {
            "doi": "10.1/no-direction",
            "scorer_version": "v3",
            "llm": {"priority": "High"},
        },
        "not-a-paper-object",  # not a dict
    ])
    rc = build_analytics.main(["--daily-dir", str(daily), "--out-dir", str(out)])
    assert rc == 0
    rows = _read_csv(out / "distribution_yearly.csv")
    assert len(rows) == 1  # only the "ok" paper survives
    assert rows[0]["direction"] == "ai_bioprinting"


def test_dry_run_writes_nothing(tmp_path):
    """--dry-run leaves out-dir untouched."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-05-01", [_paper()])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out), "--dry-run",
    ])
    assert rc == 0
    assert not out.exists() or not any(out.iterdir())


def test_single_pass(tmp_path, monkeypatch):
    """Each bucket file is opened at most once across the whole run."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-05-01", [_paper(doi="10.1/p1")])
    _write_bucket(daily, "2024-06-01", [_paper(doi="10.1/p2")])

    opened: list[str] = []
    real_open = builtins.open

    def counting_open(file, *args, **kwargs):
        try:
            s = str(file)
        except Exception:  # pragma: no cover — defensive
            s = ""
        if s.endswith(".json") and "daily" in s:
            opened.append(s)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", counting_open)
    rc = build_analytics.main(["--daily-dir", str(daily), "--out-dir", str(out)])
    assert rc == 0

    counts = Counter(opened)
    assert len(counts) == 2, f"expected 2 distinct daily files, got {counts}"
    assert all(c == 1 for c in counts.values()), f"each file opened once: {counts}"
