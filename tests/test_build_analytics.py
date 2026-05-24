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
           scorer_version: str = "v3",
           tags: list[str] | None = None) -> dict:
    return {
        "doi": doi,
        "title": f"Paper {doi}",
        "direction": direction,
        "scorer_version": scorer_version,
        "date": "2024-06-15",
        "date_precision": "day",
        "llm": {"priority": priority, "summary_zh": {}, "tags": list(tags or [])},
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


# ----------------------------------------------------------------------------
# Phase B (A2 — tag frequency trends) tests
# ----------------------------------------------------------------------------

def test_alias_map_merges(tmp_path):
    """SLM + LPBF variants collapse into the 'selective laser melting' canonical."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-01-01", [
        _paper(doi="10.1/slm", direction="am_biomedical", scorer_version="v3",
               tags=["SLM"]),
        _paper(doi="10.1/lpbf", direction="am_biomedical", scorer_version="v3",
               tags=["LPBF"]),
        _paper(doi="10.1/full", direction="am_biomedical", scorer_version="v3",
               tags=["laser powder bed fusion"]),
    ])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0
    rows = _read_csv(out / "tag_frequency_by_year_by_direction.csv")
    canonical = [r for r in rows if r["tag"] == "selective laser melting"]
    assert len(canonical) == 1
    assert int(canonical[0]["count"]) == 3
    # No variant should appear verbatim in the CSV.
    tags = {r["tag"] for r in rows}
    for variant in ("SLM", "LPBF", "slm", "lpbf", "laser powder bed fusion"):
        assert variant not in tags


def test_exclude_meta_tags(tmp_path):
    """'review' (and other meta tags) are dropped before counting."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-01-01", [
        _paper(doi="10.1/r", direction="ai_bioprinting", scorer_version="v3",
               tags=["review", "bioprinting", "Clinical Study"]),
    ])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0
    rows = _read_csv(out / "tag_frequency_by_year_by_direction.csv")
    tags = {r["tag"] for r in rows}
    assert "review" not in tags
    assert "Clinical Study" not in tags
    assert "clinical study" not in tags
    assert "bioprinting" in tags


def test_3d_bioprinting_not_merged(tmp_path):
    """'3D bioprinting' and 'bioprinting' must stay as two distinct rows."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-01-01", [
        _paper(doi="10.1/3d", direction="ai_bioprinting", scorer_version="v3",
               tags=["3D bioprinting"]),
        _paper(doi="10.1/b", direction="ai_bioprinting", scorer_version="v3",
               tags=["bioprinting"]),
    ])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0
    rows = _read_csv(out / "tag_frequency_by_year_by_direction.csv")
    tags = {r["tag"] for r in rows}
    assert "3D bioprinting" in tags
    assert "bioprinting" in tags
    # Neither should be merged into "additive manufacturing" via the
    # "3d printing" alias — the strings differ ("3d bioprinting" != "3d printing").
    am_rows = [r for r in rows if r["tag"] == "additive manufacturing"]
    assert am_rows == []


def test_emerging_arithmetic(tmp_path):
    """3 -> 8 qualifies; 10 -> 11 does not (fails the 2x ratio)."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"

    # emerging_tag: 3 occurrences in 2023, 8 in 2024 (fea_surrogate).
    _write_bucket(daily, "2023-06-01", [
        _paper(doi=f"10.1/e23-{i}", direction="fea_surrogate",
               scorer_version="v3", tags=["emerging_tag"]) for i in range(3)
    ])
    _write_bucket(daily, "2024-06-01", [
        _paper(doi=f"10.1/e24-{i}", direction="fea_surrogate",
               scorer_version="v3", tags=["emerging_tag"]) for i in range(8)
    ])
    # stable_tag: 10 in 2023, 11 in 2024 (hip_implant).
    _write_bucket(daily, "2023-07-01", [
        _paper(doi=f"10.1/s23-{i}", direction="hip_implant",
               scorer_version="v3", tags=["stable_tag"]) for i in range(10)
    ])
    _write_bucket(daily, "2024-07-01", [
        _paper(doi=f"10.1/s24-{i}", direction="hip_implant",
               scorer_version="v3", tags=["stable_tag"]) for i in range(11)
    ])

    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0
    rows = _read_csv(out / "tag_emerging_terms.csv")

    emerging_2024 = [r for r in rows
                     if r["tag"] == "emerging_tag" and r["year"] == "2024"]
    assert len(emerging_2024) == 1
    assert int(emerging_2024[0]["count_year"]) == 8
    assert int(emerging_2024[0]["count_prev_year"]) == 3
    assert int(emerging_2024[0]["delta"]) == 5
    assert emerging_2024[0]["direction"] == "fea_surrogate"

    stable_2024 = [r for r in rows
                   if r["tag"] == "stable_tag" and r["year"] == "2024"]
    assert stable_2024 == []


