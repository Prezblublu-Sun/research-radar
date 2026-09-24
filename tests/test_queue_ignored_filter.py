"""The queue page can show everything, everything but 忽略, or only 忽略.

Marks live in localStorage, so the server-side facet counts describe none of
this; these tests pin the contract that keeps the count, the loader and the
live refresh honest in each of the three modes.

Run with:
    pytest tests/test_queue_ignored_filter.py
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


def test_the_toolbar_offers_three_modes_not_a_hide_switch():
    queue = build_pages._render_queue_page()
    assert 'id="queue-ignored"' in queue
    for option in ('value=""', 'value="exclude"', 'value="only"'):
        assert option in queue, option
    for label in ("全部", "已忽略以外", "只看已忽略"):
        assert label in queue, label
    # The first cut was a checkbox; it and its style are gone.
    assert "queue-hide-ignored" not in queue
    assert "queue-toggle" not in queue
    assert "queue-toggle" not in (STATIC / "radar-ui.css").read_text(encoding="utf-8")


def test_each_mode_selects_the_right_cards():
    block = QUEUE_JS.split("function filteredRecords()")[1].split("function hiddenIgnoredCount")[0]
    assert 'if (state.ignored === "exclude") return !ignored;' in block
    assert 'if (state.ignored === "only") return ignored;' in block
    assert "return true;" in block            # "" shows everything
    assert 'markStateOf(record) === "ignore"' in block
    # Unknown values from a hand-edited URL collapse to "show everything".
    assert 'IGNORED_MODES = ["", "exclude", "only"]' in QUEUE_JS
    assert "function normaliseMode(value)" in QUEUE_JS
    assert "IGNORED_MODES.indexOf(value) >= 0 ? value : \"\"" in QUEUE_JS


def test_the_mark_state_comes_from_the_shared_bundle():
    assert "api.markState" in QUEUE_JS and "markState: markState" in UI_JS


def test_the_total_is_corrected_in_exclude_and_abandoned_in_only():
    assert 'if (state.ignored === "only") return null;' in QUEUE_JS
    assert "return Math.max(0, total - hiddenIgnoredCount());" in QUEUE_JS
    hidden = QUEUE_JS.split("function hiddenIgnoredCount()")[1].split("function yearsHoldingIgnoredMarks")[0]
    assert 'if (state.ignored !== "exclude") return 0;' in hidden
    # The status line says which view the reader is looking at.
    assert '" · 只看已忽略"' in QUEUE_JS
    assert '" · 已隐藏 " + hidden + " 篇忽略"' in QUEUE_JS


def test_only_mode_loads_just_the_shards_that_can_hold_ignored_papers():
    # A mark records the paper's publication date, which names its year shard,
    # so "only" must not drag in every year of the priority.
    assert "function yearsHoldingIgnoredMarks()" in QUEUE_JS
    assert "api.ignoredYears()" in QUEUE_JS
    ensure = QUEUE_JS.split("function ensureDataForView")[1].split("function syncUrl")[0]
    assert 'if (state.ignored === "only")' in ensure
    assert "yearsHoldingIgnoredMarks()" in ensure
    assert "loadYears(wanted, generation)" in ensure
    # An explicit year filter still narrows it further.
    assert "year === state.year" in ensure


def test_a_mark_without_a_usable_date_widens_instead_of_vanishing():
    years = QUEUE_JS.split("function yearsHoldingIgnoredMarks()")[1].split("function knownFilteredTotal")[0]
    assert 'if (wanted.indexOf("") >= 0) return available;' in years
    exporter = UI_JS.split("function ignoredYears()")[1].split("window.RadarUI")[0]
    assert 'record.state !== "ignore"' in exporter      # only 忽略 marks count
    assert '/^\\d{4}$/.test(year)' in exporter          # a junk date becomes ""
    assert "ignoredYears: ignoredYears" in UI_JS


def test_exclude_mode_still_reads_far_enough_to_refill_a_page():
    prefix = QUEUE_JS.split("function ensurePrefixForPage")[1].split("function loadAllYears")[0]
    assert "state.page * PAGE_SIZE + hiddenIgnoredCount()" in prefix
    assert prefix.index("var target") > prefix.index("function step()")


def test_a_mark_change_refreshes_both_ignore_views():
    handler = QUEUE_JS.split('radar:mark-changed"')[1]
    assert "if (!state.ignored || state.loading) return;" in handler
    assert "loadView(state.page, false)" in handler
    assert UI_JS.count("announceMarkChange(") == 4  # 1 definition + 3 writers


def test_the_choice_persists_travels_and_migrates():
    assert 'IGNORED_KEY = "radar:filter:queue-ignored"' in QUEUE_JS
    assert 'params.set("ignored", state.ignored)' in QUEUE_JS
    assert 'params.delete("ignored")' in QUEUE_JS
    # The short-lived checkbox form is honoured, from the URL and from storage.
    assert 'params.get("hide_ignored") === "1" ? "exclude"' in QUEUE_JS
    assert '"radar:filter:queue-hide-ignored") === "1"' in QUEUE_JS
    assert 'params.delete("hide_ignored")' in QUEUE_JS   # and then retired
    # An explicit URL value wins over the remembered preference.
    assert 'params.has("ignored")' in QUEUE_JS


def test_storage_failures_do_not_break_the_page():
    remembered = QUEUE_JS.split("function rememberedIgnoredMode")[1].split("function element")[0]
    assert remembered.count("catch (error)") == 2  # read and write both guarded
