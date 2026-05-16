"""Tests for pipeline/weekly_report.py under the ADR-0015 v2 corpus.

Covers the Phase 4.3 migration:
  - daily JSONs are now v2 dicts ({schema_version, date, papers, ...}),
    not bare lists -- collect_week_papers must unwrap them
  - "weekly" means *published this week*: filter on paper["date"]
    (decision D9), NOT paper["first_seen_at"]
  - month/year date_precision papers are still included (no precision
    filtering yet -- that is Phase 4.4 UI work)

Run with:
    pytest tests/test_weekly_report.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import weekly_report as wr  # noqa: E402


def _make_paper(*, doi: str, priority: str = "High",
                date: str, first_seen_at: str = "2099-01-01T00:00:00Z",
                date_precision: str = "day") -> dict:
    return {
        "source": "openalex",
        "doi": doi,
        "title": f"Paper {doi}",
        "authors": ["A. Author"],
        "venue": "Test Venue",
        "year": int(date[:4]),
        "date": date,
        "date_precision": date_precision,
        "first_seen_at": first_seen_at,
        "scorer_version": "v3",
        "direction": "fea_surrogate",
        "direction_name": "FEA & Surrogate Modelling",
        "cited_by_count": 0,
        "llm": {"priority": priority, "summary_zh": {}, "relevance_to_user": ""},
    }


def _write_v2(daily_dir: pathlib.Path, date_str: str, papers: list[dict],
              date_precision: str = "day") -> None:
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f"{date_str}.json").write_text(json.dumps({
        "schema_version": "v2",
        "date": date_str,
        "date_precision": date_precision,
        "papers": papers,
        "counts": {"total": len(papers)},
    }, ensure_ascii=False))


@pytest.fixture
def patched_data_dir(tmp_path, monkeypatch):
    """Point weekly_report at a temp data/ tree."""
    data_dir = tmp_path / "data"
    (data_dir / "daily").mkdir(parents=True)
    monkeypatch.setattr(wr, "DATA_DIR", data_dir)
    return data_dir


# A reference week. 2026-05-13 is a Wednesday; its ISO week is Mon..Sun.
END = dt.date(2026, 5, 13)
MONDAY, SUNDAY = wr._week_dates(END)


def test_reads_v2_dict_shape(patched_data_dir):
    """A v2 dict-wrapped daily file is unwrapped, not skipped as 'not a list'."""
    _write_v2(patched_data_dir / "daily", MONDAY.isoformat(), [
        _make_paper(doi="10.1/a", date=MONDAY.isoformat()),
        _make_paper(doi="10.1/b", date=MONDAY.isoformat(), priority="Medium"),
    ])
    papers, stats = wr.collect_week_papers(END)
    assert {p["doi"] for p in papers} == {"10.1/a", "10.1/b"}
    assert stats["total_papers"] == 2
    assert stats["days_with_data"] == 1
    assert stats["priority_totals"]["High"] == 1
    assert stats["priority_totals"]["Medium"] == 1


def test_v1_list_shape_still_supported(patched_data_dir):
    """A stray pre-migration v1 list file still works."""
    daily = patched_data_dir / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / f"{MONDAY.isoformat()}.json").write_text(
        json.dumps([_make_paper(doi="10.1/legacy", date=MONDAY.isoformat())])
    )
    papers, stats = wr.collect_week_papers(END)
    assert [p["doi"] for p in papers] == ["10.1/legacy"]
    assert stats["total_papers"] == 1


def test_filters_on_publication_date_not_first_seen_at(patched_data_dir):
    """D9: window membership keys on paper['date'], not first_seen_at.

    The bucket filename is in-window, but we put one paper whose own
    publication date is OUTSIDE the week (it should be dropped) and one
    whose date is in-window but whose first_seen_at is years away (kept).
    """
    out_of_week = (SUNDAY + dt.timedelta(days=10)).isoformat()
    _write_v2(patched_data_dir / "daily", MONDAY.isoformat(), [
        _make_paper(doi="10.1/in-window",
                    date=MONDAY.isoformat(),
                    first_seen_at="2020-01-01T00:00:00Z"),
        _make_paper(doi="10.1/out-of-window",
                    date=out_of_week,
                    first_seen_at=f"{MONDAY.isoformat()}T00:00:00Z"),
    ])
    papers, stats = wr.collect_week_papers(END)
    dois = {p["doi"] for p in papers}
    assert "10.1/in-window" in dois
    assert "10.1/out-of-window" not in dois
    assert stats["total_papers"] == 1


def test_month_and_year_precision_papers_included(patched_data_dir):
    """D9c: no date_precision filtering yet -- month/year still counted."""
    mid_week = (MONDAY + dt.timedelta(days=2)).isoformat()
    _write_v2(patched_data_dir / "daily", mid_week, [
        _make_paper(doi="10.1/day",   date=mid_week, date_precision="day"),
        _make_paper(doi="10.1/month", date=mid_week, date_precision="month"),
        _make_paper(doi="10.1/year",  date=mid_week, date_precision="year"),
    ], date_precision="month")
    papers, stats = wr.collect_week_papers(END)
    assert {p["doi"] for p in papers} == {"10.1/day", "10.1/month", "10.1/year"}
    assert stats["total_papers"] == 3


def test_filter_top_picks_keeps_high_medium_only(patched_data_dir):
    papers = [
        _make_paper(doi="10.1/h", date=MONDAY.isoformat(), priority="High"),
        _make_paper(doi="10.1/m", date=MONDAY.isoformat(), priority="Medium"),
        _make_paper(doi="10.1/l", date=MONDAY.isoformat(), priority="Low"),
    ]
    by_dir = wr.filter_top_picks(papers)
    kept = {p["doi"] for ps in by_dir.values() for p in ps}
    assert kept == {"10.1/h", "10.1/m"}
