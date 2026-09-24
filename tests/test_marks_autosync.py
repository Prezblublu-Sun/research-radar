"""ADR-0033: optional automatic marks sync with a browser-held token.

The token is a real security cost, so these tests pin the guardrails as hard
as the behaviour: it is never logged, only ever sent to api.github.com, the
page degrades to the token-free issue route without it, and the deploy is not
retriggered by a marks-only commit.

Run with:
    pytest tests/test_marks_autosync.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import marks_store as ms  # noqa: E402
from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
UI_CSS = (STATIC / "radar-ui.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the token as a liability
# ---------------------------------------------------------------------------

def test_the_token_only_ever_travels_to_github():
    assert UI_JS.count('fetch("https://api.github.com"') == 1
    assert '"Authorization": "Bearer " + syncToken()' in UI_JS
    # One place builds the authorised request; nothing else attaches it.
    assert UI_JS.count("Bearer") == 1


def test_the_token_is_never_printed_or_embedded():
    for pattern in ("console.log", "console.warn", "console.error"):
        assert pattern not in UI_JS, pattern
    # Only the last four characters ever reach the DOM.
    assert 'token.slice(-4)' in UI_JS
    assert "github_pat_" not in UI_JS  # no literal credential in the bundle


def test_the_reader_can_take_the_token_back():
    assert 'localStorage.removeItem(TOKEN_KEY)' in UI_JS
    forget = UI_JS.split('forgetBtn.addEventListener')[1].split('nowBtn.addEventListener')[0]
    assert "confirm(" in forget                      # destructive, so it asks
    assert "lastSyncedSignature = null" in forget    # no stale "already synced"
    library = build_pages._render_library_page()
    assert 'id="rui-token-forget"' in library
    assert 'type="password"' in library
    assert "只勾选这一个仓库" in library and "只给 Contents 读写" in library
    assert "rui-warn" in library and "localStorage" in library


def test_without_a_token_nothing_syncs_and_the_issue_route_survives():
    assert "function autoSyncReady()" in UI_JS
    assert "return Boolean(syncToken() && repoSlug());" in UI_JS
    for guard in ("function pushMarks(force)", "function runMarksPush(force)",
                  "function scheduleMarksPush()"):
        block = UI_JS.split(guard)[1][:260]
        assert "autoSyncReady()" in block, guard
    # The token-free hand-off is still wired.
    assert 'id="rui-sync-marks"' in build_pages._render_library_page()
    assert "labels=marks-sync" in UI_JS


# ---------------------------------------------------------------------------
# correctness of the write
# ---------------------------------------------------------------------------

def test_the_browser_writes_the_same_bytes_as_the_server():
    # payloadText mirrors json.dumps(sort_keys=True, indent=1); if the two
    # drift, the issue route and the direct write churn the file forever.
    payload = {
        "schema_version": 1,
        "device": "dev-1a2b3c4d",
        "updated_at": "2026-09-24T08:00:00Z",
        "marks": {
            "doi:10.1/b": {"state": "read", "at": "2026-09-23T00:00:00Z", "note": "",
                           "title": "B", "date": "", "direction": "", "priority": ""},
            "doi:10.1/a": {"state": "to-read", "at": "2026-09-24T00:00:00Z", "note": "记",
                           "title": "A", "date": "", "direction": "", "priority": ""},
        },
    }
    expected = json.dumps(ms.validate_payload(payload), ensure_ascii=False,
                          indent=1, sort_keys=True)
    # The JS sorts identity keys, sorts each mark's fields, and emits the four
    # top-level keys in sorted order with indent 1.
    assert 'Object.keys(payload.marks).sort()' in UI_JS
    assert 'Object.keys(source).sort()' in UI_JS
    top = UI_JS.split("return JSON.stringify({")[1].split("}, null, 1)")[0]
    assert top.index("device") < top.index("marks") < top.index("schema_version") \
        < top.index("updated_at")
    assert expected.startswith('{\n "device": "dev-1a2b3c4d",')


def test_a_concurrent_write_is_retried_once_not_forever():
    push = UI_JS.split("function pushMarks(force)")[1].split("function syncChip")[0]
    assert "response.status === 409 && retriesLeft > 0" in push
    assert "attempt(retriesLeft - 1)" in push
    assert "return attempt(1);" in push  # one retry, then the error surfaces


def test_an_unchanged_mark_set_does_not_push():
    push = UI_JS.split("function pushMarks(force)")[1].split("function syncChip")[0]
    assert "signature === lastSyncedSignature" in push
    # updated_at changes on every call, so only the marks may form the key.
    assert "JSON.stringify(payload.marks)" in push


def test_pending_edits_are_flushed_when_the_page_is_hidden():
    handler = UI_JS.split('"visibilitychange"')[1].split("var syncBtn")[0]
    assert 'document.visibilityState === "hidden"' in handler
    assert "runMarksPush(false)" in handler
    assert "clearTimeout(syncTimer)" in handler


def test_writes_are_debounced_and_serialised():
    assert "SYNC_DEBOUNCE_MS = 4000" in UI_JS
    assert 'document.addEventListener("radar:mark-changed", scheduleMarksPush)' in UI_JS
    run = UI_JS.split("function runMarksPush(force)")[1].split("function scheduleMarksPush")[0]
    assert "syncQueued = true" in run       # overlapping pushes collapse
    assert "syncInFlight = false" in run


# ---------------------------------------------------------------------------
# honesty about the outcome
# ---------------------------------------------------------------------------

def test_every_failure_mode_is_named_rather_than_guessed():
    errors = UI_JS.split("function apiError(response)")[1].split("function putMarksFile")[0]
    for code in ("401", "403", "404", "409", "422"):
        assert code in errors, code
    run = UI_JS.split("function runMarksPush(force)")[1].split("function scheduleMarksPush")[0]
    assert '"同步失败：" + error.message' in run
    assert '"bad", true' in run             # a failure stays on screen
    assert '✓ 已同步 ' in run


def test_saving_a_token_verifies_it_with_a_real_write():
    save = UI_JS.split("saveBtn.addEventListener")[1].split("forgetBtn.addEventListener")[0]
    assert "runMarksPush(true)" in save
    assert "正在用一次真实提交验证令牌" in save


def test_the_status_chip_exists_and_is_dismissable():
    assert ".rui-sync-chip" in UI_CSS
    chip = UI_JS.split("function syncChip()")[1].split("function showSync")[0]
    assert 'chip.hidden = true' in chip      # click to dismiss


# ---------------------------------------------------------------------------
# the deploy must not rebuild the site per mark
# ---------------------------------------------------------------------------

def test_a_marks_only_commit_does_not_rebuild_the_whole_site():
    pages = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"))
    assert pages[True]["push"]["paths-ignore"] == ["data/marks/**"]
    raw = (REPO_ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "REMOVE this" in raw  # the condition for undoing it is written down
