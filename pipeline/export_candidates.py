"""Export Medium+ candidates from data/daily/*.json to data/exports/candidates.jsonl.

This is the Radar -> lit-system contract handoff (SCOPE.md "Radar to lit-system
contract", TODO.md W2.3 / B1). It is a read-only consumer of Radar's daily JSONs
- no fetcher calls, no LLM calls, no Zotero writes.

================================================================================
JSONL OUTPUT SCHEMA -- AUTHORITATIVE CONTRACT
================================================================================

One paper per JSONL line. UTF-8, ensure_ascii=False, keys sorted within each
line. The schema below is the canonical contract between Radar and lit-system;
changes here must be mirrored in lit-system's CLAUDE.md and any lit-system
inbox-importer code.

Schema (flat -- the daily JSON's nested `llm.*` block is flattened so
lit-system reads top-level keys, no dot-navigation required):

  Identity:
    doi                       str   canonical DOI (may be "" for arxiv preprints)
    arxiv_id                  str   arXiv id (e.g. "2605.13834v1"); fallback
                                    primary key when doi == ""
    title                     str
    url                       str
    source                    str   "arxiv" | "openalex" | "pubmed"
    date                      str   ISO date string from upstream
    date_precision            str   "day" | "month" | "year" -- granularity of
                                    `date`; under v2 a month/year-precision date
                                    is still a full ISO date pinned to the 1st
    year                      int|None
    venue                     str

  Content:
    abstract                  str   upstream abstract, full (used by lit-system
                                    pre-ingest triage UI)

  Authorship (may be empty for the arxiv source -- lit-system must handle
  empty string / empty list gracefully):
    authors                   list[str]
    first_author_affiliation  str   ""  when not provided upstream
    corresponding_authors     list[dict]  [] when not provided upstream;
                                    each entry: {name, affiliation, inferred?}

  Routing:
    direction                 str   internal direction key (e.g. "fea_surrogate")
    direction_name            str   display name

  LLM scoring (flattened from data/daily/*.json `llm.*`):
    priority                  "High" | "Medium" | "Low" | "Exclude"
    relevance_level           str
    read_action               str
    validation_kind           str
    relevance_to_user         str
    why_not_core              str
    flags                     dict
    tags                      list[str]
    key_terms                 list[dict]  each {en, zh}
    summary_zh                dict        {motivation, method, result, validation}
    summary_en                dict        same shape

  Provenance:
    scorer_version            str   prompt version that graded this paper
                                    (e.g. "v3"); "" for legacy v1 records
    radar_source_date         str   YYYY-MM-DD of the source daily/*.json.
                                    Under the v2 corpus, daily files are
                                    bucketed by *publication* date, so this is
                                    effectively the paper's publication date,
                                    not the radar-run date. The field name is
                                    kept for the lit-system contract (ADR-0015).
    radar_export_date         str   YYYY-MM-DD this export ran
    radar_export_version      str   schema version, currently "v2"

Lit-system primary key recipe:
    candidate_id = doi if doi else arxiv_id
    # If both empty (rare; arxiv always supplies arxiv_id), fall back to title.

Cross-day dedup:
    When the same paper (by doi-or-arxiv-id) appears in multiple daily JSONs,
    the exporter keeps the entry from the latest radar_source_date. Dedupe
    count is printed to stderr.

Sort order:
    (radar_source_date DESC, priority_rank ASC, direction ASC)
    -> newest, highest-priority papers come first.
    Priority rank: High=0 Medium=1 Low=2 Exclude=3.
================================================================================
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Iterable


ROOT = pathlib.Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "daily"
DEFAULT_OUTPUT = ROOT / "data" / "exports" / "candidates.jsonl"

EXPORT_VERSION = "v2"

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2, "Exclude": 3}

MIN_PRIORITY_INCLUDES: dict[str, set[str]] = {
    "High":   {"High"},
    "Medium": {"High", "Medium"},
    "Low":    {"High", "Medium", "Low"},
    "All":    {"High", "Medium", "Low", "Exclude"},
}

DAILY_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")


def _load_papers_v2_or_v1(path: pathlib.Path) -> tuple[list[dict], dict]:
    """Return (papers, file_meta) for a daily JSON, v2-dict or stray v1-list.

    v2 (ADR-0015 §4.5): {schema_version, date, date_precision, papers, counts}
    v1 (pre-migration): top-level list of paper dicts.
    Anything unparseable / unexpected returns ([], {}).

    Mirrors render/build_pages.py:_load_papers_v2_or_v1. Duplicated rather
    than imported because export_candidates.py is a standalone read-only
    contract producer and must not take a dependency on the render layer.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], {}
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        papers = data.get("papers", [])
        if not isinstance(papers, list):
            papers = []
        meta = {k: v for k, v in data.items() if k != "papers"}
        return papers, meta
    return [], {}


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _discover_daily_files(
    daily_dir: pathlib.Path,
    from_date: dt.date | None,
    to_date: dt.date | None,
) -> list[tuple[dt.date, pathlib.Path]]:
    """Return [(date, path), ...] sorted by date ASC.

    Only matches files literally named YYYY-MM-DD.json, so .SKIPPED.json
    marker files are silently ignored.
    """
    out: list[tuple[dt.date, pathlib.Path]] = []
    if not daily_dir.exists():
        return out
    for p in sorted(daily_dir.iterdir()):
        m = DAILY_FILENAME_RE.match(p.name)
        if not m:
            continue
        d = _parse_date(m.group(1))
        if from_date and d < from_date:
            continue
        if to_date and d > to_date:
            continue
        out.append((d, p))
    return out


