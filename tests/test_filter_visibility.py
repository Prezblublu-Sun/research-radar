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

from render import build_pages, corpus_view  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
DAY_JS = (STATIC / "radar-day.js").read_text(encoding="utf-8")
QUEUE_JS = (STATIC / "radar-queue.js").read_text(encoding="utf-8")


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


def test_an_all_hidden_page_offers_a_way_to_see_its_papers():
    # Saying "1 paper, all hidden" over an empty box is not a fix: the reader
    # opened the day to read it. The notice is drawn by the bundle that owns
    # the filters, so every page with a filter bar gets it — it was day-page
    # code first, and random-reading, with the same bar, sat empty.
    block = UI_JS.split("function renderBlockedNotice(total, hidden)")[1].split("function announceFiltersApplied")[0]
    assert 'document.querySelectorAll("#rui-priority-filter, #rui-marks-filter")' in block
    assert "if (!bars.length) return;" in block          # no bar, no filter, no notice
    assert "var blocked = total > 0 && hidden >= total;" in block
    assert '"显示全部"' in block
    assert 'reset.addEventListener("click", clearFilters);' in block
    assert "renderBlockedNotice(cards.length, hidden);" in UI_JS
    # The day page keeps only its status-line suffix.
    assert "day-blocked" not in DAY_JS


def test_the_notice_names_the_filter_that_did_it_not_a_guess():
    # The first notice listed the hidden cards' priorities, so a page emptied
    # by the mark filter said "（等级：High、Medium、Low、Exclude）".
    assert "hiddenPriorities" not in DAY_JS
    block = UI_JS.split("function activeFilters()")[1].split("function clearFilters")[0]
    assert '"等级未勾选 "' in block
    assert '"标记未勾选 "' in block
    assert '"只看标签 "' in block
    # Under the same gating applyFilters uses, so it never names a filter the
    # page is not applying.
    assert 'document.getElementById("rui-priority-filter")' in block
    assert 'document.getElementById("rui-marks-filter")' in block
    assert "activeFilters: activeFilters," in UI_JS


def test_a_selected_tag_nobody_carries_still_has_a_chip():
    # Chips were built from the tags in use, so a selected tag removed from
    # its last paper vanished from the bar while still hiding every card.
    block = UI_JS.split("function renderTagFilter()")[1].split("function announceFilterChange")[0]
    assert "active.forEach(function (tag) {" in block
    assert "known.push({ tag: tag, count: 0 });" in block
    assert block.index("var active = tagFilter();") < block.index("if (!known.length) return;")


def test_an_empty_queue_gets_the_same_way_out():
    assert "showBlocked(!total && filtersMarks());" in QUEUE_JS
    block = QUEUE_JS.split("function showBlocked(blocked)")[1]
    assert '"当前筛选下没有论文"' in block
    assert "window.RadarUI.clearFilters();" in block
    assert "api.activeFilters()" in block


def test_clearing_the_filters_resets_every_one_of_them():
    block = UI_JS.split("function clearFilters()")[1].split("function mergeMeta")[0]
    assert 'dirFilter = "all";' in block                 # direction tabs
    assert 'lsSet("radar:filter:priority", prios);' in block
    assert 'lsSet("radar:filter:marks", MARKS_DEFAULT.slice());' in block
    assert "setTagFilter([]);" in block                  # and the tag chips
    assert "applyFilters();" in block
    # "Unscored" has no checkbox but cards carry it, so it has to be added
    # explicitly or a rescored-pending paper stays invisible.
    assert 'var prios = ["Unscored"];' in block
    assert "clearFilters: clearFilters," in UI_JS


def test_clearing_filters_is_offered_never_imposed():
    # Silently overriding a filter the reader chose would be worse than an
    # empty page; the reset only ever runs from a button.
    assert UI_JS.count("clearFilters()") == 1            # the definition only
    assert UI_JS.count('addEventListener("click", clearFilters)') == 1
    assert DAY_JS.count("clearFilters") == 0
    assert QUEUE_JS.count("clearFilters()") == 1         # inside its click handler
    handler = QUEUE_JS.split('reset.addEventListener("click"')[1].split("});")[0]
    assert "clearFilters()" in handler


def test_a_filter_is_only_applied_where_its_control_is_shown():
    # The workbench has neither bar. A stored "only 忽略" hid all 777 of its
    # cards — headings and counts still claiming they were there — with no
    # checkbox on the page to undo it. Reported 2026-09-26 as "没变化".
    block = UI_JS.split("function applyFilters()")[1].split("function announceFiltersApplied")[0]
    assert 'var gradeBar = document.getElementById("rui-priority-filter");' in block
    assert 'var markBar = document.getElementById("rui-marks-filter");' in block
    assert "var prOk = !gradeBar || prios.indexOf(pr) >= 0;" in block
    assert "var mkOk = !markBar || visible(idk ? markRecord(idk) : null);" in block


def test_the_pages_that_filter_are_exactly_the_pages_that_offer_the_control():
    filtered = {
        "queue": build_pages._render_queue_page(),
        "random": build_pages._render_random_reading_page([], {}),
    }
    for name, html in filtered.items():
        assert 'id="rui-marks-filter"' in html, name
    # The workbench renders cards and offers neither bar, so under the rule
    # above it filters nothing.
    workbench = build_pages._render_workbench(
        [], {}, {}, corpus_view.CorpusStats(0, 0, 0, {}), {})
    assert 'id="rui-marks-filter"' not in workbench
    assert 'id="rui-priority-filter"' not in workbench


def test_the_queue_preference_is_not_promoted_to_a_global_filter():
    # The first cut of the ADR-0034 migration turned the queue's own
    # "只看已忽略" into the global mark filter, which is what produced the
    # ["ignore"] that emptied the site.
    block = UI_JS.split("function migrateMarks()")[1].split("migrateMarks();")[0]
    assert 'lsSet("radar:filter:marks", ["ignore"]);' not in block
    assert 'lsSet("radar:filter:marks", ["to-read", "read", "none"]);' not in block
    assert 'localStorage.removeItem("radar:filter:queue-ignored");' in block


def test_a_browser_that_already_ran_the_bad_migration_is_repaired():
    block = UI_JS.split("function migrateMarks()")[1].split("migrateMarks();")[0]
    assert "var SCHEMA_NOW = 3;" in UI_JS
    assert "if (done === 2) {" in block
    assert 'stored.length === 1 && stored[0] === "ignore"' in block
    assert 'lsSet("radar:filter:marks", MARKS_DEFAULT.slice());' in block


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
