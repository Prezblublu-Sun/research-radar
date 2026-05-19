"""Tests for ADR-0016 client-side curation UI affordances (D1-D5).

All five affordances are rendered server-side by render/build_pages.py into
static HTML + a copied JS/CSS bundle; behaviour itself is client-side and not
exercised here. These tests assert the *markup contract* the JS depends on:

  D1  index.html priority-count badges + low-quality day class
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
           direction: str = "fea_surrogate", date: str) -> dict:
    return {
        "source": "openalex",
        "doi": doi,
        "title": title,
        "abstract": "Synthetic abstract.",
        "authors": ["A. Author", "B. Builder"],
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
               date="2024-12-10"),
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

def test_d1_index_has_priority_count_badges_and_low_quality_class(built):
    idx = (built / "index.html").read_text(encoding="utf-8")
    assert 'class="rui-daycount"' in idx
    # 2024-12-10 had 1H 1M 1L 1X
    assert '<span class="dc-h">1H</span>' in idx
    assert '<span class="dc-m">1M</span>' in idx
    assert '<span class="dc-l">1L</span>' in idx
    # The Low+Exclude-only day is greyed, not hidden (ADR-0016 Q1)
    assert 'class="day-low-quality"' in idx
    assert "2024-12-11.html" in idx  # still listed, not removed
    # Cross-corpus + curation entry points linked from the header
    for href in ("high-priority.html", "medium-priority.html",
                 "my-marks.html", "my-promotes.html"):
        assert href in idx


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
