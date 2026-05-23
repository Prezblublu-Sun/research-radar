"""scripts/rescore_silent.py — ADR-0017 §Decision 2 in-place rescore.

One-shot tool that walks ``data/daily/20*.json``, finds papers whose
original LLM scoring produced a silent Low (priority set, reasoning
fields empty, ``priority_reason`` populated with an exception trace),
and re-invokes ``pipeline.llm_scorer.score_batch`` — which after
ADR-0017 §Decision 1 is retry-aware. Daily files are rewritten
atomically via ``.tmp`` + ``os.fsync`` + ``os.replace`` so a kill
mid-flush never leaves a partially-updated bucket on disk.

CLI::

    .venv/bin/python -m scripts.rescore_silent
        [--dry-run] [--limit N] [--resume]

  --dry-run  Report silent-paper counts per month + total. No writes.
  --limit N  Stop after N silent papers re-scored. Useful for testing.
  --resume   Skip papers that already carry ``scorer_failed=True`` from a
             previous rescore attempt — i.e. don't re-spend the 3 retries
             on papers that already exhausted them. (Successfully-rescored
             papers are skipped naturally because they're no longer silent.)

This script is read-mostly: the only files it writes are
``data/daily/*.json``. It does not call build_pages, run_daily,
run_historical, export_candidates, or weekly_report, and it does not
trigger any fetcher.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

import yaml

# `pipeline.llm_scorer` constructs the OpenAI client at import time and
# therefore requires OPENAI_API_KEY in the environment. ``--dry-run``
# only counts silent papers — it never calls the scorer — so the import
# is deferred into :func:`rescore_run` to keep dry-run usable without
# credentials. Tests still patch ``rs.llm_scorer.score_batch`` after
# this lazy import has bound the attribute.
llm_scorer = None  # populated by _ensure_llm_scorer()


def _ensure_llm_scorer():
    global llm_scorer
    if llm_scorer is None:
        from pipeline import llm_scorer as _ls
        llm_scorer = _ls
    return llm_scorer


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CORPUS_ROOT = ROOT / "data" / "daily"
DEFAULT_DIRECTIONS_YAML = ROOT / "config" / "directions.yaml"


# ============================== predicates =================================

def is_silent(llm: dict) -> bool:
    """The ADR-0017 silent-Low signature: priority is set, reasoning is empty,
    and ``priority_reason`` carries the legacy exception-trace string."""
    priority = llm.get("priority")
    if not priority:
        return False
    relevance = (llm.get("relevance_to_user") or "").strip()
    motivation = ((llm.get("summary_zh") or {}).get("motivation") or "").strip()
    tags = llm.get("tags") or []
    priority_reason = (llm.get("priority_reason") or "").strip()
    return not relevance and not motivation and not tags and bool(priority_reason)


def is_scorer_failed(llm: dict) -> bool:
    """Set by the post-ADR-0017 retry loop after 3 attempts fail."""
    return llm.get("scorer_failed") is True


def is_candidate(p: dict, resume: bool) -> bool:
    """A paper this run should attempt to re-score.

    Always: the original silent-Low pattern.
    Additionally, when --resume is NOT set: papers that previously
    exhausted their 3 retries (``scorer_failed=True``) get one more
    attempt. With --resume, those are skipped — the use case is
    "interrupted run, picking up where we left off; don't burn the
    retry budget on papers we've already tried".
    """
    llm = p.get("llm", {}) or {}
    if is_silent(llm):
        return True
    if (not resume) and is_scorer_failed(llm):
        return True
    return False


# ============================== I/O ========================================

def _load_bucket(path: pathlib.Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def atomic_write_json(path: pathlib.Path, data: dict) -> None:
    """Write ``data`` to ``path`` atomically: ``.tmp`` → fsync → os.replace.

    If the rename fails (disk full, permission flip, etc.), the original
    ``path`` is never touched; the orphaned ``.tmp`` is best-effort
    cleaned up before re-raising.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


# ============================== scans ======================================

def dry_run_scan(daily_dir: pathlib.Path) -> dict:
    """Count silent + scorer_failed papers per YYYY-MM bucket without
    touching anything. Returns ``{per_month, total_silent, total_failed}``.
    """
    per_month: dict[str, int] = {}
    total_silent = 0
    total_failed = 0
    for bp in sorted(daily_dir.glob("20*.json")):
        data = _load_bucket(bp)
        if not data:
            continue
        month = bp.stem[:7]
        for p in data.get("papers", []):
            llm = p.get("llm", {}) or {}
            if is_silent(llm):
                per_month[month] = per_month.get(month, 0) + 1
                total_silent += 1
            if is_scorer_failed(llm):
                total_failed += 1
    return {"per_month": per_month, "total_silent": total_silent,
            "total_failed": total_failed}


# ============================== rescore loop ===============================

