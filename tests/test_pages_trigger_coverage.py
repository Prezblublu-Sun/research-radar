"""Every writer whose data a page renders must be able to publish it.

A push made by a workflow with `GITHUB_TOKEN` does NOT fire the `push`
event, so `pages.yml` cannot rely on its `push:` trigger for bot commits —
it lists the writers under `workflow_run:` instead. A writer missing from
that list commits its data and the site silently never rebuilds, which is
exactly what happened to `manual-random-reading` on 2026-09-25: the backfill
committed six days of random reading and the page kept showing its empty
state.

Run with:
    pytest tests/test_pages_trigger_coverage.py
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Writers whose output no published page renders, so a rebuild would be
# wasted Actions minutes. Each must be covered by pages.yml's paths-ignore.
EXEMPT = {
    "marks-sync": "data/marks/**",
    "marks-digest": "data/digest/**",
}


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _on(document: dict) -> dict:
    # PyYAML reads the bare key `on:` as the boolean True.
    return document.get(True) or document.get("on") or {}


def _writers() -> dict[str, pathlib.Path]:
    """Workflows that commit and push to main."""
    found = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "git_push_retry.sh" not in text and "git push" not in text:
            continue
        found[_load(path.name).get("name") or path.stem] = path
    return found


@pytest.fixture(scope="module")
def pages() -> dict:
    return _on(_load("pages.yml"))


def test_every_data_writer_can_trigger_a_rebuild(pages):
    triggers = set(pages["workflow_run"]["workflows"])
    ignored = set(pages["push"]["paths-ignore"])
    for name in _writers():
        if name in EXEMPT:
            assert EXEMPT[name] in ignored, (
                f"{name} is exempt from triggering a rebuild, so "
                f"{EXEMPT[name]} must be in pages.yml paths-ignore")
            assert name not in triggers, f"{name} is exempt but also listed"
            continue
        assert name in triggers, (
            f"{name} commits data but is not in pages.yml's workflow_run "
            f"list; its commits would never be published, because a push "
            f"made with GITHUB_TOKEN does not fire the push event")


def test_the_random_reading_backfill_is_one_of_them(pages):
    assert "manual-random-reading" in set(pages["workflow_run"]["workflows"])
    assert "data/random_reading/**" not in set(pages["push"]["paths-ignore"])


def test_the_exempt_writers_really_are_exempt():
    # If a page starts rendering marks or the digest, this test is the
    # reminder that two workflows and one paths-ignore have to change too.
    for name, path in _writers().items():
        if name not in EXEMPT:
            continue
        body = path.read_text(encoding="utf-8")
        assert EXEMPT[name].replace("/**", "/") in body, (
            f"{name} no longer writes {EXEMPT[name]}; revisit its exemption")
