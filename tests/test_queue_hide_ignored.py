"""The queue page can hide papers the reader marked 忽略.

Marks live in localStorage, so the server-side facet counts know nothing
about them; these tests pin the contract that keeps the count, the loader and
the immediate re-render honest.

Run with:
    pytest tests/test_queue_hide_ignored.py
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
QUEUE_JS = (STATIC / "radar-queue.js").read_text(encoding="utf-8")
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
UI_CSS = (STATIC / "radar-ui.css").read_text(encoding="utf-8")


def test_the_queue_toolbar_offers_the_toggle():
    queue = build_pages._render_queue_page()
    assert 'id="queue-hide-ignored"' in queue
    assert 'type="checkbox"' in queue
    assert "隐藏已忽略" in queue
    assert ".queue-toggle" in UI_CSS


def test_the_filter_drops_only_ignored_cards():
    assert 'markStateOf(record) === "ignore"' in QUEUE_JS
    assert "state.hideIgnored && markStateOf(record)" in QUEUE_JS
    # The facet filters stay factored out so both paths agree on what matches.
    assert "function matchesFacets(record)" in QUEUE_JS
    assert QUEUE_JS.count("matchesFacets(record)") >= 2


def test_the_mark_state_comes_from_the_shared_bundle():
    assert "window.RadarUI" in QUEUE_JS and "api.markState" in QUEUE_JS
    assert "markState: markState" in UI_JS
    assert "function markState(idkey)" in UI_JS


def test_the_displayed_total_is_corrected_for_hidden_cards():
    # Server facets cannot know about local marks, so the known total has the
    # loaded-and-hidden ones subtracted rather than being reported as-is.
    assert "return Math.max(0, total - hiddenIgnoredCount());" in QUEUE_JS
    assert "已隐藏 " in QUEUE_JS and "篇忽略" in QUEUE_JS


def test_the_loader_reads_far_enough_to_refill_a_page():
    # A page of 20 that hides 3 must pull 23, and every newly loaded year can
    # reveal more, so the target is recomputed inside the loop.
    prefix = QUEUE_JS.split("function ensurePrefixForPage")[1].split("function loadAllYears")[0]
    assert "state.page * PAGE_SIZE + hiddenIgnoredCount()" in prefix
    assert prefix.index("var target") > prefix.index("function step()")


def test_marking_a_visible_card_ignored_refreshes_the_list():
    assert 'document.addEventListener("radar:mark-changed"' in QUEUE_JS
    handler = QUEUE_JS.split('radar:mark-changed"')[1]
    assert "if (!state.hideIgnored || state.loading) return;" in handler
    assert "loadView(state.page, false)" in handler
    # ...and radar-ui.js actually emits it on every write path.
    assert UI_JS.count("announceMarkChange(") == 4  # 1 definition + 3 writers


def test_the_choice_survives_a_reload_and_travels_in_the_url():
    assert 'HIDE_IGNORED_KEY = "radar:filter:queue-hide-ignored"' in QUEUE_JS
    assert "rememberedHideIgnored()" in QUEUE_JS
    assert 'params.set("hide_ignored", "1")' in QUEUE_JS
    assert 'params.delete("hide_ignored")' in QUEUE_JS
    # An explicit URL value wins over the remembered preference.
    assert 'params.has("hide_ignored")' in QUEUE_JS


def test_storage_failures_do_not_break_the_page():
    remembered = QUEUE_JS.split("function rememberedHideIgnored")[1].split("function element")[0]
    assert remembered.count("catch (error)") == 2  # read and write both guarded
