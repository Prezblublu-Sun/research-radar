"""ADR-0034: a paper has one state and any number of tags.

The old model had a single flat enum — 待阅读 / 已阅读 / 有启发 / 忽略 — which
could not say "read, and worth something", and which only the daily pages
could filter on. This suite pins the replacement:

* ``state`` is the triage flow (待读 → 已读, plus 忽略), one at a time;
* ``tags`` are judgements, any number at a time, free text;
* one filter rule, shared by the daily pages, the queue and the reading list;
* the retired ``interesting`` state migrates to ``read`` + the ``有启发`` tag,
  in this browser *and* in anything an un-migrated browser uploads.

Run with:
    pytest tests/test_mark_tags.py
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import marks_store as ms  # noqa: E402
from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
QUEUE_JS = (STATIC / "radar-queue.js").read_text(encoding="utf-8")
CARD_JS = (STATIC / "radar-card.js").read_text(encoding="utf-8")
READING_JS = (STATIC / "radar-reading.js").read_text(encoding="utf-8")
UI_CSS = (STATIC / "radar-ui.css").read_text(encoding="utf-8")


def _payload(**marks):
    return {"schema_version": 1, "device": "dev-1a2b3c4d", "marks": marks}


# ---------------------------------------------------------------------------
# The stored shape
# ---------------------------------------------------------------------------

def test_the_state_vocabulary_lost_interesting_and_kept_the_rest():
    assert ms.STATES == {"to-read", "read", "ignore", ""}
    assert ms.INSPIRING_TAG == "有启发"


def test_an_old_browser_still_syncing_interesting_is_migrated_not_rejected():
    # The page is cached aggressively and a tab can live for weeks; a mark
    # from one must land in the new shape rather than bounce the whole file.
    marks = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "interesting", "at": "2026-09-24T00:00:00Z"},
    }))["marks"]
    assert marks["doi:10.1/x"]["state"] == "read"
    assert marks["doi:10.1/x"]["tags"] == ["有启发"]


def test_the_migration_does_not_duplicate_a_tag_the_reader_already_added():
    marks = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "interesting", "tags": ["有启发", "方法可借鉴"],
                       "at": "2026-09-24T00:00:00Z"},
    }))["marks"]
    assert marks["doi:10.1/x"]["tags"] == ["方法可借鉴", "有启发"]


def test_tags_are_trimmed_deduplicated_and_sorted():
    # Sorted so two devices that added the same tags in a different order
    # write byte-identical files instead of fighting over the commit.
    marks = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "read", "at": "2026-09-24T00:00:00Z",
                       "tags": ["  b  ", "a", "a", "", "c  d"]},
    }))["marks"]
    assert marks["doi:10.1/x"]["tags"] == ["a", "b", "c d"]


def test_a_payload_is_a_trust_boundary_for_tags_too():
    for bad in ("not a list", {"a": 1}, [1], [None]):
        with pytest.raises(ms.MarksPayloadError):
            ms.validate_payload(_payload(**{
                "doi:10.1/x": {"state": "read", "tags": bad,
                               "at": "2026-09-24T00:00:00Z"},
            }))
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(**{
            "doi:10.1/x": {"state": "read", "at": "2026-09-24T00:00:00Z",
                           "tags": [f"t{n}" for n in range(ms.MAX_TAGS + 1)]},
        }))
    long = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "read", "at": "2026-09-24T00:00:00Z",
                       "tags": ["x" * (ms.MAX_TAG + 20)]},
    }))["marks"]
    assert long["doi:10.1/x"]["tags"] == ["x" * ms.MAX_TAG]


def test_a_paper_can_carry_tags_without_a_state():
    # "I haven't read it but it's 有启发" has to be sayable, and it must not
    # be mistaken for a cleared mark and dropped at merge time.
    payload = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "", "tags": ["有启发"],
                       "at": "2026-09-24T00:00:00Z"},
    }))
    mark = payload["marks"]["doi:10.1/x"]
    assert mark["tags"] == ["有启发"] and not ms.is_tombstone(mark)
    empty = ms.validate_payload(_payload(**{
        "doi:10.1/y": {"state": "", "at": "2026-09-24T00:00:00Z"},
    }))["marks"]["doi:10.1/y"]
    assert ms.is_tombstone(empty)


def test_clearing_everything_still_removes_the_mark_everywhere(tmp_path):
    ms.write_device(tmp_path, ms.validate_payload({
        "schema_version": 1, "device": "dev-laptop01",
        "marks": {"doi:10.1/x": {"state": "read", "tags": ["有启发"],
                                 "at": "2026-09-20T00:00:00Z"}}}))
    ms.write_device(tmp_path, ms.validate_payload({
        "schema_version": 1, "device": "dev-desktop1",
        "marks": {"doi:10.1/x": {"state": "", "tags": [],
                                 "at": "2026-09-22T00:00:00Z"}}}))
    assert ms.load_all(tmp_path) == {}


def test_the_server_can_read_a_tag_the_way_it_reads_a_state():
    # The curated library and the daily digest are next; both need to ask
    # "everything tagged 有启发", not just "everything marked 已读".
    marks = {
        "doi:a": {"state": "read", "tags": ["有启发"], "at": "2026-09-20T00:00:00Z"},
        "doi:b": {"state": "to-read", "tags": ["有启发", "方法可借鉴"],
                  "at": "2026-09-22T00:00:00Z"},
        "doi:c": {"state": "read", "tags": [], "at": "2026-09-23T00:00:00Z"},
    }
    assert [k for k, _ in ms.by_tag(marks, "有启发")] == ["doi:b", "doi:a"]
    assert [k for k, _ in ms.by_state(marks, "read")] == ["doi:c", "doi:a"]
    assert ms.tag_counts(marks) == {"有启发": 2, "方法可借鉴": 1}


# ---------------------------------------------------------------------------
# The browser: migration and the write path
# ---------------------------------------------------------------------------

def test_the_browser_migrates_its_own_storage_once():
    block = UI_JS.split("function migrateMarks()")[1].split("migrateMarks();")[0]
    assert 'var SCHEMA_KEY = "radar:marks-schema";' in UI_JS
    assert "var SCHEMA_NOW = 2;" in UI_JS
    assert "if (done >= SCHEMA_NOW) return;" in block
    assert 'record.state = "read";' in block
    assert "tags.push(INSPIRING_TAG)" in block
    # Migration runs before anything reads a mark or a filter.
    assert UI_JS.index("migrateMarks();") < UI_JS.index("function applyFilters")


def test_the_migration_leaves_the_timestamp_alone():
    # Bumping `at` would make this browser win every merge and silently
    # revert marks made on another device since.
    block = UI_JS.split("function migrateMarks()")[1].split("migrateMarks();")[0]
    assert "new Date().toISOString()" not in block
    assert "record.at" not in block


def test_the_migration_carries_the_two_filters_that_named_states():
    block = UI_JS.split("function migrateMarks()")[1].split("migrateMarks();")[0]
    # The daily-page checkbox bar...
    assert 'lsGet("radar:filter:marks", null)' in block
    assert 'state !== "interesting"' in block
    # ...and the queue's retired three-way 忽略 select.
    assert 'localStorage.getItem("radar:filter:queue-ignored")' in block
    assert 'lsSet("radar:filter:marks", ["ignore"]);' in block
    assert 'lsSet("radar:filter:marks", ["to-read", "read", "none"]);' in block


def test_a_stale_filter_value_cannot_hide_every_read_paper():
    # Defence in depth: a tab that never reloads keeps writing the old state
    # into the filter, and marksFilter() has to survive reading it back.
    block = UI_JS.split("function marksFilter()")[1].split("function tagFilter")[0]
    assert 'v.indexOf("interesting") >= 0' in block
    assert 'known.indexOf("read") < 0' in block


def test_every_mark_write_goes_through_one_stamped_path():
    block = UI_JS.split("function updateMark(")[1].split("function mergeMeta")[0]
    assert "record.tags = normTags(record.tags);" in block
    assert 'record.at = new Date().toISOString();' in block
    assert "applyFilters();" in block and "announceMarkChange(idkey);" in block
    # The radios, the clear and the note all use it...
    assert UI_JS.count("updateMark(idk, card, function (record)") == 3
    # ...and so does the tag editor, one level down.
    assert "updateMark(idkey, card, change);" in UI_JS
    # ...and none of them writes the record itself any more.
    assert 'cur.at = new Date().toISOString();' not in UI_JS


# ---------------------------------------------------------------------------
# The browser: one filter rule for three surfaces
# ---------------------------------------------------------------------------

def test_states_are_or_ed_and_a_chosen_tag_narrows_further():
    block = UI_JS.split("function markFilterFn()")[1].split("function markRecord")[0]
    assert "if (states.indexOf(state) < 0) return false;" in block
    assert "if (!wanted.length) return true;" in block
    assert "if (have.indexOf(wanted[index]) >= 0) return true;" in block
    # Built once per pass, not once per card.
    assert "var visible = markFilterFn();" in UI_JS


def test_the_daily_page_and_the_queue_run_the_same_rule():
    assert "markFilter: markFilterFn" in UI_JS
    assert "markRecord: markRecord" in UI_JS
    assert "var visible = api.markFilter();" in QUEUE_JS
    assert "visible(api.markRecord(record.identity_key))" in QUEUE_JS
    # The queue's own copy of the ignore logic is gone.
    for retired in ("state.ignored", "markStateOf", "IGNORED_MODES",
                    "queue-ignored", "hiddenIgnoredCount"):
        assert retired not in QUEUE_JS, retired


def test_the_queue_shows_the_same_bar_the_daily_pages_show():
    queue = build_pages._render_queue_page()
    assert 'id="rui-marks-filter"' in queue
    assert 'class="rui-mf-cb"' in queue
    for label in ("待阅读", "已阅读", "忽略", "未标记"):
        assert label in queue, label
    # The bespoke select it replaces is gone.
    assert 'id="queue-ignored"' not in queue
    assert "已忽略以外" not in queue


def test_the_filter_bar_offers_the_three_states_plus_unmarked():
    bar = build_pages._marks_filter_bar()
    for value in ('value="to-read"', 'value="read"', 'value="ignore"',
                  'value="none"'):
        assert value in bar, value
    assert 'value="interesting"' not in bar


def test_the_tag_chips_are_built_in_the_browser_because_only_it_knows_them():
    block = UI_JS.split("function renderTagFilter()")[1].split("function announceFilterChange")[0]
    assert 'document.getElementById("rui-marks-filter")' in block
    assert "if (!known.length) return;" in block           # nothing tagged yet
    assert "setTagFilter(next);" in block
    assert "announceFilterChange();" in block
    assert ".rui-tagf-chip" in UI_CSS


def test_a_filter_change_restarts_the_queue_from_page_one():
    # The filter decides which year shards even have to be fetched, so the
    # queue cannot just re-render what it is holding.
    handler = QUEUE_JS.split('radar:filter-changed"')[1]
    assert "loadView(1, false)" in handler
    assert 'announceFilterChange();' in UI_JS


def test_a_mark_change_only_costs_a_reload_when_the_filter_can_hide_things():
    block = QUEUE_JS.split("function filtersMarks()")[1].split("function element")[0]
    assert "visible(null)" in block                        # the unmarked case
    for state in ("to-read", "read", "ignore"):
        assert f'{{ state: "{state}" }}' in block
    handler = QUEUE_JS.split('radar:mark-changed"')[1]
    assert "if (state.loading || !filtersMarks()) return;" in handler


def test_a_marks_only_view_loads_only_the_shards_that_can_hold_marks():
    # A mark records the paper's publication date, which names its year
    # shard, so excluding 未标记 must not drag in every year of the priority.
    assert "marksOnly: marksOnly" in UI_JS
    assert "markedYears: markedYears" in UI_JS
    only = UI_JS.split("function marksOnly()")[1].split("// The one rule")[0]
    assert 'marksFilter().indexOf("none") < 0' in only
    years = UI_JS.split("function markedYears()")[1].split("renderTagFilter();")[0]
    assert "var visible = markFilterFn();" in years
    assert "if (!visible(record)) return;" in years
    assert '/^\\d{4}$/.test(year)' in years                # a junk date becomes ""
    ensure = QUEUE_JS.split("function ensureDataForView")[1].split("function syncUrl")[0]
    assert "if (marksOnly()) {" in ensure
    assert "loadYears(wanted, generation)" in ensure
    assert "year === state.year" in ensure                 # a year filter still narrows


def test_a_mark_without_a_usable_date_widens_instead_of_vanishing():
    years = QUEUE_JS.split("function yearsHoldingMarks()")[1].split("function knownFilteredTotal")[0]
    assert 'if (wanted.indexOf("") >= 0) return available;' in years


def test_the_total_is_corrected_when_it_can_be_and_abandoned_when_it_cannot():
    assert "if (marksOnly()) return null;" in QUEUE_JS
    assert "return Math.max(0, total - hiddenByMarks());" in QUEUE_JS
    hidden = QUEUE_JS.split("function hiddenByMarks()")[1].split("function priorityInfo")[0]
    assert "if (marksOnly()) return 0;" in hidden
    assert "if (matchesFacets(record) && !visible(record)) hidden += 1;" in hidden
    assert '" · 只看已标记"' in QUEUE_JS
    assert '" · 标记筛选已隐藏 " + hidden + " 篇"' in QUEUE_JS


def test_the_queue_still_reads_far_enough_ahead_to_refill_a_page():
    prefix = QUEUE_JS.split("function ensurePrefixForPage")[1].split("function loadAllYears")[0]
    assert "var hidden = hiddenByMarks();" in prefix
    assert "state.page * PAGE_SIZE + hidden" in prefix
    assert prefix.index("var target") > prefix.index("function step()")


def test_the_mark_filter_stays_out_of_the_shared_url():
    # Sharing a queue link should not impose your triage on the reader.
    assert 'params.delete("ignored");' in QUEUE_JS
    assert 'params.set("ignored"' not in QUEUE_JS


def test_the_priority_filter_only_applies_where_its_control_is_shown():
    # It is a daily-page control; the queue picks its own priority. Left
    # global, unticking High on a daily page silently empties the queue.
    block = UI_JS.split("function applyFilters()")[1].split("function renderTagFilter")[0]
    assert 'document.getElementById("rui-priority-filter")' in block
    assert "var prOk = !gradeBar || prios.indexOf(pr) >= 0;" in block


# ---------------------------------------------------------------------------
# The browser: editing tags on a card
# ---------------------------------------------------------------------------

def test_a_card_offers_three_states_and_a_tag_panel():
    tools = build_pages._card_tools({"doi": "10.1/x"})
    for value in ('value="to-read"', 'value="read"', 'value="ignore"'):
        assert value in tools, value
    assert 'value="interesting"' not in tools
    assert 'class="rui-tag-btn"' in tools
    # Without the wrap the editor has nowhere to render on a daily page.
    assert 'class="rui-tag-wrap"' in tools
    # The JS-built card (queue, reading list) matches the rendered one.
    assert '["to-read", "待阅读"], ["read", "已阅读"], ["ignore", "忽略"]' in CARD_JS
    assert '"rui-tag-btn"' in CARD_JS
    assert '"rui-tag-wrap"' in CARD_JS


def test_the_tag_editor_reads_and_writes_through_the_shared_path():
    block = UI_JS.split("function renderTagEditor(")[1].split("// ---- D4 + D5")[0]
    assert "var current = markTags(idkey);" in block
    assert "updateMark(idkey, card, change);" in block
    assert "record.tags.filter(function (t) { return t !== tag; })" in block
    assert "record.tags.concat(clean)" in block
    # The tag that used to be a state keeps a one-click path.
    assert 'node("button", "rui-tag-quick", "+ " + INSPIRING_TAG)' in block
    # Adding one refreshes the filter chips and the autocomplete.
    assert "renderTagFilter();" in block and "refreshTagDatalist();" in block


def test_free_text_tags_are_offered_as_a_vocabulary_not_reinvented():
    # Without the datalist, "有启发" and "有启发 " become two tags.
    assert 'input.setAttribute("list", "rui-tags-known");' in UI_JS
    block = UI_JS.split("function refreshTagDatalist()")[1].split("// The chip row")[0]
    assert "allTags().forEach" in block
    assert 'list.id = "rui-tags-known";' in block


def test_the_chip_row_is_readable_closed_and_editable_open():
    assert ".rui-tag-wrap[data-open=\"1\"] .rui-tag-add { display: flex; }" in UI_CSS
    assert ".rui-tag-x { display: none;" in UI_CSS
    assert '.rui-tag-wrap[data-open="1"] .rui-tag-x,' in UI_CSS
    toggle = UI_JS.split('tagBtn.addEventListener("click"')[1].split("});")[0]
    assert 'tagWrap.dataset.open = open ? "0" : "1";' in toggle


def test_the_browser_caps_tags_the_way_the_server_does():
    # Clamping here beats having the sync bounce the whole file.
    assert f"var MAX_TAGS = {ms.MAX_TAGS};" in UI_JS
    assert f"var MAX_TAG = {ms.MAX_TAG};" in UI_JS
    block = UI_JS.split("function normTags(")[1].split("function tagsOf")[0]
    assert "out.length < MAX_TAGS" in block
    assert ".slice(0, MAX_TAG)" in block
    assert "return out.sort();" in block


def test_the_sync_payload_carries_the_tags():
    assert "tags: tags," in UI_JS
    assert "var tags = tagsOf(record);" in UI_JS


# ---------------------------------------------------------------------------
# The reading list
# ---------------------------------------------------------------------------

def test_the_reading_list_filters_by_tag_alongside_its_state_tabs():
    assert 'var TABS = ["to-read", "read", "ignore", "note", "all"];' in READING_JS
    assert '"interesting"' not in READING_JS
    assert 'tagSelect = document.getElementById("reading-tag")' in READING_JS
    assert "inTab(mark, view.tab) && hasTag(mark, view.tag)" in READING_JS
    # The counts on the tabs describe what a click will actually show.
    counts = READING_JS.split("function updateTabs(all)")[1].split("// ---- events")[0]
    assert "inTab(mark, tab) && hasTag(mark, view.tag)" in counts


def test_the_reading_list_keeps_the_tag_picker_honest():
    block = READING_JS.split("function updateTagPicker(all)")[1].split("function updateTabs")[0]
    assert 'view.tag = "";' in block           # last paper holding it lost it
    assert "tagSelect.disabled = known.length === 0;" in block
    assert 'document.addEventListener("radar:mark-changed"' in READING_JS


def test_tags_reach_the_search_the_stamp_and_the_markdown_export():
    assert "mark.tags.join(\" \")" in READING_JS
    assert 'element("span", "reading-stamp__tag", tag)' in READING_JS
    assert '.reading-stamp__tag' in UI_CSS
    assert 'mark.tags.map(function (tag) { return "#" + tag; })' in READING_JS
