"""Migrate v1 paper JSON files to v2 schema per ADR-0015.

Reads from --source-dir (default data/_archive_v1/) and writes to --output-dir
(default data/). Source layout:

    <source-dir>/daily/YYYY-MM-DD.json       v1 flat list of paper dicts
    <source-dir>/historical/YYYY-MM.json     v1 dict with `papers` + `completed_at`

Output layout (ADR-0015 §4.5, §4.3):

    <output-dir>/daily/YYYY-MM-DD.json           v2 dict keyed by publication date
    <output-dir>/discovery_log/YYYY-MM-DD.json   per source-file run-date records

Per-paper additions (ADR-0015 §5.2):

    schema_version  = "v2"
    date_precision  inferred from old `date` string:
                      "*-01-01"  -> "year"
                      "*-01"     -> "month"  (and not "*-01-01")
                      else       -> "day"
    scorer_version  "v1" for historical-source papers (Phase C state),
                    "v3" for daily-source papers (workflow pinned v3).
    first_seen_at   source-file run timestamp; historical uses `completed_at`,
                    daily infers midnight UTC from the filename date.

Dedup (ADR-0015 §4.4): identity key = doi-or-arxiv_id; first-seen wins.
Source files are processed in chronological order of run timestamp; every
observation appends to the discovery log even when deduplicated.

CLI:
    python scripts/migrate_to_schema_v2.py
    python scripts/migrate_to_schema_v2.py --source-dir /tmp/v1 --output-dir /tmp/v2
    python scripts/migrate_to_schema_v2.py --dry-run
    python scripts/migrate_to_schema_v2.py --no-discovery-log
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field


# ============================================================================
# Schema helpers
# ============================================================================

_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RX = re.compile(r"^\d{4}-\d{2}$")


def infer_date_precision(date_str: str) -> str:
    """Return 'day' | 'month' | 'year' per ADR-0015 §5.2 + §4.1 (year case)."""
    if not date_str:
        return "year"
    if date_str.endswith("-01-01"):
        return "year"
    if date_str.endswith("-01"):
        return "month"
    return "day"


def identity_key(paper: dict) -> str:
    """Return prefixed dedup key per CLAUDE.md §4 / ADR-0015 §4.4.

    Returns empty string if the paper has neither DOI nor arxiv_id.
    """
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"doi:{doi}"
    arxiv = (paper.get("arxiv_id") or "").strip()
    if arxiv:
        return f"arxiv:{arxiv}"
    return ""


# ============================================================================
# Source discovery
# ============================================================================

@dataclass
class SourceFile:
    path: pathlib.Path
    kind: str            # "daily" or "historical"
    run_timestamp: str   # ISO 8601 UTC
    run_date: str        # YYYY-MM-DD


def _is_skip_filename(name: str) -> bool:
    """Skip v1 sidecars: _progress, _dryrun, _summary, hidden files."""
    if name.startswith("_") or name.startswith("."):
        return True
    stem = pathlib.Path(name).stem
    return stem.endswith("_dryrun") or stem.endswith("_summary")


def _run_timestamp_for_daily(stem: str) -> str:
    """Daily filename is YYYY-MM-DD; map to midnight UTC of that day."""
    if _DATE_RX.match(stem):
        return f"{stem}T00:00:00Z"
    return ""


def _run_timestamp_for_historical(data: dict, stem: str) -> str:
    completed_at = (data.get("completed_at") or "").strip()
    if completed_at:
        return completed_at
    if _MONTH_RX.match(stem):
        return f"{stem}-01T00:00:00Z"
    if _DATE_RX.match(stem):
        return f"{stem}T00:00:00Z"
    return ""


def collect_source_files(source_dir: pathlib.Path) -> list[SourceFile]:
    """Walk daily/ and historical/ subdirs; return SourceFile records.

    Files are returned sorted by run_timestamp ascending so that first-seen
    dedup processes the chronologically earliest observation first.
    """
    found: list[SourceFile] = []

    daily_dir = source_dir / "daily"
    if daily_dir.is_dir():
        for p in sorted(daily_dir.glob("*.json")):
            if _is_skip_filename(p.name):
                continue
            ts = _run_timestamp_for_daily(p.stem)
            if not ts:
                continue
            found.append(SourceFile(path=p, kind="daily",
                                    run_timestamp=ts, run_date=ts[:10]))

    hist_dir = source_dir / "historical"
    if hist_dir.is_dir():
        for p in sorted(hist_dir.glob("*.json")):
            if _is_skip_filename(p.name):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict):
                continue
            ts = _run_timestamp_for_historical(data, p.stem)
            if not ts:
                continue
            found.append(SourceFile(path=p, kind="historical",
                                    run_timestamp=ts, run_date=ts[:10]))

    found.sort(key=lambda s: s.run_timestamp)
    return found


def load_papers(src: SourceFile) -> list[dict]:
    """Return raw paper dicts from a v1 source file."""
    try:
        data = json.loads(src.path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if src.kind == "daily":
        return data if isinstance(data, list) else []
    if isinstance(data, dict):
        papers = data.get("papers", [])
        return papers if isinstance(papers, list) else []
    return []


# ============================================================================
# Migration core
# ============================================================================

@dataclass
class MigrationResult:
    files_written: dict[str, list[dict]] = field(default_factory=dict)
    discovery_log: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    source_files_seen: int = 0
    papers_observed: int = 0
    papers_kept: int = 0
    papers_deduped: int = 0
    papers_missing_date: int = 0
    papers_missing_id: int = 0


def _scorer_version_for(kind: str) -> str:
    return "v3" if kind == "daily" else "v1"


def _run_type_for(kind: str) -> str:
    return "daily" if kind == "daily" else "historical_backfill"


def migrate_paper(paper: dict, *, scorer_version: str,
                  first_seen_at: str) -> dict | None:
    """Return a v2-shaped paper dict, or None if it has no date.

    Adds schema_version, date_precision, scorer_version, first_seen_at.
    Leaves all other fields untouched.
    """
    date = (paper.get("date") or "").strip()
    if not date:
        return None
    out = dict(paper)
    out["schema_version"] = "v2"
    out["date_precision"] = infer_date_precision(date)
    out["scorer_version"] = scorer_version
    out["first_seen_at"] = first_seen_at
    return out


def build_counts(papers: list[dict]) -> dict:
    """Reconstruct historical-style counts from a file's papers.

    Faithful to the file's content: every paper is post-dedup and post-routing
    by construction during migration.
    """
    by_source: Counter = Counter()
    by_direction: Counter = Counter()
    priority_counts: Counter = Counter()
    scored = 0
    for p in papers:
        by_source[p.get("source", "")] += 1
        d = p.get("direction") or p.get("direction_name")
        if d:
            by_direction[d] += 1
        elif p.get("directions"):
            for dn in p["directions"]:
                by_direction[dn] += 1
        llm = p.get("llm")
        if isinstance(llm, dict):
            scored += 1
            pr = llm.get("priority")
            if pr:
                priority_counts[pr] += 1
    return {
        "fetched_total": len(papers),
        "by_source": dict(by_source),
        "after_dedup": len(papers),
        "after_routing": len(papers),
        "by_direction": dict(by_direction),
        "routed_by_source": dict(by_source),
        "scored": scored,
        "priority_counts": dict(priority_counts) if priority_counts else None,
    }


def build_v2_file(date_str: str, papers: list[dict]) -> dict:
    """Wrap a publication-date bucket of papers as a v2 file dict."""
    return {
        "schema_version": "v2",
        "date": date_str,
        "date_precision": infer_date_precision(date_str),
        "papers": papers,
        "counts": build_counts(papers),
    }


def run_migration(source_dir: pathlib.Path) -> MigrationResult:
    """Pure in-memory migration. Returns a MigrationResult; writes nothing."""
    res = MigrationResult()
    seen_keys: set[str] = set()

    for src in collect_source_files(source_dir):
        res.source_files_seen += 1
        scorer_version = _scorer_version_for(src.kind)
        run_type = _run_type_for(src.kind)

        for paper in load_papers(src):
            res.papers_observed += 1
            key = identity_key(paper)
            if not key:
                res.papers_missing_id += 1

            # Every observation produces a discovery_log record, even if
            # the paper is deduped downstream (ADR-0015 §4.3).
            if key:
                res.discovery_log[src.run_date].append({
                    "doi_or_arxiv_id": key,
                    "first_seen_at": src.run_timestamp,
                    "run_type": run_type,
                })

            if key and key in seen_keys:
                res.papers_deduped += 1
                continue

            migrated = migrate_paper(
                paper,
                scorer_version=scorer_version,
                first_seen_at=src.run_timestamp,
            )
            if migrated is None:
                res.papers_missing_date += 1
                continue

            if key:
                seen_keys.add(key)
            res.papers_kept += 1
            res.files_written.setdefault(migrated["date"], []).append(migrated)

    return res


# ============================================================================
# Output writers
# ============================================================================

def write_v2_files(result: MigrationResult, output_dir: pathlib.Path) -> list[pathlib.Path]:
    written: list[pathlib.Path] = []
    daily_out = output_dir / "daily"
    daily_out.mkdir(parents=True, exist_ok=True)
    for date_str, papers in sorted(result.files_written.items()):
        path = daily_out / f"{date_str}.json"
        path.write_text(json.dumps(build_v2_file(date_str, papers),
                                   indent=2, ensure_ascii=False))
        written.append(path)
    return written


def write_discovery_log(result: MigrationResult, output_dir: pathlib.Path) -> list[pathlib.Path]:
    written: list[pathlib.Path] = []
    log_out = output_dir / "discovery_log"
    log_out.mkdir(parents=True, exist_ok=True)
    for date_str, records in sorted(result.discovery_log.items()):
        path = log_out / f"{date_str}.json"
        path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
        written.append(path)
    return written


# ============================================================================
# CLI
# ============================================================================

def _format_summary(result: MigrationResult,
                    written_v2: list[pathlib.Path] | None,
                    written_log: list[pathlib.Path] | None,
                    dry_run: bool) -> str:
    lines = []
    lines.append(f"  source files processed:  {result.source_files_seen}")
    lines.append(f"  papers observed:         {result.papers_observed}")
    lines.append(f"  papers kept (post-dedup):{result.papers_kept}")
    lines.append(f"  papers deduped:          {result.papers_deduped}")
    lines.append(f"  papers missing date:     {result.papers_missing_date}")
    lines.append(f"  papers missing id:       {result.papers_missing_id}")
    lines.append(f"  v2 daily files:          {len(result.files_written)}")
    lines.append(f"  discovery_log dates:     {len(result.discovery_log)}")
    if dry_run:
        lines.append("  (dry-run: no files written)")
    else:
        lines.append(f"  v2 files written:        {len(written_v2 or [])}")
        lines.append(f"  log files written:       {len(written_log or [])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate v1 radar paper JSON to v2 schema (ADR-0015).",
    )
    parser.add_argument("--source-dir", default="data/_archive_v1/",
                        help="v1 source root (contains daily/ and historical/)")
    parser.add_argument("--output-dir", default="data/",
                        help="v2 output root (daily/ and discovery_log/ created)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report counts without writing any files")
    parser.add_argument("--no-discovery-log", action="store_true",
                        help="do not write discovery_log files")
    args = parser.parse_args(argv)

    source_dir = pathlib.Path(args.source_dir)
    output_dir = pathlib.Path(args.output_dir)

    if not source_dir.exists():
        print(f"error: source-dir does not exist: {source_dir}", file=sys.stderr)
        return 2

    result = run_migration(source_dir)

    written_v2: list[pathlib.Path] = []
    written_log: list[pathlib.Path] = []
    if not args.dry_run:
        written_v2 = write_v2_files(result, output_dir)
        if not args.no_discovery_log:
            written_log = write_discovery_log(result, output_dir)

    print("migrate_to_schema_v2 summary:")
    print(_format_summary(result, written_v2, written_log, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
