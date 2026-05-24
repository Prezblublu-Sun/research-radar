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
        "llm": {
            "priority": priority,
            "summary_zh": {"motivation": "动机", "method": "方法"},
            "summary_en": {"motivation": "Motivation", "method": "Method"},
            "relevance_to_user": "Relevant because synthetic.",
            "tags": ["t1"],
            "key_terms": [],
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

    build_pages.build(docs, DIRECTIONS)
    return docs


def _article_priorities(html: str) -> list[str]:
    """All data-priority values on <article> tags, in document order."""
    return re.findall(r'<article class="paper"[^>]*data-priority="([^"]+)"', html)


# ---------------------------------------------------------------- D1

def test_v1_index_is_a_month_card_grid_with_pill_counts(built):
    idx = (built / "index.html").read_text(encoding="utf-8")
    # C1: index links to month pages via clickable month-cards, no flat dates.
    assert 'class="month-grid"' in idx
    assert '<a class="month-card" href="month-2024-12.html">' in idx
    assert "2024-12-10.html" not in idx  # the flat date list is gone
    # V1: pill components, not the old dc-h/dc-m spans. The fixture's only
    # month, 2024-12, has 2 High (12-09, 12-10), 1 Medium, 2 Low, 2 Exclude.
    assert "dc-h" not in idx and 'class="rui-daycount"' not in idx
    assert '<span class="pill pill--high">2H</span>' in idx
    assert '<span class="pill pill--medium">1M</span>' in idx
    assert '<span class="pill pill--low">2L</span>' in idx
    # Cross-corpus + curation entry points still linked from the header
    for href in ("high-priority.html", "medium-priority.html",
                 "my-marks.html", "my-promotes.html"):
        assert href in idx


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
    assert 'class="month-topbar__back" href="index.html"' in html
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

def test_d2_high_priority_page_contains_only_high(built):
    page = built / "high-priority.html"
    assert page.exists()
    html = page.read_text(encoding="utf-8")
    prios = _article_priorities(html)
    assert prios, "expected at least one High card"
    assert set(prios) == {"High"}
    assert "High Paper One" in html and "High Paper Two" in html
    assert "Medium Paper One" not in html
    assert "Low Paper One" not in html
    # newest-first ordering: 2024-12-10 card before the 2024-12-09 card
    assert html.index("High Paper One") < html.index("High Paper Two")


def test_d2_medium_priority_page_contains_only_medium(built):
    page = built / "medium-priority.html"
    assert page.exists()
    html = page.read_text(encoding="utf-8")
    prios = _article_priorities(html)
    assert prios and set(prios) == {"Medium"}
    assert "Medium Paper One" in html
    assert "High Paper One" not in html


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
    marks_pg = (built / "my-marks.html").read_text(encoding="utf-8")
    assert 'id="rui-export-marks"' in marks_pg


# ---------------------------------------------------------------- D5

def test_d5_every_card_has_promote_button_with_identity_key(built):
    html = (built / "2024-12-10.html").read_text(encoding="utf-8")
    articles = re.findall(r"<article class=\"paper\".*?</article>", html, re.S)
    assert articles
    for art in articles:
        assert 'class="rui-promote-btn"' in art
        assert "Send to lit-system" in art
        assert re.search(r'data-identity-key="doi:10\.1/\w+"', art)
    promo_pg = (built / "my-promotes.html").read_text(encoding="utf-8")
    assert 'id="rui-copy-promotes"' in promo_pg


# ---------------------------------------------------------------- assets

def test_static_bundle_copied_into_docs(built):
    assert (built / "radar-ui.js").exists()
    assert (built / "radar-ui.css").exists()
    js = (built / "radar-ui.js").read_text(encoding="utf-8")
    assert "radar:promote-queue" in js
    assert "radar:mark:" in js


# ---------------------------------------------------------------- ADR-0022
# Search index: per-year split + manifest, blob drops summary_en but
# keeps why_not_core and summary_zh.

SEARCH_INDEX_DISPLAY_FIELDS = {
    "date", "title", "authors", "venue", "direction", "direction_name",
    "priority", "relevance_level", "read_action", "source", "doi",
    "date_precision", "scorer_version", "blob",
}

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
            "key_terms": [],
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


def test_adr0022_search_index_writes_per_year_files_and_manifest(search_built):
    docs, total = search_built
    assert not (docs / "search-index.json").exists()
    manifest_path = docs / "search-index-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["years"] == ["2024", "2025", "2026"]
    assert manifest["counts"] == {"2024": 2, "2025": 1, "2026": 1}
    assert manifest["total"] == 4
    assert total == 4
    assert sum(manifest["counts"].values()) == manifest["total"]
    assert "generated_at" in manifest

    written = sorted(p.name for p in docs.glob("search-index-*.json")
                     if p.name != "search-index-manifest.json")
    assert written == [
        "search-index-2024.json",
        "search-index-2025.json",
        "search-index-2026.json",
    ]
    for year, expected in manifest["counts"].items():
        records = json.loads(
            (docs / f"search-index-{year}.json").read_text(encoding="utf-8"))
        assert isinstance(records, list)
        assert len(records) == expected
        for rec in records:
            assert rec["date"].startswith(year)


def test_adr0022_blob_drops_summary_en_keeps_why_not_core_and_summary_zh(search_built):
    docs, _ = search_built
    records = json.loads(
        (docs / "search-index-2024.json").read_text(encoding="utf-8"))
    assert records
    for rec in records:
        blob = rec["blob"]
        assert EN_ONLY_TOKEN.lower() not in blob
        assert WHY_NOT_TOKEN.lower() in blob
        assert ZH_ONLY_TOKEN in blob  # zh token isn't ASCII-affected by .lower()
        assert blob == blob.lower()   # still lowercased


def test_adr0022_search_index_display_fields_unchanged(search_built):
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
    assert sample["read_action"] == "Read"
    assert sample["scorer_version"] == "v3"
    assert sample["date_precision"] == "day"


def test_adr0022_search_page_loads_manifest_then_per_year_files(built):
    """The inline search JS should be manifest-driven, not a single fetch."""
    search_html = (built / "search.html").read_text(encoding="utf-8")
    assert "fetch('search-index.json')" not in search_html
    assert "fetch('search-index-manifest.json')" in search_html
    assert "search-index-' + y + '.json" in search_html


def test_adr0022_build_emits_per_year_index_through_full_build(built):
    """The full build pipeline (build_pages.build) writes the new files."""
    assert not (built / "search-index.json").exists()
    assert (built / "search-index-manifest.json").exists()
    # fixture spans 2024 only
    assert (built / "search-index-2024.json").exists()
