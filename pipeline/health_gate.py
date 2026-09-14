"""Exit non-zero only when a persisted run needs operator attention.

ADR-0030: a single-source outage (e.g. arXiv HTTP 429 on 2026-09-13) used to
fail the workflow *after* the day's data had been committed. The failed
conclusion then skipped the Pages deploy and left the public site stale,
even though 782 OpenAlex papers had been fetched, scored and saved.

The gate now blocks only on outcomes that mean the day's data is missing or
largely unscored. Everything else (a partial_success run, one failed
source, a truncated OpenAlex window, low counts) is emitted as a GitHub
Actions warning so it stays visible without hiding the good data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent

HEALTHY_STATUSES = ("success", "partial_success")
# Flags that are always non-blocking but worth a warning line.
WARNING_FLAGS = ("low_fetch_count", "zero_routed", "zero_high_medium")
WARNING_SUFFIXES = ("_failed", "_truncated", "_returned_zero")


def _scorer_failure_is_blocking(manifest: dict) -> bool:
    """True when at least half of the routed papers failed to score.

    One malformed DeepSeek response out of 70 is a rescore_silent job, not a
    reason to hide the other 69 papers; a scorer that failed on most of the
    batch means the day is effectively unscored.
    """
    counts = manifest.get("counts") or {}
    failed = int(counts.get("scorer_failed") or 0)
    if failed <= 0:
        return False
    scored_ok = sum(int(v or 0) for v in (counts.get("priority_counts") or {}).values())
    return failed >= max(scored_ok, 1)


def evaluate(manifest: dict) -> list[str]:
    """Return blocking reasons; an empty list means the gate passes."""
    reasons: list[str] = []
    status = manifest.get("run_status")
    if status not in HEALTHY_STATUSES:
        reasons.append(f"run_status={status or 'missing'}")
    flags = manifest.get("quality_flags") or []
    if "fetched_zero" in flags:
        reasons.append("fetched_zero")
    if "scorer_failed" in flags and _scorer_failure_is_blocking(manifest):
        reasons.append("scorer_failed")
    return list(dict.fromkeys(reasons))


def warnings(manifest: dict) -> list[str]:
    """Return non-blocking observations for the workflow log."""
    out: list[str] = []
    if manifest.get("run_status") == "partial_success":
        out.append("run_status=partial_success")
    blocking = set(evaluate(manifest))
    for flag in manifest.get("quality_flags") or []:
        if flag in blocking or flag == "fetched_zero":
            continue
        if flag in WARNING_FLAGS or flag.endswith(WARNING_SUFFIXES):
            out.append(flag)
    return list(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument(
        "--manifests-dir", type=pathlib.Path,
        default=ROOT / "data" / "manifests",
    )
    args = parser.parse_args(argv)
    path = args.manifests_dir / f"{args.date}.json"
    if not path.exists():
        print(f"::error::run manifest is missing: {path}")
        return 1
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for note in warnings(manifest):
        print(f"::warning::daily run persisted with a non-blocking problem: {note}")
    reasons = evaluate(manifest)
    if reasons:
        print("::error::daily run persisted with health problems: "
              + ", ".join(reasons))
        return 1
    print("daily run health gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
