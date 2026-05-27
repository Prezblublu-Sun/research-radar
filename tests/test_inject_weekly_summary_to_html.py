"""Tests for scripts/inject_weekly_summary_to_html.py (ADR-0026 Phase M.5).

Style mirrors tests/test_build_analytics.py: load the script as a module,
fabricate inputs in tmp_path, drive the public main(...).
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "inject_weekly_summary_to_html.py"

spec = importlib.util.spec_from_file_location(
    "inject_weekly_summary_to_html", SCRIPT,
)
mod = importlib.util.module_from_spec(spec)
sys.modules["inject_weekly_summary_to_html"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


PLACEHOLDER_HTML = (
    "<!doctype html><html lang=\"zh\"><head><title>x</title></head><body>\n"
    "<h1>Research Radar Weekly</h1>\n"
    "<div class=\"coming-soon\">📊 Trend analysis and 📝 LLM weekly summary "
    "coming soon. (Phase 2 — will compare keyword frequency week-over-week, "
    "and add an AI-generated narrative overview.)</div>\n"
    "<h2>Top picks by direction</h2>\n"
    "</body></html>"
)

SAMPLE_MD = (
    "# Sample Weekly\n"
    "\n"
    "This is a paragraph with **bold** and *italic* and "
    "a [link](https://example.com).\n"
    "\n"
    "## Section\n"
    "\n"
    "- item one with **strong**\n"
    "- item two with `code`\n"
    "\n"
    "> a blockquote line\n"
)


def _make_week(tmp_path, week_id="2026-W99", md=SAMPLE_MD, html=PLACEHOLDER_HTML):
    reports = tmp_path / "reports" / "weekly"
    docs = tmp_path / "docs" / "weekly"
    reports.mkdir(parents=True)
    docs.mkdir(parents=True)
    (reports / f"{week_id}_周报.md").write_text(md, encoding="utf-8")
    (docs / f"{week_id}.html").write_text(html, encoding="utf-8")
    return reports, docs


def _run(reports, docs, *extra):
    return mod.main([
        "--reports-dir", str(reports),
        "--docs-dir", str(docs),
        *extra,
    ])


def test_injects_markdown_into_placeholder(tmp_path):
    reports, docs = _make_week(tmp_path)
    rc = _run(reports, docs, "--week", "2026-W99")
    assert rc == 0
    out = (docs / "2026-W99.html").read_text(encoding="utf-8")
    assert 'class="weekly-summary"' in out
    assert "coming-soon" not in out
    assert "coming soon" not in out.lower()
    assert "<h1>Sample Weekly</h1>" in out
    assert "<h2>Section</h2>" in out
    assert "<strong>bold</strong>" in out
    assert "<em>italic</em>" in out
    assert '<a href="https://example.com">link</a>' in out
    assert "<ul>" in out and "<li>" in out
    assert "<blockquote>" in out
    # The page's surrounding HTML must survive.
    assert "<h2>Top picks by direction</h2>" in out
    assert "</body></html>" in out


def test_idempotent(tmp_path):
    reports, docs = _make_week(tmp_path)
    rc1 = _run(reports, docs, "--week", "2026-W99")
    assert rc1 == 0
    first = (docs / "2026-W99.html").read_text(encoding="utf-8")
    assert first.count('class="weekly-summary"') == 1

    # Modify the markdown and re-inject.
    (reports / "2026-W99_周报.md").write_text(
        "# Replacement\n\nA new body.\n", encoding="utf-8",
    )
    rc2 = _run(reports, docs, "--week", "2026-W99")
    assert rc2 == 0
    second = (docs / "2026-W99.html").read_text(encoding="utf-8")

    # Exactly one weekly-summary block — the second run replaced, not appended.
    assert second.count('class="weekly-summary"') == 1
    # New content visible, old content gone.
    assert "<h1>Replacement</h1>" in second
    assert "Sample Weekly" not in second


def test_missing_markdown_errors(tmp_path):
    reports, docs = _make_week(tmp_path)
    (reports / "2026-W99_周报.md").unlink()
    rc = _run(reports, docs, "--week", "2026-W99")
    assert rc == 2


def test_missing_html_errors(tmp_path):
    reports, docs = _make_week(tmp_path)
    (docs / "2026-W99.html").unlink()
    rc = _run(reports, docs, "--week", "2026-W99")
    assert rc == 2


def test_dry_run_no_write(tmp_path):
    reports, docs = _make_week(tmp_path)
    html_path = docs / "2026-W99.html"
    before = html_path.read_bytes()
    rc = _run(reports, docs, "--week", "2026-W99", "--dry-run")
    assert rc == 0
    after = html_path.read_bytes()
    assert before == after, "dry-run must not modify the HTML file"


def test_html_escape_safety(tmp_path):
    nasty_md = (
        "# T\n\n"
        "Look: <script>alert(1)</script> & a literal *star* and `x*y`.\n"
    )
    reports, docs = _make_week(tmp_path, md=nasty_md)
    rc = _run(reports, docs, "--week", "2026-W99")
    assert rc == 0
    out = (docs / "2026-W99.html").read_text(encoding="utf-8")
    # The raw <script> tag must NOT appear executable in the output.
    assert "<script>alert(1)</script>" not in out
    # Its escaped form MUST appear.
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    # The ampersand from the markdown must be escaped, not raw.
    assert " &amp; " in out


def test_renderer_basic():
    out = mod.render_markdown(
        "# H1\n\nbody **bold** *em* `code` [a](https://b)\n"
    )
    assert "<h1>H1</h1>" in out
    assert "<p>" in out
    assert "<strong>bold</strong>" in out
    assert "<em>em</em>" in out
    assert "<code>code</code>" in out
    assert '<a href="https://b">a</a>' in out

    bullets_out = mod.render_markdown("- one\n- two\n- three\n")
    assert bullets_out.count("<li>") == 3
    assert bullets_out.count("<ul>") == 1

    quote_out = mod.render_markdown("> quoted\n> still quoted\n")
    assert quote_out.count("<blockquote>") == 1
    assert "quoted still quoted" in quote_out

    levels = mod.render_markdown("# one\n\n## two\n\n### three\n")
    assert "<h1>one</h1>" in levels
    assert "<h2>two</h2>" in levels
    assert "<h3>three</h3>" in levels

    # Bullet continuation: indented non-bullet line joins the previous item
    # rather than breaking the ul.
    cont = mod.render_markdown("- first\n  continues\n- second\n")
    assert cont.count("<ul>") == 1
    assert cont.count("<li>") == 2
    assert "first continues" in cont


def test_all_flag(tmp_path):
    reports, docs = _make_week(tmp_path, week_id="2026-W98")
    # Add a second week.
    (reports / "2026-W99_周报.md").write_text(SAMPLE_MD, encoding="utf-8")
    (docs / "2026-W99.html").write_text(PLACEHOLDER_HTML, encoding="utf-8")
    rc = _run(reports, docs, "--all")
    assert rc == 0
    for w in ("2026-W98", "2026-W99"):
        out = (docs / f"{w}.html").read_text(encoding="utf-8")
        assert 'class="weekly-summary"' in out


def test_all_continues_past_missing_html(tmp_path):
    # W98 has both files; W99 has markdown but no HTML target.
    reports, docs = _make_week(tmp_path, week_id="2026-W98")
    (reports / "2026-W99_周报.md").write_text(SAMPLE_MD, encoding="utf-8")
    rc = _run(reports, docs, "--all")
    # At least one week succeeded -> exit 0.
    assert rc == 0
    out98 = (docs / "2026-W98.html").read_text(encoding="utf-8")
    assert 'class="weekly-summary"' in out98
