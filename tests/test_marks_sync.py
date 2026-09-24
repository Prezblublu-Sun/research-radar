"""ADR-0032: reading marks become durable repository data.

The payload arrives pasted into a public issue, so validation is a trust
boundary: these tests pin the rejections as hard as the happy path.

Run with:
    pytest tests/test_marks_sync.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import marks_store as ms  # noqa: E402
from scripts import apply_marks_sync  # noqa: E402

UI_JS = (REPO_ROOT / "render" / "static" / "radar-ui.js").read_text(encoding="utf-8")


def _payload(device="dev-1a2b3c4d", **marks) -> dict:
    return {
        "schema_version": 1,
        "device": device,
        "updated_at": "2026-09-22T12:00:00Z",
        "marks": marks or {
            "doi:10.1/x": {"state": "to-read", "at": "2026-09-22T11:00:00Z",
                           "note": "看方法", "title": "T", "date": "2026-09-10",
                           "direction": "fea_surrogate", "priority": "High"},
        },
    }


# ---------------------------------------------------------------------------
# validation — the trust boundary
# ---------------------------------------------------------------------------

def test_a_well_formed_payload_round_trips():
    out = ms.validate_payload(_payload())
    assert out["device"] == "dev-1a2b3c4d"
    assert out["marks"]["doi:10.1/x"]["state"] == "to-read"
    assert out["marks"]["doi:10.1/x"]["note"] == "看方法"


@pytest.mark.parametrize("device", [
    "../../etc/passwd", "a/b", "dev 1", "ab", "x" * 40, "", ".hidden", 42,
])
def test_a_device_name_can_never_escape_the_marks_directory(device):
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(device=device))


def test_an_over_long_device_name_is_rejected_not_silently_truncated():
    # Truncating to the cap would let "x"*40 and "x"*32 land on one file.
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(device="x" * 33))
    assert ms.validate_payload(_payload(device="x" * 32))["device"] == "x" * 32


def test_device_case_is_normalised_rather_than_rejected():
    assert ms.validate_payload(_payload(device="DEV-1a2B"))["device"] == "dev-1a2b"


def test_device_path_refuses_traversal_even_if_called_directly(tmp_path):
    with pytest.raises(ms.MarksPayloadError):
        ms.device_path(tmp_path, "../escape")


@pytest.mark.parametrize("key", [
    "not-an-identity", "doi:", "ftp:10.1/x", "doi:" + "x" * 300, "",
])
def test_identity_keys_are_checked(key):
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(**{key: {"state": "to-read"}}))


def test_unknown_states_and_timestamps_are_rejected():
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(**{"doi:10.1/x": {"state": "promote"}}))
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(**{"doi:10.1/x": {"state": "read", "at": "yesterday"}}))


def test_a_wrong_schema_version_is_refused():
    bad = _payload()
    bad["schema_version"] = 99
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(bad)


def test_oversized_payloads_are_capped():
    huge = {f"doi:10.1/p{i}": {"state": "to-read"} for i in range(ms.MAX_MARKS + 1)}
    with pytest.raises(ms.MarksPayloadError):
        ms.validate_payload(_payload(**huge))
    long_note = ms.validate_payload(_payload(**{
        "doi:10.1/x": {"state": "read", "note": "字" * (ms.MAX_NOTE + 500)}}))
    assert len(long_note["marks"]["doi:10.1/x"]["note"]) == ms.MAX_NOTE


def test_empty_marks_are_dropped_and_unknown_fields_ignored():
    out = ms.validate_payload(_payload(**{
        "doi:10.1/empty": {"state": "", "note": ""},
        "doi:10.1/kept": {"state": "", "note": "只有笔记", "surprise": "ignored"},
    }))
    assert "doi:10.1/empty" not in out["marks"]
    assert out["marks"]["doi:10.1/kept"]["note"] == "只有笔记"
    assert "surprise" not in out["marks"]["doi:10.1/kept"]


# ---------------------------------------------------------------------------
# extraction from an issue body
# ---------------------------------------------------------------------------

def test_extract_accepts_a_fenced_block_or_a_bare_object():
    payload = _payload()
    raw = json.dumps(payload)
    assert ms.extract_payload("说明文字\n\n```json\n" + raw + "\n```\n尾巴") == payload
    assert ms.extract_payload(raw) == payload
    assert ms.extract_payload("前言 " + raw + " 后记") == payload


@pytest.mark.parametrize("body", ["", "   ", "没有 JSON 的正文", "```json\n{oops\n```"])
def test_extract_reports_paste_mistakes(body):
    with pytest.raises(ms.MarksPayloadError):
        ms.extract_payload(body)


# ---------------------------------------------------------------------------
# storage and cross-device merge
# ---------------------------------------------------------------------------

def test_write_then_load_round_trips(tmp_path):
    path = ms.write_device(tmp_path, ms.validate_payload(_payload()))
    assert path == tmp_path / "marks" / "dev-1a2b3c4d.json"
    merged = ms.load_all(tmp_path)
    assert merged["doi:10.1/x"]["state"] == "to-read"
    assert merged["doi:10.1/x"]["device"] == "dev-1a2b3c4d"


def test_the_newest_mark_wins_across_devices(tmp_path):
    ms.write_device(tmp_path, ms.validate_payload(_payload(
        device="dev-laptop01",
        **{"doi:10.1/x": {"state": "to-read", "at": "2026-09-20T00:00:00Z"}})))
    ms.write_device(tmp_path, ms.validate_payload(_payload(
        device="dev-desktop1",
        **{"doi:10.1/x": {"state": "read", "at": "2026-09-22T00:00:00Z"},
           "doi:10.1/y": {"state": "interesting", "at": "2026-09-22T00:00:00Z"}})))
    merged = ms.load_all(tmp_path)
    assert merged["doi:10.1/x"]["state"] == "read"
    assert merged["doi:10.1/x"]["device"] == "dev-desktop1"
    assert merged["doi:10.1/y"]["state"] == "interesting"


def test_a_corrupt_device_file_does_not_break_the_merge(tmp_path):
    ms.write_device(tmp_path, ms.validate_payload(_payload()))
    (tmp_path / "marks" / "dev-broken01.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "marks" / "dev-wrong001.json").write_text('{"schema_version": 99}',
                                                          encoding="utf-8")
    merged = ms.load_all(tmp_path)
    assert list(merged) == ["doi:10.1/x"]


def test_by_state_filters_and_orders_newest_first(tmp_path):
    merged = {
        "doi:a": {"state": "to-read", "at": "2026-09-20T00:00:00Z"},
        "doi:b": {"state": "to-read", "at": "2026-09-22T00:00:00Z"},
        "doi:c": {"state": "read", "at": "2026-09-23T00:00:00Z"},
    }
    assert [k for k, _ in ms.by_state(merged, "to-read")] == ["doi:b", "doi:a"]
    assert ms.load_all(tmp_path) == {}  # no marks dir at all is not an error


# ---------------------------------------------------------------------------
# the CLI the workflow runs
# ---------------------------------------------------------------------------

def test_cli_writes_the_device_file_and_summarises(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_BODY", "```json\n" + json.dumps(_payload()) + "\n```")
    summary = tmp_path / "summary.md"
    code = apply_marks_sync.main([
        "--body-env", "ISSUE_BODY", "--data-root", str(tmp_path),
        "--summary-file", str(summary)])
    assert code == 0
    assert (tmp_path / "marks" / "dev-1a2b3c4d.json").exists()
    assert "待阅读 1 条" in summary.read_text(encoding="utf-8")


def test_cli_rejects_a_bad_payload_without_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ISSUE_BODY", "```json\n{\"schema_version\": 1, "
                                     "\"device\": \"../evil\", \"marks\": {}}\n```")
    summary = tmp_path / "summary.md"
    code = apply_marks_sync.main([
        "--body-env", "ISSUE_BODY", "--data-root", str(tmp_path),
        "--summary-file", str(summary)])
    assert code == 1
    assert not (tmp_path / "marks").exists()
    assert "rejected" in summary.read_text(encoding="utf-8")
    assert "::error::" in capsys.readouterr().out


def test_cli_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("ISSUE_BODY", json.dumps(_payload()))
    code = apply_marks_sync.main([
        "--body-env", "ISSUE_BODY", "--data-root", str(tmp_path), "--dry-run"])
    assert code == 0
    assert not (tmp_path / "marks").exists()


# ---------------------------------------------------------------------------
# workflow contract — the other half of the trust boundary
# ---------------------------------------------------------------------------

def _workflow() -> dict:
    return yaml.safe_load(
        (REPO_ROOT / ".github/workflows/marks-sync.yml").read_text(encoding="utf-8"))


def test_only_the_owner_can_trigger_a_sync():
    condition = _workflow()["jobs"]["sync"]["if"]
    assert "github.event.issue.user.login == github.repository_owner" in condition
    assert "marks-sync" in condition


def test_the_issue_body_is_never_interpolated_into_a_shell_command():
    steps = _workflow()["jobs"]["sync"]["steps"]
    for step in steps:
        assert "github.event.issue.body" not in (step.get("run") or "")
    # It reaches the validator through the environment instead.
    apply = next(s for s in steps if s.get("id") == "apply")
    assert apply["env"]["ISSUE_BODY"] == "${{ github.event.issue.body }}"
    assert "--body-env ISSUE_BODY" in apply["run"]
    # Exactly one live reference in the parsed workflow; the other mention in
    # the file is the comment that explains why.
    live = [step.get("env", {}).get("ISSUE_BODY") for step in steps]
    assert live.count("${{ github.event.issue.body }}") == 1


def test_the_sync_serialises_with_the_other_writers_and_pushes_with_retry():
    workflow = _workflow()
    assert workflow["concurrency"]["group"] == "research-radar-writer"
    commit = next(s for s in workflow["jobs"]["sync"]["steps"]
                  if s.get("name") == "Commit the synced marks")
    assert "scripts/git_push_retry.sh" in commit["run"]
    assert "git add data/marks/" in commit["run"]


# ---------------------------------------------------------------------------
# browser side
# ---------------------------------------------------------------------------

def test_the_issue_hand_off_needs_no_credential():
    # ADR-0032's route must keep working on its own. ADR-0033 later added an
    # OPTIONAL token for automatic sync, so the invariant is no longer "the
    # bundle mentions no token" but "this route never consults one".
    assert "rui-sync-marks" in UI_JS and "rui-sync-panel" in UI_JS
    assert "labels=marks-sync" in UI_JS
    assert "issues/new" in UI_JS
    handoff = UI_JS.split("var syncBtn = document.getElementById")[1]                    .split("// ---- library.html: the automatic-sync settings")[0]
    for forbidden in ("syncToken", "Authorization", "api.github.com"):
        assert forbidden not in handoff, forbidden


def test_the_device_id_matches_what_the_validator_accepts():
    assert '/^[a-z0-9][a-z0-9_-]{2,31}$/' in UI_JS
    assert ms.DEVICE_RE.pattern == "^[a-z0-9][a-z0-9_-]{2,31}$"
    assert ms.DEVICE_RE.match("dev-1a2b3c4d")


def test_the_payload_is_always_shown_not_only_put_in_a_url():
    sync = UI_JS.split('id="rui-sync-marks"')[0]  # constants live above the handler
    assert "SYNC_URL_BUDGET" in sync
    block = UI_JS.split("var syncBtn")[1]
    assert "area.readOnly = true" in block
    assert "已复制" in block and "自动复制被拒绝" in block
    # A payload too long for a URL still gets a submit link, just unfilled.
    assert "需粘贴" in block and "已预填" in block


def test_the_library_page_offers_the_sync():
    from render import build_pages
    library = build_pages._render_library_page()
    assert 'id="rui-sync-marks"' in library
    assert 'id="rui-sync-panel"' in library
    assert "data/marks/" in library
