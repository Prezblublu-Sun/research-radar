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
    assert "!inputs.dry_run" in commit["if"]
    # ...but a failed month must not discard the completed ones (ADR-0030 §10).
    assert "!cancelled()" in commit["if"]


def test_manual_backfill_progress_dir_is_stable_per_range():
    run = next(
        step
        for step in _manual_backfill_steps()
        if step.get("name") == "Run historical backfill"
    )["run"]
    assert "${{ inputs.from_date }}_${{ inputs.to_date }}" in run
    assert "github.run_id" not in run


# ---------------------------------------------------------------------------
# ADR-0030: publish resilience
# ---------------------------------------------------------------------------

def _workflow(name: str) -> dict:
    return yaml.safe_load(
        (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
    )


def _step(workflow: dict, job: str, name: str) -> dict:
    return next(
        step for step in workflow["jobs"][job]["steps"]
        if step.get("name") == name
    )


def test_daily_cron_avoids_the_top_of_the_hour():
    # September 2026: a "0 3" schedule actually started 07:19-08:14 UTC.
    daily = _workflow("daily.yml")
    cron = daily[True]["schedule"][0]["cron"]  # PyYAML parses `on:` as True
    minute = cron.split()[0]
    assert minute.isdigit() and int(minute) != 0


def test_writers_push_through_the_retry_script():
    # 2026-09-12: one failed push lost the whole day. Every writer must use
    # scripts/git_push_retry.sh instead of a bare `git push`.
    for workflow_name, job, step_name in _WRITER_COMMIT_STEPS:
        run = _step(_workflow(workflow_name), job, step_name)["run"]
        assert "scripts/git_push_retry.sh" in run, workflow_name
        assert "\ngit push\n" not in run and not run.rstrip().endswith("git push"), workflow_name


_WRITER_COMMIT_STEPS = (
    ("daily.yml", "run", "Commit results"),
    ("manual-backfill.yml", "backfill", "Commit backfill results"),
    ("manual-rescore.yml", "rescore", "Commit rescore results"),
)


def test_writers_never_commit_generated_docs():
    # ADR-0028 follow-up: the site is a disposable artifact built from data/.
    for workflow_name, job, step_name in _WRITER_COMMIT_STEPS:
        run = _step(_workflow(workflow_name), job, step_name)["run"]
        assert "docs/" not in run, workflow_name
    assert not (ROOT / ".github/workflows/weekly.yml").exists()
    pages = _workflow("pages.yml")
    assert "weekly-research-radar" not in pages[True]["workflow_run"]["workflows"]


def test_pytest_runs_in_ci_for_pull_requests():
    tests = _workflow("tests.yml")
    assert "pull_request" in tests[True]
    runs = " ".join(step.get("run", "") for step in tests["jobs"]["pytest"]["steps"])
    assert "pytest" in runs


def test_retry_script_is_committed_and_bounded():
    script = (ROOT / "scripts/git_push_retry.sh").read_text(encoding="utf-8")
    assert "git push origin" in script
    assert "git pull --rebase" in script
    assert "exit 1" in script  # gives up loudly instead of looping forever


def test_daily_health_gate_runs_after_commit():
    steps = _workflow("daily.yml")["jobs"]["run"]["steps"]
    names = [s.get("name") for s in steps]
    assert names.index("Commit results") < names.index("Daily run health gate")
