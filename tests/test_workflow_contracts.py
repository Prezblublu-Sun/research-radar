"""Regression checks for writer workflow behavior."""

from __future__ import annotations

import pathlib

import yaml


ROOT = pathlib.Path(__file__).resolve().parent.parent


def _manual_backfill_steps() -> list[dict]:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/manual-backfill.yml").read_text(
            encoding="utf-8"
        )
    )
    return workflow["jobs"]["backfill"]["steps"]


def test_manual_backfill_checks_out_latest_main():
    checkout = _manual_backfill_steps()[0]
    assert checkout["uses"] == "actions/checkout@v4"
    assert checkout["with"]["ref"] == "main"


def test_manual_backfill_dry_run_never_commits():
    commit = next(
        step
        for step in _manual_backfill_steps()
        if step.get("name") == "Commit backfill results"
    )
    assert commit["if"] == "${{ !inputs.dry_run }}"
