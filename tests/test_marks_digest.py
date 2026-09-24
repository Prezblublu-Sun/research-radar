"""ADR-0032 §digest: the 待阅读 list becomes one standing issue and one mail.

The contract worth pinning is not the wording, it is the noise: a run with
nothing new must produce no comment (and therefore no mail), a paper must be
reported exactly once, and nothing a browser wrote may reach the issue
unescaped or reach a shell at all.

Run with:
    pytest tests/test_marks_digest.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import marks_digest as md  # noqa: E402

WORKFLOW = (ROOT / ".github" / "workflows" / "marks-digest.yml").read_text(encoding="utf-8")


def _device(tmp_path: pathlib.Path, device: str, marks: dict) -> None:
    root = tmp_path / "marks"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{device}.json").write_text(json.dumps({
        "schema_version": 1, "device": device,
        "updated_at": "2026-09-24T00:00:00Z", "marks": marks,
    }, ensure_ascii=False), encoding="utf-8")


def _mark(state="to-read", **extra):
    base = {"state": state, "at": "2026-09-24T10:00:00Z", "title": "T",
            "date": "2026-09-20", "direction": "fea_surrogate",
            "priority": "High", "note": "", "tags": []}
    base.update(extra)
    return base


def _run(tmp_path, out=None, dry_run=False):
    out = out or (tmp_path / "out")
    argv = ["--data-root", str(tmp_path), "--out-dir", str(out)]
    if dry_run:
        argv.append("--dry-run")
    assert md.main(argv) == 0
    body = (out / "digest-body.md").read_text(encoding="utf-8")
    comment_path = out / "digest-comment.md"
    comment = comment_path.read_text(encoding="utf-8") if comment_path.exists() else None
    return body, comment


# ---------------------------------------------------------------------------
# What gets reported, and how often
# ---------------------------------------------------------------------------

def test_a_paper_is_mailed_once_and_then_only_listed(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(title="First paper")})

    body, comment = _run(tmp_path)
    assert "First paper" in body
    assert comment is not None and "First paper" in comment

    # Second run, nothing changed: the body is still right, but there is no
    # comment — which is the whole point, because a comment is a mail.
    body, comment = _run(tmp_path)
    assert "First paper" in body
    assert comment is None


def test_a_second_run_does_not_reuse_the_first_runs_comment_file(tmp_path):
    # Same out-dir twice: a stale file left on disk would be posted again.
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark()})
    out = tmp_path / "out"
    _run(tmp_path, out)
    assert (out / "digest-comment.md").exists()
    _run(tmp_path, out)
    assert not (out / "digest-comment.md").exists()


def test_editing_an_old_mark_does_not_resurface_it(tmp_path):
    # `at` moves on every write (ADR-0034), so a timestamp watermark would
    # re-report a paper whose note was touched. Membership is a set diff.
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark()})
    _run(tmp_path)
    _device(tmp_path, "dev-laptop01", {
        "doi:10.1/a": _mark(note="想起来要看方法部分", at="2026-09-25T10:00:00Z")})
    body, comment = _run(tmp_path)
    assert comment is None
    assert "想起来要看方法部分" in body


def test_putting_a_paper_back_reports_it_again(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark()})
    _run(tmp_path)
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(state="read")})
    _, comment = _run(tmp_path)
    assert comment is None
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(state="to-read")})
    _, comment = _run(tmp_path)
    assert comment is not None


def test_a_paper_leaving_the_list_mails_nothing_and_is_not_named(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(title="Leaving"),
                                       "doi:10.1/b": _mark()})
    _run(tmp_path)
    # a is read now and nothing new arrived: silence — but the watermark
    # still moves, which is exactly why the next comment cannot honestly
    # talk about departures, and does not try to.
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(state="read"),
                                       "doi:10.1/b": _mark()})
    body, comment = _run(tmp_path)
    assert comment is None
    assert "Leaving" not in body
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(state="read"),
                                       "doi:10.1/b": _mark(),
                                       "doi:10.1/c": _mark(title="Newcomer")})
    _, comment = _run(tmp_path)
    assert "Newcomer" in comment
    assert "不在待阅读" not in comment
    assert "当前待阅读共 2 篇" in comment


def test_a_dry_run_reports_without_consuming_the_papers(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark()})
    _, comment = _run(tmp_path, dry_run=True)
    assert comment is not None
    assert not (tmp_path / "digest" / "to-read.json").exists()
    _, comment = _run(tmp_path)          # the real run still has them
    assert comment is not None


def test_marks_from_every_device_are_merged(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(title="From laptop")})
    _device(tmp_path, "dev-desktop1", {"doi:10.1/b": _mark(title="From desktop")})
    body, _ = _run(tmp_path)
    assert "From laptop" in body and "From desktop" in body


def test_only_to_read_is_mailed_but_the_others_are_counted(tmp_path):
    _device(tmp_path, "dev-laptop01", {
        "doi:10.1/a": _mark(title="Waiting"),
        "doi:10.1/b": _mark(state="read", title="Finished", tags=["有启发"]),
        "doi:10.1/c": _mark(state="ignore", title="Discarded"),
    })
    body, comment = _run(tmp_path)
    assert "Waiting" in body
    assert "Finished" not in body and "Discarded" not in body
    assert "待阅读 1 · 已阅读 1 · 忽略 1" in body
    assert "有启发 1" in body                   # the tag census rides along
    assert "Finished" not in comment


def test_an_empty_list_renders_instead_of_crashing(tmp_path):
    (tmp_path / "marks").mkdir()
    body, comment = _run(tmp_path)
    assert "目前没有待阅读的论文" in body
    assert comment is None


def test_a_long_list_is_capped_with_a_pointer_to_the_site(tmp_path):
    _device(tmp_path, "dev-laptop01", {
        f"doi:10.1/p{n}": _mark(title=f"Paper {n}",
                                at=f"2026-09-24T10:{n % 60:02d}:00Z")
        for n in range(md.BODY_LIMIT + 5)})
    body, comment = _run(tmp_path)
    assert f"另有 5 篇" in body
    assert "reading.html" in body
    assert f"另有 {md.BODY_LIMIT + 5 - md.COMMENT_LIMIT} 篇" in comment


# ---------------------------------------------------------------------------
# The marks are untrusted text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("A [bracket] title", r"A \[bracket\] title"),
    ("closes #1 and <img src=x>", r"closes #1 and \<img src=x\>"),
    ("back`tick`", r"back\`tick\`"),
    ("line\nbreak", "line break"),
    ("bell\x07char", "bell char"),
])
def test_a_title_cannot_break_out_of_the_markdown_it_is_placed_in(tmp_path, title, expected):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark(title=title)})
    body, _ = _run(tmp_path)
    assert expected in body


def test_a_doi_with_parentheses_stays_inside_its_link_target(tmp_path):
    # Biomechanics DOIs are full of them and an unbalanced ")" would end the
    # Markdown link early, leaving the rest of the URL as page text.
    key = "doi:10.1016/S0021-9290(02)00123-4"
    _device(tmp_path, "dev-laptop01", {key: _mark()})
    body, _ = _run(tmp_path)
    assert "https://doi.org/10.1016/S0021-9290%2802%2900123-4" in body
    assert "(02)" not in body


def test_every_identity_scheme_links_somewhere_sensible():
    assert md.paper_url("doi:10.1/x") == "https://doi.org/10.1/x"
    assert md.paper_url("arxiv:2509.12345") == "https://arxiv.org/abs/2509.12345"
    assert md.paper_url("pmid:12345") == "https://pubmed.ncbi.nlm.nih.gov/12345/"
    assert md.paper_url("openalex:W123") == "https://openalex.org/W123"
    assert md.paper_url("noid:abc") == ""      # nothing to resolve
    assert md.paper_url("doi:") == ""


def test_a_paper_with_no_resolvable_link_is_still_listed(tmp_path):
    _device(tmp_path, "dev-laptop01", {"noid:abc123": _mark(title="Unlinkable")})
    body, _ = _run(tmp_path)
    assert "Unlinkable" in body
    assert "](" not in body.split("---")[0].split("\n\n")[2]  # no empty link


def test_a_corrupt_state_file_costs_a_repeat_not_a_crash(tmp_path):
    _device(tmp_path, "dev-laptop01", {"doi:10.1/a": _mark()})
    _run(tmp_path)
    (tmp_path / "digest" / "to-read.json").write_text("{not json", encoding="utf-8")
    _, comment = _run(tmp_path)
    assert comment is not None        # reported again, rather than lost


# ---------------------------------------------------------------------------
# The workflow around it
# ---------------------------------------------------------------------------

def test_the_body_is_refreshed_silently_and_only_a_comment_mails():
    # Editing an issue body sends no notification; commenting does. The
    # whole no-noise design rests on that split.
    assert "gh issue edit" in WORKFLOW
    assert "gh issue comment" in WORKFLOW
    assert 'if [ -f "$RUNNER_TEMP/digest/digest-comment.md" ]; then' in WORKFLOW
    # A freshly opened issue already carries the list in its creation mail.
    assert 'rm -f "$RUNNER_TEMP/digest/digest-comment.md"' in WORKFLOW


def test_no_issue_is_opened_just_to_say_there_is_nothing():
    assert "pending_count" in WORKFLOW
    assert 'if [ "${{ steps.build.outputs.pending_count }}" = "0" ]; then' in WORKFLOW


def test_the_watermark_is_committed_last_so_a_failure_repeats_rather_than_loses():
    commit_at = WORKFLOW.index("Remember what was reported")
    assert commit_at > WORKFLOW.index("Comment when there is something new")
    assert "git add data/digest/" in WORKFLOW
    assert "scripts/git_push_retry.sh main 5" in WORKFLOW
    # Committing to main is serialised with every other writer.
    assert "group: research-radar-writer" in WORKFLOW


def test_the_digest_state_does_not_trigger_a_site_rebuild():
    pages = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert '- "data/digest/**"' in pages


def test_nothing_from_a_mark_is_interpolated_into_a_shell():
    # The marks are browser-supplied. Titles and notes travel as files, and
    # the only ${{ }} in a run: block are the job's own numbers.
    for fragment in ("--body-file", "digest-body.md"):
        assert fragment in WORKFLOW
    assert "github.event" not in WORKFLOW           # no event payload at all
    for expansion in ("title", "note", "mark"):
        assert "${{ steps.build.outputs." + expansion not in WORKFLOW


def test_the_job_can_be_rehearsed_without_touching_an_issue():
    assert "dry_run" in WORKFLOW
    assert "--dry-run" in WORKFLOW
    assert "if: ${{ !inputs.dry_run }}" in WORKFLOW
