"""A filter may not hide cards without the page saying so.

Two ways that went wrong, both found on the live site:

* 2026-09-25 published one paper and it was Low. The day page printed "全天 1
  篇 · 当前页 1 篇" over an empty grid, because the count is taken before the
  priority filter runs and nothing ever revisited it.
* The random-reading page renders `.paper` cards, so the shared mark filter
  applies to them — but the page carried no filter bar, so a reader who had
  unticked 未标记 elsewhere would see an empty page and no control explaining
  it. (The same shape as the priority filter leaking onto the queue, fixed in
  ADR-0034.)

Run with:
    pytest tests/test_filter_visibility.py
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
DAY_JS = (STATIC / "radar-day.js").read_text(encoding="utf-8")


def test_apply_filters_reports_how_much_it_hid():
    block = UI_JS.split("function applyFilters()")[1].split("function announceFiltersApplied")[0]
    assert "if (!show) hidden += 1;" in block
    assert "announceFiltersApplied(cards.length, hidden);" in block
    # The exempt path reports too, so a listener is never left with a stale
    # note on a page that filters nothing.
    assert "announceFiltersApplied(cards.length, 0);" in block


def test_the_report_comes_from_one_place_not_from_each_control():
    # Direction tabs, priority bar, mark bar, tag chips and every mark write
    # all end in applyFilters; announcing there covers them all at once.
    announce = UI_JS.split("function announceFiltersApplied(total, hidden)")[1]
    assert 'radar:filters-applied' in announce
    assert "shown: total - hidden" in announce
    assert UI_JS.count("announceFiltersApplied(") == 3   # 1 definition + 2 calls


def test_the_day_page_status_line_accounts_for_the_filters():
    assert 'document.addEventListener("radar:filters-applied"' in DAY_JS
    describe = DAY_JS.split("function describeFilters(hidden)")[1].split("document.addEventListener")[0]
    assert '" · 本页 " + hidden + " 篇都被上方筛选隐藏了"' in describe
    assert '" · 已按筛选隐藏 " + hidden + " 篇"' in describe
    assert "if (!cardsOnPage || !hidden) return \"\";" in describe


def test_the_base_line_exists_before_the_filters_run():
    # hydrate() applies the filters and dispatches; if the base line is set
    # afterwards it overwrites the note, and the first render shows none.
    page = DAY_JS.split("function showPage(records, targetAnchor)")[1].split("function showError")[0]
    assert page.index("baseStatus =") < page.index("hydrate();")
    assert page.index("cardsOnPage = records.length;") < page.index("hydrate();")


def test_the_card_counter_does_not_shadow_the_page_total_element():
    # `pageTotal` is the "共 N 页" element, declared at the top of the IIFE.
    # A second `var pageTotal` in the same function scope overwrote it with a
    # number and renderPagination threw on every load.
    assert 'var pageTotal = document.getElementById("day-page-total");' in DAY_JS
    assert DAY_JS.count("var pageTotal") == 1
    assert "var cardsOnPage = 0;" in DAY_JS


def test_the_random_reading_page_shows_the_filter_that_applies_to_it():
    html = build_pages._render_random_reading_page([], {})
    assert 'id="rui-marks-filter"' in html
    assert 'class="rui-mf-cb"' in html
    # It is not exempt from filtering, so the bar is the honest option.
    assert "data-rui-no-filter" not in html


def test_the_reading_list_stays_exempt_and_needs_no_bar():
    # It shows exactly what the reader marked; filtering it by marks would be
    # circular, which is why it opts out instead of carrying a bar.
    html = build_pages._render_reading_page()
    assert 'data-rui-no-filter="1"' in html
    assert 'id="rui-marks-filter"' not in html
