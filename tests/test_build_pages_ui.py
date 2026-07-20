"""Tests for ADR-0016 client-side curation UI affordances (D1-D5).

All five affordances are rendered server-side by render/build_pages.py into
static HTML + a copied JS/CSS bundle; behaviour itself is client-side and not
exercised here. These tests assert the *markup contract* the JS depends on:

  D1  index.html is a month-card grid (C1) with .pill aggregate counts
      (V1); month-YYYY-MM.html is a day-card grid (V2) where High/Medium
      days carry the V3 enrichment (★, authors, direction-pill,
      motivation, <details>) and Low/Exclude-only days stay bare
  D2  high-priority.html / medium-priority.html exist and are single-priority
  D3  each daily page has the priority filter bar + data-priority on cards
  D4  every paper card carries mark + note controls with its identity key
  D5  every paper card carries a promote-to-lit-system button + identity key

Run with:
    pytest tests/test_build_pages_ui.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from render import build_pages  # noqa: E402

DIRECTIONS = {
    "fea_surrogate": {"display_name": "FEA & Surrogate", "color": "#D85A30"},
    "ai_bioprinting": {"display_name": "AI Bioprinting", "color": "#7F77DD"},
}


def _paper(*, doi: str, priority: str, title: str,
           direction: str = "fea_surrogate", date: str,
           authors: list[str] | None = None) -> dict:
    return {
        "source": "openalex",
        "doi": doi,
        "title": title,
        "abstract": "Synthetic abstract.",
        "authors": authors if authors is not None else ["A. Author", "B. Builder"],
        "venue": "Test Venue",
        "year": int(date[:4]),
        "date": date,
        "date_precision": "day",
        "url": f"https://doi.org/{doi}",
        "direction": direction,
        "direction_name": DIRECTIONS[direction]["display_name"],
        "scorer_version": "v3",
        "first_seen_at": "2024-12-12T08:00:00Z",
        "llm": {
            "priority": priority,
            "summary_zh": {"motivation": "动机", "method": "方法"},
            "summary_en": {"motivation": "Motivation", "method": "Method"},
            "relevance_to_user": "Relevant because synthetic.",
            "tags": ["t1"],
            "key_terms": [{"en": "surrogate model", "zh": "代理模型"}],
            "flags": {},
        },
    }


def _write_v2(daily_dir: pathlib.Path, date_str: str, papers: list[dict]) -> None:
    daily_dir.mkdir(parents=True, exist_ok=True)
    pc: dict[str, int] = {}
    for p in papers:
        pr = p["llm"]["priority"]
        pc[pr] = pc.get(pr, 0) + 1
    (daily_dir / f"{date_str}.json").write_text(
        json.dumps({
            "schema_version": "v2",
            "date": date_str,
            "date_precision": "day",
            "papers": papers,
            "counts": {
                "fetched_total": len(papers),
                "scored": len(papers),
                "priority_counts": pc or None,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture()
def built(tmp_path: pathlib.Path) -> pathlib.Path:
    """Build a small corpus and return the docs/ dir."""
    docs = tmp_path / "docs"
    daily = tmp_path / "data" / "daily"

    # Day with High + Medium + Low + Exclude
    _write_v2(daily, "2024-12-10", [
        _paper(doi="10.1/h1", priority="High", title="High Paper One",
               date="2024-12-10",
               authors=["Wei Sun", "Jane Doe", "Bob Lee", "Extra Person"]),
        _paper(doi="10.1/m1", priority="Medium", title="Medium Paper One",
               direction="ai_bioprinting", date="2024-12-10"),
        _paper(doi="10.1/l1", priority="Low", title="Low Paper One",
               date="2024-12-10"),
        _paper(doi="10.1/x1", priority="Exclude", title="Exclude Paper One",
               date="2024-12-10"),
    ])
    # Day with only Low + Exclude -> "low quality" day
    _write_v2(daily, "2024-12-11", [
        _paper(doi="10.1/l2", priority="Low", title="Low Paper Two",
               date="2024-12-11"),
        _paper(doi="10.1/x2", priority="Exclude", title="Exclude Paper Two",
               date="2024-12-11"),
    ])
    # A second high paper on an earlier date (D2 ordering)
    _write_v2(daily, "2024-12-09", [
        _paper(doi="10.1/h2", priority="High", title="High Paper Two",
               date="2024-12-09"),
    ])

    manifests = tmp_path / "data" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "2024-12-12.json").write_text(json.dumps({
        "run_status": "success", "quality_flags": [],
        "counts": {"priority_counts": {"High": 2, "Medium": 1}},
    }), encoding="utf-8")

    build_pages.build(docs, DIRECTIONS)
    return docs


def _article_priorities(html: str) -> list[str]:
    """All data-priority values on <article> tags, in document order."""
    return re.findall(r'<article class="paper"[^>]*data-priority="([^"]+)"', html)


def test_legacy_null_priority_renders_as_low_instead_of_skipping_page():
    paper = _paper(doi="10.1/null", priority="Low", title="Legacy record",
                   date="2021-01-01")
    paper["llm"]["priority"] = None
    card = build_pages._paper_card(paper, "#D85A30")
    stats = build_pages._stats_row([paper], DIRECTIONS)
    assert 'data-priority="Low"' in card
    assert 'priority--low' in card
    assert "论文总数" in stats


# ---------------------------------------------------------------- D1

def test_workbench_root_and_archive_month_grid(built):
    idx = (built / "index.html").read_text(encoding="utf-8")
    assert "最近 7 次运行" in idx
    assert "2024-12-12 新发现" in idx
    assert 'class="run-section"' in idx
    assert "High Paper One" in idx and "Medium Paper One" in idx
    assert 'aria-current="page" class="site-nav__link is-active">今日' in idx

    archive = (built / "archive.html").read_text(encoding="utf-8")
    assert 'class="month-grid"' in archive
    assert '<a class="month-card" href="month-2024-12.html">' in archive
    assert '<span class="pill pill--high">2H</span>' in archive
    assert '<span class="pill pill--medium">1M</span>' in archive
    assert '<span class="pill pill--low">2L</span>' in archive
    for href in ("queue.html", "search.html", "library.html", "archive.html"):
        assert href in archive


def _articles(html: str) -> list[str]:
    return re.findall(r'<article class="day-card.*?</article>', html, re.S)


def test_v2_v3_month_page_renders_enriched_day_cards(built):
    page = built / "month-2024-12.html"
    assert page.exists()
    html = page.read_text(encoding="utf-8")

    # V2: a responsive grid of day-card articles, newest first.
    assert 'class="day-grid"' in html
    assert '<article class="day-card' in html
    assert "<ul>" not in html  # the old list markup is gone
    assert html.index("2024-12-11.html") < html.index("2024-12-09.html")
    # V2: month topbar back-to-calendar nav
    assert 'class="month-topbar__back" href="archive.html"' in html
    # V1: pill counts on the cards, no legacy dc-* markup
    assert '<span class="pill pill--high">1H</span>' in html
    assert "dc-h" not in html

    cards = _articles(html)
    high = next(c for c in cards if "2024-12-10.html" in c)
    low = next(c for c in cards if "2024-12-11.html" in c)

    # V3: a High day card carries the ★ marker and a <details> expander
    assert "day-card--low-quality" not in high.split(">")[0]
    assert "★" in high
    assert "<details class=\"day-card__expand\">" in high
    # V3: motivation block + direction-pill on the meta line
    assert 'class="day-card__motivation"' in high
    assert 'class="direction-pill"' in high
    assert "FEA &amp; Surrogate" in high  # direction_name, escaped
    # V3: >2 authors render "First, Second et al."
    assert "Wei Sun, Jane Doe et al." in high
    assert "Bob Lee" not in high

    # Low/Exclude-only day: bare low-quality card, no enrichment.
    assert 'class="day-card day-card--low-quality"' in low
    assert 'class="day-card__motivation"' not in low
    assert "day-card__top" not in low
    assert "★" not in low


# ---------------------------------------------------------------- D2

def test_d2_high_queue_shard_and_compatibility_redirect(built):
    redirect = (built / "high-priority.html").read_text(encoding="utf-8")
    assert "queue.html?priority=High" in redirect
    records = json.loads(
        (built / "queue-high-2024.json").read_text(encoding="utf-8")
    )
    assert records and {record["priority"] for record in records} == {"High"}
    assert {record["title"] for record in records} == {
        "High Paper One", "High Paper Two",
    }


def test_d2_medium_queue_shard_and_manifest(built):
    redirect = (built / "medium-priority.html").read_text(encoding="utf-8")
    assert "queue.html?priority=Medium" in redirect
    records = json.loads(
        (built / "queue-medium-2024.json").read_text(encoding="utf-8")
    )
    assert [record["title"] for record in records] == ["Medium Paper One"]
    manifest = json.loads(
        (built / "queue-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["priorities"]["High"]["total"] == 2
    assert manifest["priorities"]["Medium"]["total"] == 1


# ---------------------------------------------------------------- D3

def test_d3_daily_page_has_priority_filter_bar_and_data_priority(built):
    html = (built / "2024-12-10.html").read_text(encoding="utf-8")
    assert 'id="rui-priority-filter"' in html
    assert 'class="rui-pf-cb"' in html
    for prio in ("High", "Medium", "Low", "Exclude"):
        assert f'value="{prio}"' in html
    # every card exposes its priority for the client-side filter
    assert set(_article_priorities(html)) == {"High", "Medium", "Low", "Exclude"}
    # external bundle referenced, not inlined
    assert '<script src="radar-ui.js" defer></script>' in html
    assert '<link rel="stylesheet" href="radar-ui.css">' in html


# ---------------------------------------------------------------- D4

def test_d4_every_card_has_mark_and_note_controls_with_identity_key(built):
    html = (built / "2024-12-10.html").read_text(encoding="utf-8")
    articles = re.findall(r"<article class=\"paper\".*?</article>", html, re.S)
    assert len(articles) == 4
    for art in articles:
        assert 'data-identity-key="doi:10.1/' in art
        assert 'class="rui-mark-radio"' in art
        # all four mark states present
        for state in ("to-read", "read", "interesting", "ignore"):
            assert f'value="{state}"' in art
        assert 'class="rui-note-btn"' in art
        assert 'class="rui-note-ta"' in art
    # daily-page "filter to my marks" bar present
    assert 'id="rui-marks-filter"' in html
    assert 'class="rui-mf-cb"' in html
    # D4 export escape-hatch page exists
    marks_pg = (built / "library.html").read_text(encoding="utf-8")
    assert 'id="rui-export-marks"' in marks_pg
    assert "library.html#marks" in (built / "my-marks.html").read_text()


# ---------------------------------------------------------------- D5

def test_d5_every_card_has_promote_button_with_identity_key(built):
    html = (built / "2024-12-10.html").read_text(encoding="utf-8")
    articles = re.findall(r"<article class=\"paper\".*?</article>", html, re.S)
    assert articles
    for art in articles:
        assert 'class="rui-promote-btn"' in art
        assert "发送到 lit-system" in art
        assert re.search(r'data-identity-key="doi:10\.1/\w+"', art)
    promo_pg = (built / "library.html").read_text(encoding="utf-8")
    assert 'id="rui-copy-promotes"' in promo_pg


# ---------------------------------------------------------------- assets

def test_static_bundle_copied_into_docs(built):
    assert (built / "radar-ui.js").exists()
    assert (built / "radar-ui.css").exists()
    assert (built / "radar-queue.js").exists()
    assert (built / "radar-search.js").exists()
    assert (built / "radar-search-worker.js").exists()
    js = (built / "radar-ui.js").read_text(encoding="utf-8")
    assert "radar:promote-queue" in js
    assert "radar:mark:" in js


# ---------------------------------------------------------------- ADR-0027
# Search index: metadata loads progressively; abstract and Chinese summaries
# are held in opt-in, year-scoped deep shards.

SEARCH_INDEX_DISPLAY_FIELDS = {
    "identity_key", "date", "title", "authors", "venue",
    "direction", "direction_name", "priority", "relevance_level",
    "tags", "term",
}
SEARCH_DEEP_FIELDS = {"identity_key", "deep_blob"}

# Distinctive tokens we can search for to assert blob composition.
EN_ONLY_TOKEN = "zogglefritz"   # only in summary_en
ZH_ONLY_TOKEN = "啧噬咕"         # only in summary_zh
WHY_NOT_TOKEN = "snorgflarble"  # only in why_not_core


def _search_paper(*, doi: str, date: str, year_unique: str) -> dict:
    return {
        "source": "openalex",
        "doi": doi,
        "title": f"Paper {year_unique}",
        "abstract": "Abstract text.",
        "authors": ["A. Author", "B. Builder"],
        "venue": "Test Venue",
        "year": int(date[:4]),
        "date": date,
        "date_precision": "day",
        "url": f"https://doi.org/{doi}",
        "direction": "fea_surrogate",
        "direction_name": "FEA & Surrogate",
        "scorer_version": "v3",
        "llm": {
            "priority": "High",
            "relevance_level": "Direct",
            "read_action": "Read",
            "summary_zh": {"motivation": ZH_ONLY_TOKEN, "method": "方法"},
            "summary_en": {"motivation": EN_ONLY_TOKEN, "method": "Method"},
            "why_not_core": WHY_NOT_TOKEN,
            "relevance_to_user": "Relevant because synthetic.",
            "tags": ["t1"],
            "key_terms": [{"en": "surrogate model", "zh": "代理模型"}],
            "flags": {},
        },
    }


@pytest.fixture()
def search_built(tmp_path: pathlib.Path) -> tuple[pathlib.Path, int]:
    """Run _build_search_index on a multi-year fixture; return (docs, total)."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    daily = tmp_path / "data" / "daily"
    _write_v2(daily, "2024-12-10", [
        _search_paper(doi="10.1/a", date="2024-12-10", year_unique="2024-a"),
        _search_paper(doi="10.1/b", date="2024-12-10", year_unique="2024-b"),
    ])
    _write_v2(daily, "2025-06-01", [
        _search_paper(doi="10.2/a", date="2025-06-01", year_unique="2025-a"),
    ])
    _write_v2(daily, "2026-05-23", [
        _search_paper(doi="10.3/a", date="2026-05-23", year_unique="2026-a"),
    ])
    total = build_pages._build_search_index(docs, tmp_path / "data")
    return docs, total


