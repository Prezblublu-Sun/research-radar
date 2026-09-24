"""Turn the synced reading marks into a 待阅读 digest (ADR-0032 §"digest").

ADR-0032's stated motivation was "a daily digest of the papers they marked
待阅读, which a server job cannot assemble from browser-only state". This is
that job. It reads the merged marks, renders the current to-read list, and
works out which papers are *new* since the last run.

The workflow keeps one standing issue:

  * the issue **body** is rewritten every run with the whole current list —
    editing a body sends no notification, so this is free;
  * a **comment** is posted only when papers appeared since the last run —
    a comment does notify, and that notification is the email the reader
    asked for;
  * nothing new means no comment and therefore no mail.

"New" is a set difference, not a timestamp: the state file remembers the
identity keys that were to-read at the last run, so editing a note on an old
mark does not resurface it, and putting a paper back into 待阅读 after
clearing it does. The state is bounded by the size of the list itself.

    python -m scripts.marks_digest --out-dir "$RUNNER_TEMP"
    python -m scripts.marks_digest --dry-run

The mark fields are free text that reached this repository from a browser
(through the ADR-0032 trust boundary, which caps their length but does not
care what is in them), so everything interpolated into Markdown is escaped
here rather than trusted.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import marks_store  # noqa: E402

STATE_VERSION = 1
# An issue body caps at 65,536 characters and nobody reads 500 rows anyway.
BODY_LIMIT = 200
COMMENT_LIMIT = 50
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _plain(value: object, limit: int = 300) -> str:
    """Collapse a stored field to one safe line of Markdown text."""
    text = CONTROL_RE.sub(" ", str(value or ""))
    text = " ".join(text.split())
    # `[` and `]` would break out of link text; backslash escapes them, and
    # escaping the backslash first keeps the escape from being escaped away.
    for char in ("\\", "[", "]", "`", "<", ">", "|", "*", "_"):
        text = text.replace(char, "\\" + char)
    return text[:limit]


def paper_url(identity_key: str) -> str:
    """A resolvable link for an identity key, or "" when there is none."""
    scheme, _, rest = identity_key.partition(":")
    if not rest:
        return ""
    # Only "/" stays literal: a DOI may contain parentheses or angle
    # brackets, which would break out of a Markdown link target. Resolvers
    # accept the percent-encoded form.
    quoted = urllib.parse.quote(rest, safe="/")
    if scheme == "doi":
        return f"https://doi.org/{quoted}"
    if scheme == "arxiv":
        return f"https://arxiv.org/abs/{quoted}"
    if scheme == "pmid":
        return f"https://pubmed.ncbi.nlm.nih.gov/{quoted}/"
    if scheme == "openalex":
        return f"https://openalex.org/{quoted}"
    return ""  # noid: the renderer's fallback — nothing to link to


def render_row(identity_key: str, mark: dict) -> str:
    """One Markdown list item for a paper."""
    title = _plain(mark.get("title")) or _plain(identity_key)
    url = paper_url(identity_key)
    head = f"[{title}]({url})" if url else title

    facts = [_plain(mark.get("date"), 32), _plain(mark.get("direction"), 64),
             _plain(mark.get("priority"), 32)]
    for tag in (mark.get("tags") or []):
        facts.append("#" + _plain(tag, marks_store.MAX_TAG))
    tail = " · ".join(fact for fact in facts if fact)

    row = f"- {head}" + (f"\n  {tail}" if tail else "")
    note = _plain(mark.get("note"), 400)
    if note:
        row += f"\n  > {note}"
    return row


def render_list(pairs: list[tuple[str, dict]], limit: int) -> str:
    rows = [render_row(key, mark) for key, mark in pairs[:limit]]
    if len(pairs) > limit:
        rows.append(f"- …另有 {len(pairs) - limit} 篇，见 "
                    "[阅读清单](https://prezblublu-sun.github.io/research-radar/reading.html)")
    return "\n".join(rows)


def load_state(path: pathlib.Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": STATE_VERSION, "keys": []}
    if not isinstance(state, dict):
        return {"schema_version": STATE_VERSION, "keys": []}
    keys = state.get("keys")
    state["keys"] = sorted(k for k in keys if isinstance(k, str)) \
        if isinstance(keys, list) else []
    return state


def build_digest(marks: dict[str, dict], previous: list[str]) -> dict:
    """Split the current 待阅读 list into new / carried over / cleared."""
    pending = marks_store.by_state(marks, "to-read")
    current = {key for key, _ in pending}
    seen = set(previous)
    new = [(key, mark) for key, mark in pending if key not in seen]
    return {
        "pending": pending,
        "new": new,
        "cleared": sorted(seen - current),
        "keys": sorted(current),
        "counts": {state: len(marks_store.by_state(marks, state))
                   for state in ("to-read", "read", "ignore")},
        "tags": marks_store.tag_counts(marks),
    }


def render_body(digest: dict) -> str:
    counts = digest["counts"]
    lines = [
        "## 待阅读",
        "",
        f"共 **{len(digest['pending'])}** 篇。这条正文每次运行都会整体刷新；"
        "新增的论文会单独回复一条评论（那条才会发邮件）。",
        "",
    ]
    lines.append(render_list(digest["pending"], BODY_LIMIT) if digest["pending"]
                 else "_目前没有待阅读的论文。_")
    lines += [
        "",
        "---",
        "",
        f"全部标记：待阅读 {counts['to-read']} · 已阅读 {counts['read']} · "
        f"忽略 {counts['ignore']}",
    ]
    if digest["tags"]:
        chips = " · ".join(f"{_plain(tag, marks_store.MAX_TAG)} {count}"
                           for tag, count in list(digest["tags"].items())[:12])
        lines.append(f"标签：{chips}")
    lines += [
        "",
        "由 `.github/workflows/marks-digest.yml` 自动维护（ADR-0032）。"
        "标记来自 `data/marks/`，在 "
        "[网站](https://prezblublu-sun.github.io/research-radar/) 上标注即可。",
    ]
    return "\n".join(lines)


def render_comment(digest: dict) -> str:
    """Only what is new.

    Papers that *left* the list are deliberately not named. A silent run
    still advances the watermark, so by the time a comment happens the
    departures it could report are an arbitrary slice of the ones since the
    last run — an accurate number that reads as a wrong one. The body always
    shows the truth, and the running total below is enough.
    """
    return "\n".join([
        f"### 新增 {len(digest['new'])} 篇待阅读", "",
        render_list(digest["new"], COMMENT_LIMIT), "",
        f"当前待阅读共 {len(digest['pending'])} 篇，完整清单见上方正文。",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=pathlib.Path, default=ROOT / "data")
    parser.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "build",
                        help="where to write digest-body.md / digest-comment.md")
    parser.add_argument("--dry-run", action="store_true",
                        help="render and report, but do not touch the state file")
    parser.add_argument("--github-output", type=pathlib.Path,
                        help="append has_new / new_count / pending_count here")
    args = parser.parse_args(argv)

    state_path = args.data_root / "digest" / "to-read.json"
    state = load_state(state_path)
    marks = marks_store.load_all(args.data_root)
    digest = build_digest(marks, state["keys"])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "digest-body.md").write_text(render_body(digest), encoding="utf-8")
    comment_path = args.out_dir / "digest-comment.md"
    if digest["new"]:
        comment_path.write_text(render_comment(digest), encoding="utf-8")
    else:
        # Never leave a previous run's comment lying around for this one to
        # post: "no new papers" has to mean no file and therefore no mail.
        comment_path.unlink(missing_ok=True)

    # Only when the membership actually changed. `updated_at` moves on every
    # write, so rewriting unconditionally would commit a timestamp to main
    # every single day for nothing — and would make the field meaningless,
    # since what it should record is when the list last changed.
    changed = digest["keys"] != state["keys"]
    if not args.dry_run and changed:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            "schema_version": STATE_VERSION,
            "updated_at": marks_store.utc_now(),
            "keys": digest["keys"],
        }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"待阅读 {len(digest['pending'])} 篇，新增 {len(digest['new'])} 篇，"
          f"已离开 {len(digest['cleared'])} 篇。")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"has_new={'true' if digest['new'] else 'false'}\n")
            handle.write(f"new_count={len(digest['new'])}\n")
            handle.write(f"pending_count={len(digest['pending'])}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
