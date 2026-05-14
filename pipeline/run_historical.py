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
JSON OUTPUT SCHEMA -- v1
================================================================================

Per-month file at data/historical/<YYYY-MM>[_dryrun].json:

    schema_version       str
    month                str   "YYYY-MM"
    window               dict  {from, to}  -- the actual window for this month
    dry_run              bool
    completed_at         str   ISO 8601 Zulu
    counts               dict  per-month tallies (see below)
    papers               list  scored paper records (omitted in dry-run)

Counts dict:
    fetched_total        int   sum across sources, before any dedup
    by_source            dict  {arxiv, openalex, pubmed} -- fetched counts
    after_dedup          int   distinct papers after cross-source +
                                cross-month DOI dedup
    after_routing        int   papers with at least one direction
    by_direction         dict  per-direction routed count
    routed_by_source     dict  {arxiv, openalex, pubmed} -- routed counts;
                                values sum to after_routing
    scored               int   0 in dry-run, else == after_routing
    priority_counts      dict | null   High/Medium/Low/Exclude breakdown

Progress file at data/historical/_progress.json:

    schema_version       str
    tool                 "run_historical"
    date_range           dict  {from, to}
    dry_run              bool
    started_at, last_updated_at  str
    months               dict  per-month status block
    dois_seen            list  sorted, for cross-month dedup
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
from pipeline import direction_router, llm_scorer


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "data" / "historical"
PROGRESS_FILENAME = "_progress.json"
CONFIG_PATH = ROOT / "config" / "directions.yaml"

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
               output_dir: pathlib.Path, log) -> dict:
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

    counts = {
        "fetched_total": fetched_total,
        "by_source": by_source,
        "after_dedup": after_dedup,
        "after_routing": after_routing,
        "by_direction": dict(by_direction),
        "routed_by_source": dict(routed_by_source),
        "scored": scored_count,
        "priority_counts": priority_counts,
    }

    # Per-month output file
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_dryrun" if dry_run else ""
    out_path = output_dir / f"{month_key}{suffix}.json"
    out_data = {
        "schema_version": SCHEMA_VERSION,
        "month": month_key,
        "window": {"from": window_from, "to": window_to},
        "dry_run": dry_run,
        "completed_at": _now_iso(),
        "counts": counts,
    }
    if not dry_run:
        out_data["papers"] = scored_papers
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    log(f"  -> wrote {out_path.name} "
        f"(routed {after_routing}, scored {scored_count})")

    return counts


# ============================================================================
# Top-level orchestrator
# ============================================================================

def run(from_date: str, to_date: str, dry_run: bool,
        output_dir: pathlib.Path, no_resume: bool,
        config_path: pathlib.Path = CONFIG_PATH,
        log_fn=None) -> dict:
    log = log_fn or (lambda m: print(m, flush=True))

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
                output_dir=output_dir,
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
                        help="Output directory (default: data/historical/).")
    parser.add_argument("--no-resume", action="store_true",
                        help="Ignore any existing _progress.json and start "
                             "fresh.")
    args = parser.parse_args(argv)

    report = run(
        from_date=args.from_date, to_date=args.to_date,
        dry_run=args.dry_run, output_dir=args.output_dir.resolve(),
        no_resume=args.no_resume,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
