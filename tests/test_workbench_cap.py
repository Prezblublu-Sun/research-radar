"""ADR-0027 addendum: the workbench excludes backfill-attributed papers and
embeds a bounded number of cards per run.

Run with:
    pytest tests/test_workbench_cap.py
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import v2_schema as v2  # noqa: E402
from render import build_pages  # noqa: E402

DIRECTIONS = {
    "fea_surrogate": {"display_name": "FEA & Surrogate", "color": "#D85A30"},
}


def _paper(doi: str, priority: str, title: str, first_seen: str,
           date: str = "2024-06-01") -> dict:
    return {
        "source": "openalex", "doi": doi, "title": title,
        "abstract": "Synthetic abstract.", "authors": ["A. Author"],
        "venue": "Test Venue", "year": int(date[:4]), "date": date,
        "date_precision": "day", "url": f"https://doi.org/{doi}",
        "direction": "fea_surrogate", "direction_name": "FEA & Surrogate",
        "scorer_version": "v3", "schema_version": "v2",
        "first_seen_at": first_seen + "T06:00:00Z",
        "llm": {"priority": priority, "relevance_level": "Direct",
                "summary_zh": {"motivation": "动机"}, "summary_en": {"motivation": "M"},
                "relevance_to_user": "Relevant.", "tags": ["t"], "key_terms": [],
                "flags": {}},
    }


def _site(tmp_path, papers, run_date, discovery=None):
    data = tmp_path / "data"
    daily = data / "daily"
    daily.mkdir(parents=True)
    v2.atomic_write_json(daily / "2024-06-01.json", v2.build_v2_file("2024-06-01", papers))
    manifests = data / "manifests"
    manifests.mkdir()
    (manifests / f"{run_date}.json").write_text(
        json.dumps({"run_status": "success", "quality_flags": []}), encoding="utf-8")
    if discovery is not None:
        logs = data / "discovery_log"
        logs.mkdir()
        (logs / f"{run_date}.json").write_text(json.dumps(discovery), encoding="utf-8")
    docs = tmp_path / "docs"
    build_pages.build(docs, DIRECTIONS, data_dir=data, sharded_daily=True)
    return (docs / "index.html").read_text(encoding="utf-8")


def _card_count(html: str) -> int:
    return html.count('<article class="paper"')


def test_backfill_attributed_papers_leave_the_workbench(tmp_path):
    run = "2024-07-05"
    papers = [
        _paper("10.1/daily-1", "High", "Daily discovery", run),
        _paper("10.1/backfill-1", "High", "Backfilled one", run),
        _paper("10.1/backfill-2", "Medium", "Backfilled two", run),
    ]
    discovery = [
        {"doi_or_arxiv_id": "doi:10.1/daily-1", "first_seen_at": run, "run_type": "daily"},
        {"doi_or_arxiv_id": "doi:10.1/backfill-1", "first_seen_at": run,
         "run_type": "historical_backfill"},
        {"doi_or_arxiv_id": "doi:10.1/backfill-2", "first_seen_at": run,
         "run_type": "historical_backfill"},
    ]
    index = _site(tmp_path, papers, run, discovery)

    assert "Daily discovery" in index
    assert "Backfilled one" not in index and "Backfilled two" not in index
    assert "另有 2 篇由历史回填入库" in index
    assert _card_count(index) == 1


def test_without_a_discovery_log_nothing_is_excluded(tmp_path):
    run = "2024-07-05"
    papers = [_paper(f"10.1/p{i}", "High", f"Paper {i}", run) for i in range(3)]
    index = _site(tmp_path, papers, run, discovery=None)
    assert _card_count(index) == 3
    assert "历史回填" not in index


def test_cards_per_run_are_capped_with_high_and_medium_first(tmp_path):
    run = "2024-07-05"
    cap = build_pages.WORKBENCH_RUN_CARD_CAP
    papers = (
        [_paper(f"10.1/high-{i}", "High", f"High {i:03d}", run) for i in range(5)]
        + [_paper(f"10.1/low-{i}", "Low", f"Low {i:03d}", run) for i in range(cap + 20)]
    )
    index = _site(tmp_path, papers, run)

    assert _card_count(index) == cap
    for i in range(5):
        assert f"High {i:03d}" in index
    assert f"本次运行共 {cap + 25} 篇，首页只内嵌优先级最高的 {cap} 篇" in index
    # The counts badge still describes the whole run.
    assert "5H" in index


def test_small_runs_are_untouched(tmp_path):
    run = "2024-07-05"
    papers = [_paper(f"10.1/p{i}", "Medium", f"Paper {i}", run) for i in range(12)]
    index = _site(tmp_path, papers, run)
    assert _card_count(index) == 12
    assert "首页只内嵌" not in index
    assert 'class="run-note"' not in index
