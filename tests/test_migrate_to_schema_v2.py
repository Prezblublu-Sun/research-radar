"""Tests for scripts/migrate_to_schema_v2.py.

All tests use synthetic v1 data written into tmp_path; the real
data/ directory is never read.

Run with:
    pytest tests/test_migrate_to_schema_v2.py
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate_to_schema_v2.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("migrate_to_schema_v2", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["migrate_to_schema_v2"] = mod
    spec.loader.exec_module(mod)
    return mod


mig = _load_module()


# ============================================================================
# Synthetic data factories
# ============================================================================

def _paper(*, doi="", arxiv_id="", date="2024-03-15", source="openalex",
           title="t", direction="hip-implants",
           llm: dict | None = None) -> dict:
    p = {
        "source": source,
        "id": doi or arxiv_id or "x",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": "abs",
        "authors": ["A"],
        "venue": "V",
        "year": int(date[:4]) if date else 2024,
        "date": date,
        "url": "",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
        "directions": [direction],
        "direction": direction,
        "direction_name": direction,
        "routing_matches": [],
    }
    if llm is not None:
        p["llm"] = llm
    return p


def _write_daily_v1(root: pathlib.Path, filename_date: str, papers: list[dict]) -> None:
    d = root / "daily"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{filename_date}.json").write_text(json.dumps(papers))


def _write_historical_v1(root: pathlib.Path, month: str, papers: list[dict],
                         completed_at: str = "2026-05-14T22:21:03Z") -> None:
    d = root / "historical"
    d.mkdir(parents=True, exist_ok=True)
    body = {
        "schema_version": "v1",
        "month": month,
        "window": {"from": f"{month}-01", "to": f"{month}-28"},
        "dry_run": False,
        "completed_at": completed_at,
        "counts": {},
        "papers": papers,
    }
    (d / f"{month}.json").write_text(json.dumps(body))


def _read(path: pathlib.Path) -> dict | list:
    return json.loads(path.read_text())


# ============================================================================
# (a) Three papers, three dates -> three v2 files
# ============================================================================

def test_redistributes_papers_by_publication_date(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-03-15"),
        _paper(doi="10.1/b", date="2024-04-20"),
        _paper(doi="10.1/c", date="2024-05-25"),
    ])

    mig.main(["--source-dir", str(src), "--output-dir", str(out)])

    daily = out / "daily"
    assert (daily / "2024-03-15.json").exists()
    assert (daily / "2024-04-20.json").exists()
    assert (daily / "2024-05-25.json").exists()
    assert len(list(daily.glob("*.json"))) == 3

    f1 = _read(daily / "2024-03-15.json")
    assert f1["schema_version"] == "v2"
    assert f1["date"] == "2024-03-15"
    assert len(f1["papers"]) == 1
    assert f1["papers"][0]["doi"] == "10.1/a"


# ============================================================================
# (b) Same DOI in two source files -> first-seen wins
# ============================================================================

def test_dedup_first_seen_wins_across_source_files(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"

    # Historical run timestamp = 2024-02-01 (earliest); daily file = 2026-05-15.
    _write_historical_v1(src, "2024-01", [
        _paper(doi="10.1/shared", date="2024-01-15", title="first"),
    ], completed_at="2024-02-01T00:00:00Z")
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/shared", date="2024-01-15", title="second"),
    ])

    mig.main(["--source-dir", str(src), "--output-dir", str(out)])

    f = _read(out / "daily" / "2024-01-15.json")
    assert len(f["papers"]) == 1
    # First-seen wins => historical wins => title="first", scorer_version="v1"
    assert f["papers"][0]["title"] == "first"
    assert f["papers"][0]["scorer_version"] == "v1"
    assert f["papers"][0]["first_seen_at"] == "2024-02-01T00:00:00Z"


# ============================================================================
# (c)(d)(e) date_precision inference for day / month / year
# ============================================================================

def test_date_precision_day_for_mid_month(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-03-15"),
    ])
    mig.main(["--source-dir", str(src), "--output-dir", str(out)])
    f = _read(out / "daily" / "2024-03-15.json")
    assert f["date_precision"] == "day"
    assert f["papers"][0]["date_precision"] == "day"


def test_date_precision_month_for_first_of_non_january(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-03-01"),
    ])
    mig.main(["--source-dir", str(src), "--output-dir", str(out)])
    f = _read(out / "daily" / "2024-03-01.json")
    assert f["date_precision"] == "month"
    assert f["papers"][0]["date_precision"] == "month"


def test_date_precision_year_for_january_first(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-01-01"),
    ])
    mig.main(["--source-dir", str(src), "--output-dir", str(out)])
    f = _read(out / "daily" / "2024-01-01.json")
    assert f["date_precision"] == "year"
    assert f["papers"][0]["date_precision"] == "year"


# ============================================================================
# (f) scorer_version: v1 for historical, v3 for daily
# ============================================================================

def test_scorer_version_assigned_by_source_kind(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_historical_v1(src, "2024-01", [
        _paper(doi="10.1/hist", date="2024-01-15"),
    ], completed_at="2024-02-01T00:00:00Z")
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/daily", date="2024-04-20"),
    ])

    mig.main(["--source-dir", str(src), "--output-dir", str(out)])

    hist_file = _read(out / "daily" / "2024-01-15.json")
    daily_file = _read(out / "daily" / "2024-04-20.json")
    assert hist_file["papers"][0]["scorer_version"] == "v1"
    assert daily_file["papers"][0]["scorer_version"] == "v3"


# ============================================================================
# (g) discovery_log written with correct structure
# ============================================================================

def test_discovery_log_structure_and_keying(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_historical_v1(src, "2024-01", [
        _paper(doi="10.1/hist", date="2024-01-15"),
    ], completed_at="2026-05-14T22:21:03Z")
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/daily", date="2024-04-20"),
        _paper(arxiv_id="2605.14953v1", date="2024-04-21"),
    ])

    mig.main(["--source-dir", str(src), "--output-dir", str(out)])

    log_dir = out / "discovery_log"
    # Historical run-date = 2026-05-14 (from completed_at).
    # Daily run-date     = 2026-05-15 (from filename).
    assert (log_dir / "2026-05-14.json").exists()
    assert (log_dir / "2026-05-15.json").exists()

    hist_log = _read(log_dir / "2026-05-14.json")
    assert isinstance(hist_log, list)
    assert len(hist_log) == 1
    rec = hist_log[0]
    assert rec["doi_or_arxiv_id"] == "doi:10.1/hist"
    assert rec["first_seen_at"] == "2026-05-14T22:21:03Z"
    assert rec["run_type"] == "historical_backfill"

    daily_log = _read(log_dir / "2026-05-15.json")
    assert len(daily_log) == 2
    keys = sorted(r["doi_or_arxiv_id"] for r in daily_log)
    assert keys == ["arxiv:2605.14953v1", "doi:10.1/daily"]
    assert all(r["run_type"] == "daily" for r in daily_log)


# ============================================================================
# (h) --dry-run writes nothing but reports counts
# ============================================================================

def test_dry_run_writes_nothing_and_reports_counts(tmp_path, capsys):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-03-15"),
        _paper(doi="10.1/b", date="2024-04-20"),
    ])
    _write_historical_v1(src, "2024-01", [
        _paper(doi="10.1/c", date="2024-01-15"),
    ])

    rc = mig.main(["--source-dir", str(src), "--output-dir", str(out),
                   "--dry-run"])
    assert rc == 0

    assert not out.exists() or not any(out.rglob("*.json"))

    captured = capsys.readouterr().out
    assert "source files processed:  2" in captured
    assert "papers observed:         3" in captured
    assert "papers kept (post-dedup):3" in captured
    assert "dry-run: no files written" in captured


# ============================================================================
# Extra: --no-discovery-log suppresses log writes but still writes v2 papers
# ============================================================================

def test_no_discovery_log_flag_suppresses_logs(tmp_path):
    src = tmp_path / "src"
    out = tmp_path / "out"
    _write_daily_v1(src, "2026-05-15", [
        _paper(doi="10.1/a", date="2024-03-15"),
    ])
    mig.main(["--source-dir", str(src), "--output-dir", str(out),
              "--no-discovery-log"])
    assert (out / "daily" / "2024-03-15.json").exists()
    assert not (out / "discovery_log").exists()


# ============================================================================
# Extra: missing source-dir produces a non-zero exit code
# ============================================================================

def test_missing_source_dir_errors(tmp_path, capsys):
    rc = mig.main(["--source-dir", str(tmp_path / "nope"),
                   "--output-dir", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "does not exist" in err


# ============================================================================
# Extra: helpers are pure (no I/O) -- sanity-check infer_date_precision
# ============================================================================

@pytest.mark.parametrize("date,expected", [
    ("2024-03-15", "day"),
    ("2024-03-01", "month"),
    ("2024-12-01", "month"),
    ("2024-01-01", "year"),
    ("", "year"),
])
def test_infer_date_precision_table(date, expected):
    assert mig.infer_date_precision(date) == expected