def test_adr0027_search_index_writes_meta_deep_files_and_manifest(search_built):
    docs, total = search_built
    assert not (docs / "search-index.json").exists()
    manifest_path = docs / "search-index-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["years"] == ["2026", "2025", "2024"]
    assert manifest["counts"] == {"2024": 2, "2025": 1, "2026": 1}
    assert manifest["deep_counts"] == manifest["counts"]
    assert manifest["total"] == 4
    assert total == 4
    assert sum(manifest["counts"].values()) == manifest["total"]
    assert manifest["generated_at"] == "2026-05-23T00:00:00Z"

    written = sorted(p.name for p in docs.glob("search-index-*.json")
                     if p.name != "search-index-manifest.json")
    assert written == [
        "search-index-2024.json",
        "search-index-2025.json",
        "search-index-2026.json",
    ]
    deep_written = sorted(p.name for p in docs.glob("search-deep-*.json"))
    assert deep_written == [
        "search-deep-2024.json",
        "search-deep-2025.json",
        "search-deep-2026.json",
    ]
    for year, expected in manifest["counts"].items():
        records = json.loads(
            (docs / f"search-index-{year}.json").read_text(encoding="utf-8"))
        assert isinstance(records, list)
        assert len(records) == expected
        for rec in records:
            assert rec["date"].startswith(year)