def _build_record(paper: dict, source_date: str, export_date: str) -> dict:
    """Flatten one daily-JSON paper into the exporter's output schema."""
    llm = paper.get("llm") or {}
    return {
        "doi":       paper.get("doi", "") or "",
        "arxiv_id":  paper.get("arxiv_id", "") or "",
        "title":     paper.get("title", "") or "",
        "url":       paper.get("url", "") or "",
        "source":    paper.get("source", "") or "",
        "date":      paper.get("date", "") or "",
        "date_precision": paper.get("date_precision", "") or "",
        "year":      paper.get("year"),
        "venue":     paper.get("venue", "") or "",
        "abstract":  paper.get("abstract", "") or "",
        "authors":                  list(paper.get("authors") or []),
        "first_author_affiliation": paper.get("first_author_affiliation", "") or "",
        "corresponding_authors":    list(paper.get("corresponding_authors") or []),
        "direction":      paper.get("direction", "") or "",
        "direction_name": paper.get("direction_name", "") or "",
        "priority":          llm.get("priority", "") or "",
        "relevance_level":   llm.get("relevance_level", "") or "",
        "read_action":       llm.get("read_action", "") or "",
        "validation_kind":   llm.get("validation_kind", "") or "",
        "relevance_to_user": llm.get("relevance_to_user", "") or "",
        "why_not_core":      llm.get("why_not_core", "") or "",
        "flags":             dict(llm.get("flags") or {}),
        "tags":              list(llm.get("tags") or []),
        "key_terms":         list(llm.get("key_terms") or []),
        "summary_zh":        dict(llm.get("summary_zh") or {}),
        "summary_en":        dict(llm.get("summary_en") or {}),
        "scorer_version":       paper.get("scorer_version", "") or "",
        "radar_source_date":    source_date,
        "radar_export_date":    export_date,
        "radar_export_version": EXPORT_VERSION,
    }


def _dedup_key(rec: dict) -> str:
    """Stable primary key for cross-day dedup: doi > arxiv_id > title."""
    if rec.get("doi"):
        return f"doi:{rec['doi']}"
    if rec.get("arxiv_id"):
        return f"arxiv:{rec['arxiv_id']}"
    return f"title:{rec.get('title', '')}"


def _sort_key(rec: dict) -> tuple:
    return (
        -dt.date.fromisoformat(rec["radar_source_date"]).toordinal(),
        PRIORITY_RANK.get(rec["priority"], 99),
        rec.get("direction", ""),
    )


