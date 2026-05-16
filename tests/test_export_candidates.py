"""Tests for pipeline/export_candidates.py.

Covers:
  - normal export (Medium+ default filter)
  - --min-priority all 4 levels
  - --from-date / --to-date date filtering and --all mutual exclusion
  - cross-day dedup by doi (and arxiv_id fallback)
  - empty affiliation -> graceful empty string / empty list
  - --dry-run writes no file
  - sort order: newest source date first, then priority rank
  - output is flat: no nested `llm` object

Run with:
    pytest tests/test_export_candidates.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import export_candidates as ec  # noqa: E402


def _make_paper(*, doi: str = "", arxiv_id: str = "",
                priority: str = "Medium",
                title: str | None = None,
                date: str = "2026-05-13",
                date_precision: str = "day",
                scorer_version: str = "v3") -> dict:
    """Build a synthetic paper matching daily/*.json v2 paper schema."""
    return {
        "source":   "arxiv" if arxiv_id else "openalex",
        "id":       f"arxiv:{arxiv_id}" if arxiv_id else f"doi:{doi}",
        "doi":      doi,
        "arxiv_id": arxiv_id,
        "title":    title if title is not None else f"Paper {doi or arxiv_id}",
        "abstract": "an abstract",
        "authors":  ["A. Author"],
        "venue":    "Test Venue",
        "year":     2026,
        "date":     date,
        "date_precision": date_precision,
        "scorer_version": scorer_version,
        "url":      "http://example.org",
        "direction":      "fea_surrogate",
        "direction_name": "FEA & Surrogate Modelling",
        "llm": {
            "priority":          priority,
            "relevance_level":   "Transferable",
            "read_action":       "Save for project",
            "validation_kind":   "numerical_benchmark",
            "relevance_to_user": "...",
            "why_not_core":      "",
            "flags":             {"is_review": False},
            "tags":              ["x"],
            "key_terms":         [{"en": "FE", "zh": "有限元"}],
            "summary_zh":        {"motivation": "动机"},
            "summary_en":        {"motivation": "motivation"},
        },
    }


def _write_daily(daily_dir: pathlib.Path, date_str: str,
                 papers: list[dict],
                 date_precision: str = "day") -> pathlib.Path:
    """Write a v2-shape daily bucket: a dict wrapper around the paper list.

    ADR-0015 §4.5 v2 schema:
      {schema_version, date, date_precision, papers, counts}
    """
    daily_dir.mkdir(parents=True, exist_ok=True)
    path = daily_dir / f"{date_str}.json"
    payload = {
        "schema_version": "v2",
        "date": date_str,
        "date_precision": date_precision,
        "papers": papers,
        "counts": {"total": len(papers)},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def daily_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "data" / "daily"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def output_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "data" / "exports" / "candidates.jsonl"


# ----------------------------- normal export -----------------------------

def test_normal_export_default_medium(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/a", priority="High"),
        _make_paper(doi="10.1/b", priority="Medium"),
        _make_paper(doi="10.1/c", priority="Low"),
        _make_paper(doi="10.1/d", priority="Exclude"),
    ])
    rc = ec.main([
        "--daily-dir", str(daily_dir),
        "--output", str(output_path),
    ])
    assert rc == 0
    records = _read_jsonl(output_path)
    assert len(records) == 2
    assert {r["doi"] for r in records} == {"10.1/a", "10.1/b"}


# ----------------------------- priority levels ---------------------------

def test_min_priority_high_only(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/a", priority="High"),
        _make_paper(doi="10.1/b", priority="Medium"),
        _make_paper(doi="10.1/c", priority="Low"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path),
             "--min-priority", "High"])
    records = _read_jsonl(output_path)
    assert [r["priority"] for r in records] == ["High"]


def test_min_priority_low_excludes_exclude(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/a", priority="High"),
        _make_paper(doi="10.1/b", priority="Medium"),
        _make_paper(doi="10.1/c", priority="Low"),
        _make_paper(doi="10.1/d", priority="Exclude"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path),
             "--min-priority", "Low"])
    records = _read_jsonl(output_path)
    assert {r["priority"] for r in records} == {"High", "Medium", "Low"}


def test_min_priority_all_includes_exclude(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/a", priority="High"),
        _make_paper(doi="10.1/b", priority="Exclude"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path),
             "--min-priority", "All"])
    records = _read_jsonl(output_path)
    assert {r["priority"] for r in records} == {"High", "Exclude"}


# ----------------------------- date range --------------------------------

def test_date_range_inclusive(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-11", [_make_paper(doi="10.1/old", priority="High")])
    _write_daily(daily_dir, "2026-05-12", [_make_paper(doi="10.1/mid", priority="High")])
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/new", priority="High")])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path),
             "--from-date", "2026-05-12",
             "--to-date",   "2026-05-13"])
    records = _read_jsonl(output_path)
    assert {r["doi"] for r in records} == {"10.1/mid", "10.1/new"}


def test_all_conflicts_with_from_date(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    with pytest.raises(SystemExit):
        ec.main(["--daily-dir", str(daily_dir),
                 "--output", str(output_path),
                 "--all",
                 "--from-date", "2026-05-13"])


def test_from_after_to_errors(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    with pytest.raises(SystemExit):
        ec.main(["--daily-dir", str(daily_dir),
                 "--output", str(output_path),
                 "--from-date", "2026-05-13",
                 "--to-date",   "2026-05-01"])


def test_skipped_marker_files_ignored(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    # Simulate an empty-run skip marker, which should be ignored by the
    # filename regex (only YYYY-MM-DD.json matches).
    (daily_dir / "2026-05-14.SKIPPED.json").write_text(
        json.dumps({"date": "2026-05-14", "reason": "fetched_zero"})
    )
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    records = _read_jsonl(output_path)
    assert len(records) == 1


# ----------------------------- dedup -------------------------------------

def test_dedup_same_doi_across_days(daily_dir, output_path, capsys):
    _write_daily(daily_dir, "2026-05-12", [
        _make_paper(doi="10.1/x", priority="Medium"),
    ])
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/x", priority="High"),  # rescored later
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    records = _read_jsonl(output_path)
    assert len(records) == 1
    # Latest source_date wins
    assert records[0]["priority"] == "High"
    assert records[0]["radar_source_date"] == "2026-05-13"
    err = capsys.readouterr().err
    assert "cross-day dedup" in err
    assert "1 duplicate" in err


def test_dedup_uses_arxiv_id_when_doi_empty(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-12", [
        _make_paper(doi="", arxiv_id="2605.1234v1", priority="Medium"),
    ])
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="", arxiv_id="2605.1234v1", priority="High"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    records = _read_jsonl(output_path)
    assert len(records) == 1
    assert records[0]["priority"] == "High"
    assert records[0]["radar_source_date"] == "2026-05-13"


def test_dedup_keeps_earlier_when_no_newer_seen(daily_dir, output_path):
    # Older daily has the paper; newer daily has different papers. No dedup.
    _write_daily(daily_dir, "2026-05-12", [
        _make_paper(doi="10.1/only-old", priority="High"),
    ])
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/only-new", priority="High"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    records = _read_jsonl(output_path)
    assert {r["doi"] for r in records} == {"10.1/only-old", "10.1/only-new"}


# ----------------------------- empty affiliation -------------------------

def test_empty_affiliation_renders_empty_string_and_empty_list(daily_dir, output_path):
    p = _make_paper(doi="", arxiv_id="2605.0000v1", priority="High")
    # arxiv papers in real data have no affiliation keys at all
    p.pop("first_author_affiliation", None)
    p.pop("corresponding_authors", None)
    _write_daily(daily_dir, "2026-05-13", [p])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    rec = _read_jsonl(output_path)[0]
    assert rec["first_author_affiliation"] == ""
    assert rec["corresponding_authors"] == []


def test_corresponding_authors_passes_through(daily_dir, output_path):
    p = _make_paper(doi="10.1/y", priority="High")
    p["first_author_affiliation"] = "UCL"
    p["corresponding_authors"] = [
        {"name": "Smith", "affiliation": "UCL", "inferred": False},
    ]
    _write_daily(daily_dir, "2026-05-13", [p])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    rec = _read_jsonl(output_path)[0]
    assert rec["first_author_affiliation"] == "UCL"
    assert rec["corresponding_authors"][0]["name"] == "Smith"
    assert rec["corresponding_authors"][0]["affiliation"] == "UCL"


# ----------------------------- dry-run -----------------------------------

def test_dry_run_writes_no_file(daily_dir, output_path, capsys):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path),
             "--dry-run"])
    assert not output_path.exists()
    out = capsys.readouterr().out
    assert "[dry-run] would write 1 record" in out


# ----------------------------- ordering ----------------------------------

def test_sort_order_newest_then_priority(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-11", [
        _make_paper(doi="10.1/older-medium", priority="Medium"),
    ])
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/newer-medium", priority="Medium"),
        _make_paper(doi="10.1/newer-high",   priority="High"),
    ])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    dois = [r["doi"] for r in _read_jsonl(output_path)]
    assert dois == ["10.1/newer-high", "10.1/newer-medium", "10.1/older-medium"]


# ----------------------------- schema shape ------------------------------

def test_schema_is_flat_no_nested_llm_object(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    rec = _read_jsonl(output_path)[0]
    assert "llm" not in rec, "schema must be flat; `llm` should be unwrapped"
    for key in (
        "priority", "relevance_level", "read_action", "validation_kind",
        "relevance_to_user", "why_not_core", "flags", "tags", "key_terms",
        "summary_zh", "summary_en",
    ):
        assert key in rec, f"missing top-level LLM field: {key}"


def test_provenance_fields_present(daily_dir, output_path):
    _write_daily(daily_dir, "2026-05-13", [_make_paper(doi="10.1/a", priority="High")])
    ec.main(["--daily-dir", str(daily_dir),
             "--output", str(output_path)])
    rec = _read_jsonl(output_path)[0]
    assert rec["radar_source_date"] == "2026-05-13"
    assert rec["radar_export_version"] == "v2"
    # radar_export_date is today; just confirm it's an ISO date
    import datetime as _dt
    _dt.date.fromisoformat(rec["radar_export_date"])


# ----------------------------- v2 schema migration -----------------------

def test_v2_file_yields_date_precision_and_scorer_version(daily_dir, output_path):
    """A v2 daily bucket flows through with the two new provenance fields."""
    _write_daily(daily_dir, "2026-05-13", [
        _make_paper(doi="10.1/a", priority="High",
                    date_precision="month", scorer_version="v3"),
    ], date_precision="month")
    rc = ec.main(["--daily-dir", str(daily_dir),
                  "--output", str(output_path)])
    assert rc == 0
    rec = _read_jsonl(output_path)[0]
    assert rec["date_precision"] == "month"
    assert rec["scorer_version"] == "v3"


def test_export_version_constant_is_v2():
    assert ec.EXPORT_VERSION == "v2"


def test_legacy_v1_list_still_readable(daily_dir, output_path):
    """A stray pre-migration v1 list-shaped file is still consumed."""
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / "2026-05-13.json").write_text(
        json.dumps([_make_paper(doi="10.1/legacy", priority="High")],
                   ensure_ascii=False)
    )
    ec.main(["--daily-dir", str(daily_dir), "--output", str(output_path)])
    records = _read_jsonl(output_path)
    assert len(records) == 1
    assert records[0]["doi"] == "10.1/legacy"