def test_adr0027_metadata_shard_excludes_deep_content(search_built):
    docs, _ = search_built
    records = json.loads(
        (docs / "search-index-2024.json").read_text(encoding="utf-8"))
    assert records
    serialized = json.dumps(records, ensure_ascii=False).lower()
    assert EN_ONLY_TOKEN.lower() not in serialized
    assert WHY_NOT_TOKEN.lower() not in serialized
    assert ZH_ONLY_TOKEN not in serialized
    assert "abstract text" not in serialized
    assert "paper 2024" in serialized


def test_adr0027_deep_blob_keeps_chinese_summary_and_why_not(search_built):
    docs, _ = search_built
    records = json.loads(
        (docs / "search-deep-2024.json").read_text(encoding="utf-8"))
    assert records
    for rec in records:
        assert set(rec) == SEARCH_DEEP_FIELDS
        blob = rec["deep_blob"]
        assert EN_ONLY_TOKEN.lower() not in blob
        assert WHY_NOT_TOKEN.lower() in blob
        assert ZH_ONLY_TOKEN in blob
        assert "abstract text" in blob


def test_adr0027_search_index_display_fields_are_stable(search_built):
    docs, _ = search_built
    records = json.loads(
        (docs / "search-index-2025.json").read_text(encoding="utf-8"))
    assert records
    sample = records[0]
    assert set(sample.keys()) == SEARCH_INDEX_DISPLAY_FIELDS
    assert sample["date"] == "2025-06-01"
    assert sample["direction"] == "fea_surrogate"
    assert sample["direction_name"] == "FEA & Surrogate"
    assert sample["priority"] == "High"
    assert sample["relevance_level"] == "Direct"
    assert sample["term"] == "surrogate model · 代理模型"


