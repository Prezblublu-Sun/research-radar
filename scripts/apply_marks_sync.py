"""Commit a marks payload pasted into a GitHub issue (ADR-0032).

Run by .github/workflows/marks-sync.yml, which has already checked that the
issue carries the `marks-sync` label and was opened by the repository owner.
The body still reaches this script as untrusted text, so everything it
contains goes through pipeline.marks_store.validate_payload before a byte is
written, and the body is read from an environment variable rather than being
interpolated into a shell command.

    python -m scripts.apply_marks_sync --body-env ISSUE_BODY
    python -m scripts.apply_marks_sync --body-file body.txt --dry-run

Exit code 0 on success, 1 on a rejected payload; the workflow reports the
message back as an issue comment either way.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import marks_store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--body-env", help="environment variable holding the issue body")
    source.add_argument("--body-file", type=pathlib.Path, help="file holding the issue body")
    parser.add_argument("--data-root", type=pathlib.Path, default=ROOT / "data")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate and report, write nothing")
    parser.add_argument("--summary-file", type=pathlib.Path,
                        help="write the human-readable result here too")
    args = parser.parse_args(argv)

    if args.body_env:
        body = os.environ.get(args.body_env, "")
    else:
        body = args.body_file.read_text(encoding="utf-8")

    try:
        payload = marks_store.validate_payload(marks_store.extract_payload(body))
    except marks_store.MarksPayloadError as error:
        message = f"marks sync rejected: {error}"
        print(f"::error::{message}")
        _write_summary(args.summary_file, message)
        return 1

    counts: dict[str, int] = {}
    for mark in payload["marks"].values():
        key = mark["state"] or "note-only"
        counts[key] = counts.get(key, 0) + 1
    notes = sum(1 for mark in payload["marks"].values() if mark["note"])

    if args.dry_run:
        message = (f"marks sync OK (dry run): device {payload['device']}, "
                   f"{len(payload['marks'])} mark(s) {counts}, {notes} with notes")
        print(message)
        _write_summary(args.summary_file, message)
        return 0

    path = marks_store.write_device(args.data_root, payload)
    merged = marks_store.load_all(args.data_root)
    message = (
        f"已同步设备 `{payload['device']}`：{len(payload['marks'])} 条标记"
        f"（{json.dumps(counts, ensure_ascii=False)}，其中 {notes} 条带笔记），"
        f"写入 `{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}`。"
        f"\n\n合并全部设备后共 {len(merged)} 条标记，"
        f"待阅读 {len(marks_store.by_state(merged, 'to-read'))} 条。"
    )
    print(message)
    _write_summary(args.summary_file, message)
    return 0


def _write_summary(path: pathlib.Path | None, message: str) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
