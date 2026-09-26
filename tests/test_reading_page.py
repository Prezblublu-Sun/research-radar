"""ADR-0016 addendum: the reading-list page (full cards for locally marked
papers) is generated, linked, shipped with its bundle, and exempt from the
daily-page visibility filters.

Run with:
    pytest tests/test_reading_page.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"


def test_reading_page_shell_has_the_controls_and_bundle():
    html = build_pages._render_reading_page()
    for needle in (
        build_pages._script("radar-reading.js"),
        build_pages._script("radar-card.js"),
        'data-rui-no-filter="1"',
        'id="reading-state"', 'data-state="to-read"', 'data-state="read"',
        'data-state="ignore"', 'data-state="note"', 'id="reading-tag"',
        'data-state="all"',
        'id="reading-query"', 'id="reading-sort"', 'id="reading-copy"',
        'id="reading-status"', 'id="reading-results" class="paper-grid"',
        'id="reading-pagination"', 'id="reading-prev"', 'id="reading-next"',
        'id="reading-page"', 'id="reading-page-total"',
        'href="library.html#marks"',
    ):
        assert needle in html, needle
    assert 'href="reading.html" aria-current="page"' in html


def test_every_page_navigation_links_to_the_reading_list():
    nav = build_pages._site_nav("today")
    assert 'href="reading.html"' in nav and "阅读清单" in nav
    # Order: 资料库 → 阅读清单 → 归档.
    assert nav.index('href="library.html"') < nav.index('href="reading.html"') < nav.index('href="archive.html"')
    assert 'href="reading.html"' in build_pages._render_library_page()


def test_bundle_is_shipped_and_copied(tmp_path):
    assert (STATIC / "radar-reading.js").exists()
    build_pages._copy_static_assets(tmp_path)
    assert (tmp_path / "radar-reading.js").read_text(encoding="utf-8").startswith("/* Reading list")


def test_reading_bundle_uses_the_shared_contracts():
    js = (STATIC / "radar-reading.js").read_text(encoding="utf-8")
    for contract in (
        'localStorage.key(', '"radar:mark:"',          # ADR-0016 storage keys
        '"data/day/"', '/manifest.json', 'anchor_pages', '/page-',  # ADR-0028 shards
        'RadarCard.buildCard', 'RadarUI.hydrate',       # shared renderer + hydration
        'search.html?q=',                               # fallback for unresolved marks
        'navigator.clipboard',                          # Markdown export
    ):
        assert contract in js, contract
    # Anchor derivation must match build_pages._anchor_id (non [A-Za-z0-9_-] → '-').
    assert re.search(r'replace\(/\[\^A-Za-z0-9_-\]/g, "-"\)', js)
    assert "innerHTML" not in js  # DOM-safe like the other bundles


def test_anchor_derivation_matches_the_server():
    js = (STATIC / "radar-reading.js").read_text(encoding="utf-8")
    assert 'replace(/[^A-Za-z0-9_-]/g, "-")' in js
    assert build_pages._anchor_id("arxiv:2609.10983v1") == "arxiv-2609-10983v1"
    assert build_pages._anchor_id("doi:10.1016/j.x.2026.1") == "doi-10-1016-j-x-2026-1"


def test_radar_ui_honours_the_no_filter_opt_out():
    js = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
    assert 'main[data-rui-no-filter]' in js
    # The opt-out must run before the priority / mark visibility decision.
    assert js.index('main[data-rui-no-filter]') < js.index('dirOk && prOk && mkOk')


def test_reading_styles_are_present():
    css = (STATIC / "radar-ui.css").read_text(encoding="utf-8")
    for selector in (".reading-toolbar", ".reading-stamp", ".reading-note",
                     ".reading-stamp__state.m-to-read"):
        assert selector in css, selector