def test_adr0027_search_page_uses_external_progressive_runtime(built):
    search_html = (built / "search.html").read_text(encoding="utf-8")
    assert "fetch('search-index.json')" not in search_html
    assert 'src="radar-search.js"' in search_html
    assert 'id="search-deep-toggle"' in search_html
    assert 'id="search-deep-year"' in search_html
    assert "search-index-manifest.json" not in search_html


def test_adr0027_build_emits_per_year_indexes_through_full_build(built):
    """The full build pipeline (build_pages.build) writes the new files."""
    assert not (built / "search-index.json").exists()
    assert (built / "search-index-manifest.json").exists()
    # fixture spans 2024 only
    assert (built / "search-index-2024.json").exists()
    assert (built / "search-deep-2024.json").exists()


# ---------------------------------------------------------------- canonical corpus view

def test_public_pages_and_search_suppress_cross_bucket_duplicate_identity(tmp_path):
    docs = tmp_path / "docs"
    daily = tmp_path / "data" / "daily"
    older_bucket = _paper(
        doi="10.1/duplicate", priority="High", title="Later observation",
        date="2024-01-10",
    )
    older_bucket["first_seen_at"] = "2026-06-01T00:00:00Z"
    first_seen = _paper(
        doi="10.1/duplicate", priority="High", title="Canonical observation",
        date="2024-02-10",
    )
    first_seen["first_seen_at"] = "2026-05-01T00:00:00Z"
    _write_v2(daily, "2024-01-10", [older_bucket])
    _write_v2(daily, "2024-02-10", [first_seen])

    build_pages.build(docs, DIRECTIONS)

    high = json.loads(
        (docs / "queue-high-2024.json").read_text(encoding="utf-8")
    )
    assert [record["identity_key"] for record in high] == [
        "doi:10.1/duplicate"
    ]
    assert high[0]["title"] == "Canonical observation"

    stale_day = (docs / "2024-01-10.html").read_text(encoding="utf-8")
    assert 'data-identity-key="doi:10.1/duplicate"' not in stale_day

    manifest = json.loads(
        (docs / "search-index-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["raw_total"] == 2
    assert manifest["unique_total"] == 1
    assert manifest["duplicates_suppressed"] == 1
    assert manifest["total"] == 1


def test_identityless_records_remain_distinct_across_ui_indexes(tmp_path):
    docs = tmp_path / "docs"
    daily = tmp_path / "data" / "daily"
    first = _paper(doi="", priority="High", title="Same title",
                   date="2024-03-01")
    second = _paper(doi="", priority="High", title="Same title",
                    date="2024-03-01")
    _write_v2(daily, "2024-03-01", [first, second])

    build_pages.build(docs, DIRECTIONS)

    search = json.loads(
        (docs / "search-index-2024.json").read_text(encoding="utf-8")
    )
    deep = json.loads(
        (docs / "search-deep-2024.json").read_text(encoding="utf-8")
    )
    queue = json.loads(
        (docs / "queue-high-2024.json").read_text(encoding="utf-8")
    )
    identities = [record["identity_key"] for record in search]
    assert len(search) == len(deep) == len(queue) == 2
    assert len(set(identities)) == 2
    assert all(identity.startswith("noid:") for identity in identities)
    assert set(identities) == {record["identity_key"] for record in deep}
    assert set(identities) == {record["identity_key"] for record in queue}
    daily_html = (docs / "2024-03-01.html").read_text(encoding="utf-8")
    for identity in identities:
        assert f'data-identity-key="{identity}"' in daily_html


def test_workbench_uses_latest_seven_valid_runs_and_excludes_failed(tmp_path):
    docs = tmp_path / "docs"
    daily = tmp_path / "data" / "daily"
    papers = []
    for day in range(1, 10):
        run_date = f"2024-07-{day:02d}"
        paper = _paper(
            doi=f"10.1/run-{day}", priority="High",
            title=f"Seen on {run_date}", date="2024-06-01",
        )
        paper["first_seen_at"] = run_date + "T06:00:00Z"
        papers.append(paper)
    _write_v2(daily, "2024-06-01", papers)

    manifests = tmp_path / "data" / "manifests"
    manifests.mkdir(parents=True)
    for day in range(1, 10):
        status = "failed" if day == 9 else "success"
        (manifests / f"2024-07-{day:02d}.json").write_text(
            json.dumps({"run_status": status, "quality_flags": []}),
            encoding="utf-8",
        )

    build_pages.build(docs, DIRECTIONS)
    index = (docs / "index.html").read_text(encoding="utf-8")

    assert "Seen on 2024-07-09" not in index  # failed run
    assert "Seen on 2024-07-01" not in index  # eighth valid run
    for day in range(2, 9):
        assert f"Seen on 2024-07-{day:02d}" in index
