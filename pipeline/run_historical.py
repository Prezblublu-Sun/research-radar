"""pipeline/run_historical.py - historical backfill runner.

Pulls papers in a date range from arXiv + OpenAlex + PubMed, routes them
through the existing direction_router (keyword pre-filter), and optionally
scores via the LLM. Per-calendar-month iteration with a resumable progress
file at data/historical/_progress.json.

Hard constraints (enforced by structure of this file):
  - Zotero is intentionally NOT touched. zotero_sync is not imported; no
    env vars are read for ZOTERO_*. (test_zotero_sync_module_not_imported
    in tests/test_run_historical.py asserts this.)
  - Resume mechanism: per-month status + dois_seen kept in progress file.
    Killing and re-invoking with the same --from-date / --to-date / --dry-run
    auto-resumes from the next pending month.
  - Keyword pre-filter via direction_router.filter_routed() runs BEFORE
    any LLM call, so unrouted papers never reach the scorer.

================================================================================
OUTPUT SCHEMA -- ADR-0015 v2 (Phase 4 Session 4.6)
================================================================================

Per-publication-date bucket file at data/daily/<YYYY-MM-DD>.json (v2 schema):

    schema_version       "v2"
    date                 str   "YYYY-MM-DD" -- the paper publication date
    date_precision       "day" | "month" | "year"
    papers               list  scored paper records (with v2 fields:
                                schema_version, date_precision, scorer_version,
                                first_seen_at)
    counts               dict  reconstructed from this bucket's papers

Historical and daily producers both write into the SAME data/daily/ tree;
merge on identity_key (doi:/arxiv:) is first-seen-wins (ADR-0015 §4.4), so a
re-run of the same month never duplicates a paper that's already on disk.

Discovery log records at data/discovery_log/<RUN-START-DATE>.json:

    list of {doi_or_arxiv_id, first_seen_at, run_type="historical_backfill"}

Progress file at data/historical/_progress.json (UNCHANGED by Session 4.6):

    schema_version       run-coordination metadata version (NOT per-paper
                          schema; the paper schema_version is "v2" and lives
                          on each paper record under data/daily/).
    tool                 "run_historical"
    date_range           dict  {from, to}
    dry_run              bool
    started_at, last_updated_at  str
    months               dict  per-month status + counts block
    dois_seen            list  sorted, for cross-month dedup

In dry-run mode, no bucket files and no discovery_log entries are written;
per-month counts are still tracked inside the progress file's
`months[<key>].counts` block.
================================================================================
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import pathlib
import sys
from collections import Counter

import yaml

from fetchers import arxiv_fetcher, openalex_fetcher, pubmed_fetcher
from pipeline import direction_router, llm_scorer, v2_schema as v2


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "data" / "historical"
DEFAULT_DATA_ROOT = ROOT / "data"
PROGRESS_FILENAME = "_progress.json"
CONFIG_PATH = ROOT / "config" / "directions.yaml"

# Version tag for the run-coordination metadata in _progress.json, distinct
# from the per-paper `schema_version` field (which is "v2" per ADR-0015). The
# progress file's shape didn't change in Session 4.6.
SCHEMA_VERSION = "v1"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================================
# Month iteration
# ============================================================================

def iterate_months(from_date: dt.date,
                   to_date: dt.date) -> list[tuple[str, dt.date, dt.date]]:
    """Split a date range into calendar-month windows.

    Returns [(month_key, window_from, window_to), ...] in chronological order.
    The first and last entries may be partial months.
    """
    if from_date > to_date:
        raise ValueError(f"from_date {from_date} > to_date {to_date}")

    out: list[tuple[str, dt.date, dt.date]] = []
    year, month = from_date.year, from_date.month
    cur_start = from_date
    while True:
        last_day = calendar.monthrange(year, month)[1]
        month_end = dt.date(year, month, last_day)
        window_end = min(month_end, to_date)
        out.append((f"{year:04d}-{month:02d}", cur_start, window_end))
        if window_end >= to_date:
            break
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        cur_start = dt.date(year, month, 1)
    return out


# ============================================================================
# Progress file
# ============================================================================

def _read_progress(progress_path: pathlib.Path) -> dict | None:
    if not progress_path.exists():
        return None
    try:
        return json.loads(progress_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_progress(progress_path: pathlib.Path, data: dict) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = progress_path.with_suffix(progress_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(progress_path)


def _init_progress(from_date: str, to_date: str, dry_run: bool,
                   months: list[tuple[str, dt.date, dt.date]]) -> dict:
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": "run_historical",
        "date_range": {"from": from_date, "to": to_date},
        "dry_run": dry_run,
        "started_at": now,
        "last_updated_at": now,
        "months": {
            mk: {"status": "pending",
                 "window": {"from": ws.isoformat(), "to": we.isoformat()}}
            for mk, ws, we in months
        },
        "dois_seen": [],
    }


# ============================================================================
# Config + query terms
# ============================================================================

def _load_config(config_path: pathlib.Path = CONFIG_PATH) -> tuple[dict, dict]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return cfg["directions"], cfg.get("exclusions", {})


def _collect_source_terms(directions: dict) -> dict:
    arxiv_cats, openalex_kws, openalex_concepts, pubmed_terms = (
        set(), set(), set(), set()
    )
    for dcfg in directions.values():
        sources = dcfg.get("sources", {})
        arxiv_cats.update(sources.get("arxiv_categories", []))
        openalex_kws.update(sources.get("openalex_keywords", []))
        openalex_concepts.update(sources.get("openalex_concepts", []))
        pubmed_terms.update(sources.get("pubmed_terms", []))
    return {
        "arxiv_categories":   sorted(arxiv_cats),
        "openalex_keywords":  sorted(openalex_kws),
        "openalex_concepts":  sorted(openalex_concepts),
        "pubmed_terms":       sorted(pubmed_terms),
    }


# ============================================================================
# Dedup key
# ============================================================================

def _dedup_key(paper: dict) -> str:
    doi = (paper.get("doi") or "").lower().strip()
    if doi:
        return f"doi:{doi}"
    arxiv_id = (paper.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    pid = paper.get("id") or ""
    return f"id:{pid}" if pid else ""


# ============================================================================
# Per-month run
# ============================================================================

def _run_month(month_key: str, window_from: str, window_to: str,
               directions: dict, exclusions: dict, terms: dict,
               dois_seen: set, dry_run: bool,
               data_root: pathlib.Path, run_start_date: str,
               log) -> dict:
    log(f"Month {month_key}: window {window_from} -> {window_to}")

    by_source = {"arxiv": 0, "openalex": 0, "pubmed": 0}
    fetched_lists: list[list[dict]] = []

    if terms["arxiv_categories"]:
        try:
            r = arxiv_fetcher.fetch(
                categories=terms["arxiv_categories"],
                from_date=window_from, to_date=window_to,
            )
            by_source["arxiv"] = len(r)
            fetched_lists.append(r)
            log(f"  arxiv    -> {len(r)} papers")
        except Exception as e:
            log(f"  ! arxiv fetch failed: {e}")

    if terms["openalex_keywords"] or terms["openalex_concepts"]:
        try:
            r = openalex_fetcher.fetch(
                concepts=terms["openalex_concepts"],
                keywords=terms["openalex_keywords"],
                from_date=window_from, to_date=window_to,
            )
            by_source["openalex"] = len(r)
            fetched_lists.append(r)
            log(f"  openalex -> {len(r)} papers")
        except Exception as e:
            log(f"  ! openalex fetch failed: {e}")

    if terms["pubmed_terms"]:
        try:
            r = pubmed_fetcher.fetch(
                terms=terms["pubmed_terms"],
                from_date=window_from, to_date=window_to,
            )
            by_source["pubmed"] = len(r)
            fetched_lists.append(r)
            log(f"  pubmed   -> {len(r)} papers")
        except Exception as e:
            log(f"  ! pubmed fetch failed: {e}")

    fetched_total = sum(by_source.values())

    # Dedup across sources within this month + against dois_seen across months.
    keyed: dict[str, dict] = {}
    for lst in fetched_lists:
        for p in lst:
            k = _dedup_key(p)
            if not k:
                continue
            if k in dois_seen:
                continue
            if k in keyed:
                continue
            keyed[k] = p
    papers = list(keyed.values())
    after_dedup = len(papers)

    # Route (keyword pre-filter; unrouted papers will never reach the LLM).
    for p in papers:
        direction_router.route(p, directions, exclusions)
    routed = direction_router.filter_routed(papers)
    after_routing = len(routed)
    by_direction = Counter(p.get("direction") for p in routed)
    routed_by_source = Counter(p.get("source") for p in routed)

    # ADR-0020: pre-dedup against the corpus BEFORE scoring. Drop any routed
    # paper whose v2.identity_key already exists in the target bucket on disk,
    # so score_batch only sees genuinely-new papers. Keys MUST be identity_key
    # (not _dedup_key) to match the first-seen-wins comparison at write time.
    # Papers with empty identity_key cannot be deduped and fall through.
    # Dry-run skips this: it writes nothing, so there is no corpus to compare
    # against in tests/light runs, and after_routing is reported unchanged.
    skipped_existing = 0
    if not dry_run and routed:
        daily_dir = data_root / "daily"
        bucket_existing_keys: dict[str, set[str]] = {}
        novel: list[dict] = []
        for p in routed:
            k = v2.identity_key(p)
            if not k:
                novel.append(p)
                continue
            bucket_date = (p.get("date") or "").strip()
            if bucket_date not in bucket_existing_keys:
                existing_papers, _meta = v2.load_existing_v2(
                    daily_dir / f"{bucket_date}.json"
                )
                bucket_existing_keys[bucket_date] = {
                    ek for ek in (v2.identity_key(x) for x in existing_papers)
                    if ek
                }
            if k in bucket_existing_keys[bucket_date]:
                skipped_existing += 1
            else:
                novel.append(p)
        routed = novel

    # Score (skipped in dry-run).
    scored_count = 0
    priority_counts = None
    scored_papers: list[dict] = []
    if not dry_run and routed:
        scored, _raw = llm_scorer.score_batch(routed, directions)
        scored_count = len(scored)
        priority_counts = {"High": 0, "Medium": 0, "Low": 0, "Exclude": 0}
        for p in scored:
            prio = (p.get("llm") or {}).get("priority", "Low")
            priority_counts[prio] = priority_counts.get(prio, 0) + 1
        scored_papers = scored

    # Update dois_seen so adjacent months don't re-process the same paper.
    for k in keyed:
        dois_seen.add(k)

    # ADR-0015 v2: bucket scored papers by paper["date"] into
    # data/daily/<bucket_date>.json, first-seen-wins merge against any prior
    # content on disk. Dry-run skips scoring entirely, so scored_papers == []
    # and no bucket/discovery_log files are written; per-month counts are
    # still surfaced via the returned dict.
    touched_buckets: dict[str, int] = {}
    missing_date = 0
    if not dry_run and scored_papers:
        run_ts = v2.utc_now_iso()
        scorer_version = v2.scorer_version_from_active_prompt()
        daily_dir = data_root / "daily"

        buckets: dict[str, list[dict]] = {}
        for p in scored_papers:
            d = (p.get("date") or "").strip()
            if not d:
                missing_date += 1
                continue
            buckets.setdefault(d, []).append(p)

        for bucket_date, new_papers in buckets.items():
            target = daily_dir / f"{bucket_date}.json"
            existing_papers, _meta = v2.load_existing_v2(target)
            existing_keys = {
                k for k in (v2.identity_key(p) for p in existing_papers) if k
            }
            added = 0
            for p in new_papers:
                k = v2.identity_key(p)
                if k and k in existing_keys:
                    continue  # first-seen wins
                p_out = dict(p)
                p_out["schema_version"] = "v2"
                p_out["date_precision"] = v2.infer_date_precision(
                    p_out.get("date", "")
                )
                p_out["scorer_version"] = scorer_version
                p_out["first_seen_at"] = run_ts
                existing_papers.append(p_out)
                if k:
                    existing_keys.add(k)
                added += 1
            if added > 0:
                v2.atomic_write_json(
                    target, v2.build_v2_file(bucket_date, existing_papers)
                )
                touched_buckets[bucket_date] = added

        # Discovery log: one record per scored observation, regardless of
        # whether the paper survived the bucket-level dedup. run_date is the
        # calendar date of when this historical session started so that all
        # months in one run share a discovery file.
        discovery_records = [
            {
                "doi_or_arxiv_id": v2.identity_key(p),
                "first_seen_at": run_ts,
                "run_type": "historical_backfill",
            }
            for p in scored_papers
            if v2.identity_key(p)
        ]
        if discovery_records:
            log_path = (data_root / "discovery_log"
                        / f"{run_start_date}.json")
            existing_log: list = []
            if log_path.exists():
                try:
                    loaded = json.loads(log_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        existing_log = loaded
                except (json.JSONDecodeError, OSError):
                    existing_log = []
            v2.atomic_write_json(log_path, existing_log + discovery_records)

    counts = {
        "fetched_total": fetched_total,
        "by_source": by_source,
        "after_dedup": after_dedup,
        "after_routing": after_routing,
        "by_direction": dict(by_direction),
        "routed_by_source": dict(routed_by_source),
        "skipped_existing": skipped_existing,
        "scored": scored_count,
        "priority_counts": priority_counts,
        # v2 diagnostics
        "touched_buckets": touched_buckets,
        "papers_with_missing_date": missing_date,
    }
    if dry_run:
        log(f"  -> dry-run: routed {after_routing}, scored 0; "
            f"no bucket files written")
    else:
        total_added = sum(touched_buckets.values())
        log(f"  -> routed {after_routing}, {skipped_existing} already in "
            f"corpus, scored {scored_count}; wrote {total_added} new "
            f"paper(s) across {len(touched_buckets)} bucket(s)")
        if missing_date:
            log(f"     (skipped {missing_date} paper(s) with empty date)")

    return counts


# ============================================================================
# Top-level orchestrator
# ============================================================================

def run(from_date: str, to_date: str, dry_run: bool,
        output_dir: pathlib.Path, no_resume: bool,
        data_root: pathlib.Path | None = None,
        config_path: pathlib.Path = CONFIG_PATH,
        log_fn=None) -> dict:
    log = log_fn or (lambda m: print(m, flush=True))

    # Default: data_root is the parent of output_dir, which under production
    # config means data/historical/.parent == data/. Tests that put both
    # progress and bucket output under tmp_path should pass data_root=tmp_path
    # explicitly.
    if data_root is None:
        data_root = output_dir.parent

    fd = dt.date.fromisoformat(from_date)
    td = dt.date.fromisoformat(to_date)
    months = iterate_months(fd, td)

    progress_path = output_dir / PROGRESS_FILENAME
    existing = None if no_resume else _read_progress(progress_path)

    if existing:
        if existing.get("date_range") != {"from": from_date, "to": to_date}:
            raise SystemExit(
                f"_progress.json date_range mismatch: file has "
                f"{existing.get('date_range')}, CLI has "
                f"{{'from': '{from_date}', 'to': '{to_date}'}}. "
                f"Delete the progress file or correct the CLI dates."
            )
        if existing.get("dry_run") != dry_run:
            raise SystemExit(
                f"_progress.json dry_run mismatch: file has dry_run="
                f"{existing.get('dry_run')}, CLI has dry_run={dry_run}. "
                f"A dry-run and a real run are separate logical sessions; "
                f"delete the progress file to start a new session."
            )
        progress = existing
        log(f"Resuming from {progress_path}")
    else:
        progress = _init_progress(from_date, to_date, dry_run, months)
        log(f"Fresh historical run: {len(months)} month(s) to process")

    directions, exclusions = _load_config(config_path)
    terms = _collect_source_terms(directions)
    dois_seen: set[str] = set(progress.get("dois_seen", []))
    # Run-start calendar date drives the discovery_log filename. Use the
    # progress file's started_at so a resumed session keeps appending to the
    # original day's log.
    run_start_date = progress["started_at"][:10]

    _write_progress(progress_path, progress)

    completed = 0
    for mk, ws, we in months:
        m_info = progress["months"].get(
            mk,
            {"status": "pending",
             "window": {"from": ws.isoformat(), "to": we.isoformat()}},
        )
        if m_info.get("status") == "complete":
            log(f"Month {mk}: skip (already complete)")
            completed += 1
            continue

        progress["months"][mk] = {
            **m_info,
            "status": "in_progress",
            "window": {"from": ws.isoformat(), "to": we.isoformat()},
            "started_at": _now_iso(),
        }
        progress["last_updated_at"] = _now_iso()
        _write_progress(progress_path, progress)

        try:
            counts = _run_month(
                month_key=mk,
                window_from=ws.isoformat(),
                window_to=we.isoformat(),
                directions=directions,
                exclusions=exclusions,
                terms=terms,
                dois_seen=dois_seen,
                dry_run=dry_run,
                data_root=data_root,
                run_start_date=run_start_date,
                log=log,
            )
        except Exception as e:
            progress["months"][mk] = {
                **progress["months"][mk],
                "status": "failed",
                "error": str(e),
            }
            progress["last_updated_at"] = _now_iso()
            _write_progress(progress_path, progress)
            raise

        progress["months"][mk] = {
            **progress["months"][mk],
            "status": "complete",
            "completed_at": _now_iso(),
            "counts": counts,
        }
        progress["dois_seen"] = sorted(dois_seen)
        progress["last_updated_at"] = _now_iso()
        _write_progress(progress_path, progress)
        completed += 1

    return {
        "months_total": len(months),
        "months_completed": completed,
        "progress_file": str(progress_path),
        "dry_run": dry_run,
    }


# ============================================================================
# CLI
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Historical backfill runner for research-radar. Pulls a date "
            "range from arXiv + OpenAlex + PubMed, routes via direction_router, "
            "optionally scores via DeepSeek. Zotero is never touched."
        )
    )
    parser.add_argument("--from-date", required=True,
                        help="Start of range, YYYY-MM-DD (inclusive).")
    parser.add_argument("--to-date", required=True,
                        help="End of range, YYYY-MM-DD (inclusive).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip LLM scoring; emit fetch/route counts only.")
    parser.add_argument("--output-dir", type=pathlib.Path,
                        default=DEFAULT_OUTPUT_DIR,
                        help="Progress-file directory "
                             "(default: data/historical/).")
    parser.add_argument("--data-root", type=pathlib.Path,
                        default=DEFAULT_DATA_ROOT,
                        help="Root for v2 outputs; bucket files go to "
                             "<data-root>/daily/ and discovery_log entries "
                             "to <data-root>/discovery_log/ "
                             "(default: data/).")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore any existing _progress.json and start "
                             "fresh.")
    args = parser.parse_args(argv)

    report = run(
        from_date=args.from_date, to_date=args.to_date,
        dry_run=args.dry_run, output_dir=args.output_dir.resolve(),
        data_root=args.data_root.resolve(),
        no_resume=args.no_resume,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