def test_a1_still_works(tmp_path):
    """Regression: Phase B did not break A1 outputs."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-01-01", [
        _paper(doi="10.1/a", direction="ai_bioprinting", priority="High",
               scorer_version="v3", tags=["bioprinting"]),
        _paper(doi="10.1/b", direction="fea_surrogate", priority="Medium",
               scorer_version="v1", tags=["should_be_ignored"]),
    ])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0
    # A1 artifacts unchanged.
    assert (out / "distribution_yearly.csv").exists()
    assert (out / "distribution_monthly.csv").exists()
    assert (out / "distribution_yearly.png").stat().st_size > 5_000
    assert (out / "distribution_priority_ratio.png").stat().st_size > 5_000
    # A1 yearly carries v1 + v3 as separate rows (Phase A contract).
    yearly_rows = _read_csv(out / "distribution_yearly.csv")
    versions = {r["scorer_version"] for r in yearly_rows}
    assert {"v1", "v3"} <= versions
    # A2 tag CSV exists and excludes v1 papers entirely.
    tag_rows = _read_csv(out / "tag_frequency_by_year_by_direction.csv")
    assert len(tag_rows) == 1
    assert tag_rows[0]["tag"] == "bioprinting"
    assert "should_be_ignored" not in {r["tag"] for r in tag_rows}


def test_hm_default_filters_low(tmp_path):
    """A2 default = High+Medium: Low/Exclude-only tags are absent; flag flips it back."""
    daily = tmp_path / "daily"
    out_hm = tmp_path / "out_hm"
    out_all = tmp_path / "out_all"

    _write_bucket(daily, "2024-01-01", [
        # Three papers carrying "low_only_tag" — all Low/Exclude. Under the HM
        # default they should contribute zero rows to the tag CSV.
        _paper(doi="10.1/lo1", direction="ai_bioprinting", priority="Low",
               scorer_version="v3", tags=["low_only_tag"]),
        _paper(doi="10.1/lo2", direction="ai_bioprinting", priority="Low",
               scorer_version="v3", tags=["low_only_tag"]),
        _paper(doi="10.1/exc", direction="ai_bioprinting", priority="Exclude",
               scorer_version="v3", tags=["low_only_tag"]),
        # A High paper carrying a different tag — should always be counted.
        _paper(doi="10.1/hi", direction="ai_bioprinting", priority="High",
               scorer_version="v3", tags=["hm_tag"]),
    ])

    # Default = HM only: low_only_tag must be absent, hm_tag present.
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out_hm),
    ])
    assert rc == 0
    tags_hm = {r["tag"] for r in _read_csv(
        out_hm / "tag_frequency_by_year_by_direction.csv")}
    assert "low_only_tag" not in tags_hm
    assert "hm_tag" in tags_hm

    # --include-all-priorities: low_only_tag must reappear.
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out_all),
        "--include-all-priorities",
    ])
    assert rc == 0
    rows_all = _read_csv(out_all / "tag_frequency_by_year_by_direction.csv")
    tags_all = {r["tag"] for r in rows_all}
    assert "low_only_tag" in tags_all
    assert "hm_tag" in tags_all
    # Count should match the three Low/Exclude papers.
    low_rows = [r for r in rows_all if r["tag"] == "low_only_tag"]
    assert len(low_rows) == 1
    assert int(low_rows[0]["count"]) == 3


def test_showdown_family_variants(tmp_path):
    """Widened family defs catch 'finite element simulation' and 'Fourier neural operator'."""
    daily = tmp_path / "daily"
    out = tmp_path / "out"
    _write_bucket(daily, "2024-06-01", [
        # FEM family — variant not in the OLD set, must now match.
        _paper(doi="10.1/fem-sim", direction="fea_surrogate", priority="High",
               scorer_version="v3", tags=["finite element simulation"]),
        _paper(doi="10.1/fem-mod", direction="fea_surrogate", priority="Medium",
               scorer_version="v3", tags=["finite element model"]),
        # NO/PINN family — substring rule on "neural operator" plus the PINN alias.
        _paper(doi="10.1/fno", direction="fea_surrogate", priority="High",
               scorer_version="v3", tags=["Fourier neural operator"]),
        _paper(doi="10.1/pinn", direction="fea_surrogate", priority="High",
               scorer_version="v3", tags=["PINN"]),
    ])
    rc = build_analytics.main([
        "--daily-dir", str(daily), "--out-dir", str(out),
    ])
    assert rc == 0

    # Reconstruct the yearly_tags Counter from the CSV and apply the same
    # aggregator the showdown renderer uses. This proves the widened defs
    # route the variants into the right families.
    rows = _read_csv(out / "tag_frequency_by_year_by_direction.csv")
    yearly_tags: Counter = Counter()
    for r in rows:
        yearly_tags[(r["year"], r["direction"], r["tag"])] = int(r["count"])

    fem_per_year, pinn_per_year = build_analytics.compute_showdown_aggregates(yearly_tags)
    assert fem_per_year["2024"] == 2, (
        f"FEM family should catch 'finite element simulation' + "
        f"'finite element model'; got {dict(fem_per_year)}"
    )
    assert pinn_per_year["2024"] == 2, (
        f"NO/PINN family should catch 'Fourier neural operator' + "
        f"canonicalized PINN; got {dict(pinn_per_year)}"
    )
    # Showdown PNG was rendered with non-trivial size.
    assert (out / "methodology_showdown.png").stat().st_size > 5_000