def _ts() -> str:
    return time.strftime("%H:%M:%S")


def rescore_run(daily_dir: pathlib.Path, directions_cfg: dict,
                limit: int | None = None, resume: bool = False) -> dict:
    """The actual mutating pass. For each bucket, collect its candidate
    papers and hand them to the retry-aware scorer in a single
    :func:`score_batch` call so its ``LLM_CONCURRENCY`` worker pool
    actually engages (ADR-0019). Buckets are written atomically once
    after their candidates have all been scored. Returns final stats.
    """
    # Bind the lazy-imported scorer module. Tests that monkeypatch
    # ``rs.llm_scorer.score_batch`` install an autouse fixture that runs
    # this beforehand, so ``llm_scorer`` is the real module at patch time
    # and we pick the patched ``score_batch`` up here via the same object.
    scorer = _ensure_llm_scorer()

    # Pre-count so the progress line has a meaningful denominator.
    pre = dry_run_scan(daily_dir)
    total_candidates = pre["total_silent"] + (0 if resume else pre["total_failed"])
    if limit is not None:
        total_candidates = min(total_candidates, limit)

    started = time.time()
    processed = 0
    succeeded = 0
    failed = 0
    last_bucket = ""
    print(f"[{_ts()}] rescore: starting — {total_candidates} candidate papers "
          f"(resume={resume}, limit={limit})", flush=True)

    for bp in sorted(daily_dir.glob("20*.json")):
        if limit is not None and processed >= limit:
            break
        data = _load_bucket(bp)
        if not data:
            continue
        papers = data.get("papers", [])

        # Collect this bucket's candidates by reference so score_batch's
        # in-place mutation of paper["llm"] is what eventually lands on
        # disk when we rewrite ``data``.
        candidates = [p for p in papers if is_candidate(p, resume)]

        # Honour --limit exactly: cap candidates to the remaining budget
        # before dispatching, so total processed across all buckets never
        # exceeds limit.
        if limit is not None:
            remaining = limit - processed
            candidates = candidates[:remaining]

        if not candidates:
            continue

        # One concurrent batch per bucket. score_batch fans out across
        # LLM_CONCURRENCY workers, preserves input order, and applies
        # the ADR-0017 3-attempt retry per paper.
        scorer.score_batch(candidates, directions_cfg)

        for cp in candidates:
            new_llm = cp.get("llm", {}) or {}
            if new_llm.get("scorer_failed"):
                failed += 1
            elif new_llm.get("priority"):
                succeeded += 1
        processed += len(candidates)
        last_bucket = bp.stem

        atomic_write_json(bp, data)

        pct = 100.0 * processed / max(total_candidates, 1)
        print(f"[{_ts()}] rescore: {processed} / {total_candidates} "
              f"({pct:.1f}%) — last bucket {last_bucket}", flush=True)

    elapsed = time.time() - started
    print(f"[{_ts()}] DONE — processed={processed} succeeded={succeeded} "
          f"scorer_failed={failed} elapsed={elapsed:.1f}s", flush=True)
    return {
        "processed": processed,
        "succeeded": succeeded,
        "scorer_failed": failed,
        "elapsed": elapsed,
        "last_bucket": last_bucket,
        "total_candidates": total_candidates,
    }


# ============================== entry ======================================

def _load_directions(yaml_path: pathlib.Path) -> dict:
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    return cfg.get("directions", {}) or {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="rescore_silent",
        description="Re-score ADR-0017 silent-Low papers in place.",
    )
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Report counts only; do not call the scorer.")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N silent papers rescored.")
    p.add_argument("--resume", action="store_true",
                   help="Skip papers already retried (scorer_failed=True).")
    p.add_argument("--corpus-root", dest="corpus_root", type=pathlib.Path,
                   default=None,
                   help="Override data/daily/ root (mainly for tests).")
    p.add_argument("--directions-yaml", dest="directions_yaml",
                   type=pathlib.Path, default=None,
                   help="Override config/directions.yaml path (for tests).")
    args = p.parse_args(argv)

    daily_dir = args.corpus_root or DEFAULT_CORPUS_ROOT
    yaml_path = args.directions_yaml or DEFAULT_DIRECTIONS_YAML

    if args.dry_run:
        stats = dry_run_scan(daily_dir)
        print(f"silent paper count per month (resume={args.resume}):")
        for month in sorted(stats["per_month"]):
            print(f"  {month}: {stats['per_month'][month]}")
        print("---")
        print(f"total silent: {stats['total_silent']}")
        print(f"total scorer_failed (already retried): "
              f"{stats['total_failed']}")
        return 0

    directions_cfg = _load_directions(yaml_path)
    rescore_run(daily_dir, directions_cfg,
                limit=args.limit, resume=args.resume)
    return 0


if __name__ == "__main__":
    sys.exit(main())
