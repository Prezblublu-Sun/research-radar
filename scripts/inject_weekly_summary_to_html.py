"""scripts/inject_weekly_summary_to_html.py — ADR-0026 Phase M.5.

Inject a rendered weekly markdown report (reports/weekly/{YYYY-Www}_周报.md)
into the matching cron-generated HTML (docs/weekly/{YYYY-Www}.html),
replacing the "coming soon" placeholder. Render configuration of an
existing layered artifact — no new pipeline computation, no markdown
mutation, no network. Re-runnable: a prior weekly-summary block is
replaced in place rather than duplicated.
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = ROOT / "reports" / "weekly"
DEFAULT_DOCS_DIR = ROOT / "docs" / "weekly"

WEEK_FILE_RE = re.compile(r"^(\d{4}-W\d{2})_周报\.md$")
WEEK_ID_RE = re.compile(r"^\d{4}-W\d{2}$")

# The cron placeholder. Tolerant of whitespace inside the opening tag and of
# single-line vs multi-line content; the placeholder body contains no nested
# <div>, so the lazy .*? stops at the first </div>.
PLACEHOLDER_RE = re.compile(
    r'<div\s+class="coming-soon"\s*>.*?</div>',
    re.DOTALL,
)
# Idempotent re-injection target.
EXISTING_RE = re.compile(
    r'<div\s+class="weekly-summary"\s*>.*?</div>',
    re.DOTALL,
)


# --- Markdown renderer (stdlib only) -------------------------------------- #

_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_INLINE_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_INLINE_STRONG_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_INLINE_EM_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
# Blockquotes are detected after html.escape, where ">" has become "&gt;".
_QUOTE_PREFIX = "&gt;"


def _render_inline(text: str) -> str:
    # Code and link spans are extracted to placeholders first so their inner
    # asterisks/brackets cannot be misparsed as strong/em later.
    placeholders: list[str] = []

    def store(rendered: str) -> str:
        placeholders.append(rendered)
        return f"\x00P{len(placeholders) - 1}\x00"

    text = _INLINE_CODE_RE.sub(lambda m: store(f"<code>{m.group(1)}</code>"), text)
    text = _INLINE_LINK_RE.sub(
        lambda m: store(f'<a href="{m.group(2)}">{m.group(1)}</a>'), text,
    )
    text = _INLINE_STRONG_RE.sub(r"<strong>\1</strong>", text)
    text = _INLINE_EM_RE.sub(r"<em>\1</em>", text)
    return re.sub(
        r"\x00P(\d+)\x00", lambda m: placeholders[int(m.group(1))], text,
    )


def render_markdown(md_text: str) -> str:
    """Render a constrained Markdown subset to an HTML fragment.

    Supported: # / ## / ### headings, paragraphs, `- `/`* ` bullet lists
    (nested flattened, indented continuation lines join the previous bullet),
    `> ` blockquotes, **strong**, *em*, `code`, [text](url). All text is
    HTML-escaped before inline regex apply, so raw HTML cannot execute.
    Tables / fenced code / images / footnotes are unrecognised and fall
    through as escaped paragraph text.
    """
    out: list[str] = []
    para: list[str] = []
    bullets: list[str] = []
    quote: list[str] = []

    def flush_para() -> None:
        if para:
            joined = " ".join(para).strip()
            if joined:
                out.append(f"<p>{_render_inline(joined)}</p>")
            para.clear()

    def flush_bullets() -> None:
        if bullets:
            items = "".join(f"<li>{_render_inline(s)}</li>" for s in bullets)
            out.append(f"<ul>{items}</ul>")
            bullets.clear()

    def flush_quote() -> None:
        if quote:
            joined = " ".join(quote).strip()
            out.append(f"<blockquote>{_render_inline(joined)}</blockquote>")
            quote.clear()

    def flush_all() -> None:
        flush_para()
        flush_bullets()
        flush_quote()

    # HTML-escape each line first; the structural markers (# - * > [ ] ( ))
    # are not affected by html.escape, so block-level regexes still match.
    for raw in md_text.splitlines():
        line = html.escape(raw)
        if not line.strip():
            flush_all()
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush_all()
            level = len(m.group(1))
            out.append(f"<h{level}>{_render_inline(m.group(2).strip())}</h{level}>")
            continue

        m = _BULLET_RE.match(line)
        if m:
            flush_para()
            flush_quote()
            bullets.append(m.group(1).strip())
            continue

        if line.startswith(_QUOTE_PREFIX):
            flush_para()
            flush_bullets()
            content = line[len(_QUOTE_PREFIX):].lstrip()
            quote.append(content)
            continue

        # Indented continuation of a bullet: join into the previous item
        # instead of starting a paragraph that would break the <ul>.
        if bullets and (raw.startswith(" ") or raw.startswith("\t")):
            bullets[-1] = (bullets[-1] + " " + line.strip()).strip()
            continue

        flush_bullets()
        flush_quote()
        para.append(line.strip())

    flush_all()
    return "\n".join(out)


# --- Injection ------------------------------------------------------------ #

def _inject_into_html(html_text: str, fragment: str) -> str | None:
    # Replace the coming-soon placeholder, or — if absent — a previously
    # injected div.weekly-summary block. Returns None if neither is found.
    wrapped = f'<div class="weekly-summary">\n{fragment}\n</div>'
    new_text, n = PLACEHOLDER_RE.subn(wrapped, html_text, count=1)
    if n:
        return new_text
    new_text, n = EXISTING_RE.subn(wrapped, html_text, count=1)
    if n:
        return new_text
    return None


def _inject_one(
    week_id: str,
    reports_dir: pathlib.Path,
    docs_dir: pathlib.Path,
    *,
    dry_run: bool,
) -> tuple[str, str]:
    # Returns (status, message): 'ok' | 'skipped' (input missing) | 'errored'.
    if not WEEK_ID_RE.match(week_id):
        return "errored", f"invalid week id: {week_id}"
    md_path = reports_dir / f"{week_id}_周报.md"
    html_path = docs_dir / f"{week_id}.html"
    if not md_path.exists():
        return "skipped", f"no markdown report for {week_id}, skipping"
    if not html_path.exists():
        return "skipped", f"no HTML target for {week_id}"

    md_text = md_path.read_text(encoding="utf-8")
    fragment = render_markdown(md_text)
    html_text = html_path.read_text(encoding="utf-8")
    new_html = _inject_into_html(html_text, fragment)
    if new_html is None:
        return "errored", f"no injection target found in HTML for {week_id}"

    if not dry_run:
        html_path.write_text(new_html, encoding="utf-8")
    label = "dry-run" if dry_run else "injected"
    return "ok", (
        f"{label}: {week_id} "
        f"({len(md_text)} chars markdown → {len(fragment)} chars HTML)"
    )


def iter_week_ids(reports_dir: pathlib.Path) -> Iterable[str]:
    weeks: list[str] = []
    for p in reports_dir.glob("*_周报.md"):
        m = WEEK_FILE_RE.match(p.name)
        if m:
            weeks.append(m.group(1))
    weeks.sort()
    return weeks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--week", help="ISO week id, e.g. 2026-W21")
    grp.add_argument(
        "--all",
        action="store_true",
        help="process every week with a matching markdown report",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(DEFAULT_REPORTS_DIR),
        help="directory with {week}_周报.md files",
    )
    parser.add_argument(
        "--docs-dir",
        default=str(DEFAULT_DOCS_DIR),
        help="directory with {week}.html files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print summary but do not write HTML",
    )
    args = parser.parse_args(argv)

    reports_dir = pathlib.Path(args.reports_dir)
    docs_dir = pathlib.Path(args.docs_dir)

    if args.week:
        status, msg = _inject_one(
            args.week, reports_dir, docs_dir, dry_run=args.dry_run
        )
        if status == "ok":
            print(msg)
            return 0
        print(f"  ! {msg}", file=sys.stderr)
        return 2

    weeks = list(iter_week_ids(reports_dir))
    if not weeks:
        print(f"no _周报.md files in {reports_dir}", file=sys.stderr)
        return 2

    succeeded: list[str] = []
    skipped: list[str] = []
    errored: list[str] = []
    for w in weeks:
        status, msg = _inject_one(
            w, reports_dir, docs_dir, dry_run=args.dry_run
        )
        if status == "ok":
            print(msg)
            succeeded.append(w)
        elif status == "skipped":
            print(f"  - {msg}", file=sys.stderr)
            skipped.append(w)
        else:
            print(f"  ! {msg}", file=sys.stderr)
            errored.append(w)

    print(
        f"\nsummary: {len(succeeded)} succeeded, "
        f"{len(skipped)} skipped, {len(errored)} errored"
    )
    if succeeded:
        print(f"  succeeded: {', '.join(succeeded)}")
    if skipped:
        print(f"  skipped:   {', '.join(skipped)}")
    if errored:
        print(f"  errored:   {', '.join(errored)}")
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