def collect_records(
    daily_files: list[tuple[dt.date, pathlib.Path]],
    min_priority: str,
    export_date: str,
) -> tuple[list[dict], int, int]:
    """Read daily files, filter by priority, dedup, sort.

    Returns (records, total_scanned, dedup_collisions).
    """
    allowed = MIN_PRIORITY_INCLUDES[min_priority]
    by_key: dict[str, dict] = {}
    scanned = 0
    collisions = 0

    for date, path in daily_files:
        papers, _meta = _load_papers_v2_or_v1(path)
        if not papers:
            # Empty list, unparseable, or unexpected top-level shape.
            # _load_papers_v2_or_v1 already tolerates v2 dict + v1 list;
            # anything else (or a genuinely empty file) is skipped quietly.
            continue

        source_date = date.isoformat()
        for paper in papers:
            scanned += 1
            prio = ((paper.get("llm") or {}).get("priority") or "Low")
            if prio not in allowed:
                continue
            rec = _build_record(paper, source_date=source_date, export_date=export_date)
            key = _dedup_key(rec)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = rec
                continue
            collisions += 1
            if rec["radar_source_date"] > existing["radar_source_date"]:
                by_key[key] = rec
            # Tie or older: keep existing.

    records = sorted(by_key.values(), key=_sort_key)
    return records, scanned, collisions


def write_jsonl(records: Iterable[dict], output: pathlib.Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with output.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True))
            f.write("\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export Medium+ candidates from data/daily/*.json to a JSONL for "
            "lit-system to consume. See module docstring for the authoritative "
            "schema."
        )
    )
    parser.add_argument(
        "--min-priority",
        choices=list(MIN_PRIORITY_INCLUDES.keys()),
        default="Medium",
        help="Minimum priority tier to include (default: Medium = High + Medium).",
    )
    parser.add_argument(
        "--from-date", type=str, default=None,
        help="Only include daily/YYYY-MM-DD.json with date >= this (inclusive).",
    )
    parser.add_argument(
        "--to-date", type=str, default=None,
        help="Only include daily/YYYY-MM-DD.json with date <= this (inclusive).",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Explicitly scan all dates. Mutually exclusive with --from-date / --to-date.",
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=DEFAULT_OUTPUT,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT.relative_to(ROOT)}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print summary to stdout but write no file.",
    )
    parser.add_argument(
        "--daily-dir", type=pathlib.Path, default=DAILY_DIR,
        help=argparse.SUPPRESS,  # internal flag used by tests
    )
    args = parser.parse_args(argv)

    if args.all and (args.from_date or args.to_date):
        parser.error("--all is mutually exclusive with --from-date / --to-date")

    from_date = _parse_date(args.from_date) if args.from_date else None
    to_date = _parse_date(args.to_date) if args.to_date else None
    if from_date and to_date and from_date > to_date:
        parser.error(f"--from-date {from_date} is after --to-date {to_date}")

    export_date = dt.date.today().isoformat()

    daily_files = _discover_daily_files(args.daily_dir, from_date, to_date)
    if not daily_files:
        print("[info] no daily files matched; nothing to export.", file=sys.stderr)
        if not args.dry_run:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text("", encoding="utf-8")
        return 0

    records, scanned, collisions = collect_records(
        daily_files,
        min_priority=args.min_priority,
        export_date=export_date,
    )

    if collisions:
        print(
            f"[info] cross-day dedup: {collisions} duplicate(s) folded "
            f"(kept latest radar_source_date)",
            file=sys.stderr,
        )

    print(
        f"[info] scanned {scanned} paper(s) from {len(daily_files)} daily "
        f"file(s); kept {len(records)} after --min-priority={args.min_priority}",
        file=sys.stderr,
    )

    if args.dry_run:
        print(f"[dry-run] would write {len(records)} record(s) to {args.output}")
        return 0

    n = write_jsonl(records, args.output)
    print(f"[ok] wrote {n} record(s) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
