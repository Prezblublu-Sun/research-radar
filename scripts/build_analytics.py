"""scripts/build_analytics.py — corpus analytics, Phase A (A1: distribution).

Governed by ADR-0018 (decisions/ADR-0018-corpus-analytics.md). This script is
permitted to compute **descriptive statistics over scorer-emitted fields**.
It is NOT permitted to do topic modeling, embedding, knowledge / keyword
graph construction, citation-graph analysis, LLM narrative synthesis, or any
other operation that invents new semantic structure. If you want any of
those, stop and re-read ADR-0018 section 3.

Phase A (this file) computes A1 only:
  - distribution_yearly.csv   (long: year, direction, priority, scorer_version, count)
  - distribution_monthly.csv  (long: year_month, direction, priority, scorer_version, count)
  - distribution_yearly.png   (v3 ONLY, stacked bar by direction across years)
  - distribution_priority_ratio.png  (v3 ONLY, (High+Medium)/total per direction per year)

scorer_version handling: scorer_v1 and scorer_v3 priority calibrations are not
comparable. v3 is the primary axis. The CSVs carry scorer_version as a column
so v1/v3 rows live side-by-side without silently mixing. The PNGs render the
v3 slice ONLY. Summary reports the total / v3 / v1 / other-version split.

TODO (subsequent phases — DO NOT implement here):
  - Phase B (A2): tag / key_term frequency tables, per direction, per year
  - Phase C (A3): tag x direction co-occurrence + direction Jaccard heatmaps
  - Phase D:      docs/analytics/index.html summary page + link from index.html
  - Aggregate cache: persist the compact aggregate to
    docs/analytics/_aggregate_cache.json keyed on (bucket count, max mtime)
    so phases B/C/D can skip the scan. Phase A intentionally does NO caching
    — correctness first, no premature cache-invalidation logic.

CLI:
    python scripts/build_analytics.py [--daily-dir data/daily] \\
                                      [--out-dir docs/analytics] \\
                                      [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import time
from collections import Counter, defaultdict

# Canonical label sets. Used for ordering / labeling in PNGs and for
# deciding what gets bucketed under "OTHER" on the v3 chart axis. CSVs
# always carry the raw values verbatim — "OTHER" is a chart-only concept.
KNOWN_DIRECTIONS = ("ai_bioprinting", "am_biomedical", "fea_surrogate", "hip_implant")
KNOWN_PRIORITIES = ("High", "Medium", "Low", "Exclude")
PRIMARY_SCORER = "v3"
FOOTNOTE = (
    "Counts reflect the radar fetched corpus, not total field output. "
    "Per-day fetch yield dropped ~2023 (fetcher behavior); "
    "see FINDING-2023-fetch-yield-drop.md."
)
OTHER_LABEL = "OTHER"


def _year_and_month(bucket_date) -> tuple[str | None, str | None]:
    """Return (year, year_month) from a 'YYYY-MM-DD' bucket-level date.

    Returns (None, None) for missing or unparsable values. The bucket-level
    `date` is authoritative for binning (not paper-level `date`).
    """
    if not isinstance(bucket_date, str) or len(bucket_date) < 7:
        return None, None
    year = bucket_date[:4]
    year_month = bucket_date[:7]
    if not (year.isdigit() and year_month[5:7].isdigit()):
        return None, None
    return year, year_month


def _iter_buckets(daily_dir: pathlib.Path):
    """Yield (path, parsed_bucket_or_exception) for each *.json in daily_dir.

    Sort by filename so output is deterministic. Broken JSON yields the
    exception object so the caller can count + skip without crashing.
    """
    for path in sorted(daily_dir.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                bucket = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            yield path, exc
            continue
        yield path, bucket


def scan_corpus(daily_dir: pathlib.Path) -> dict:
    """Single streaming pass. Build the compact in-memory aggregate.

    Iterates files one at a time and discards parsed buckets after counting
    so peak memory stays bounded regardless of corpus size. Returns a dict
    with two Counters (yearly, monthly) plus run statistics.
    """
    yearly: Counter = Counter()    # (year, direction, priority, scorer_version) -> count
    monthly: Counter = Counter()   # (year_month, direction, priority, scorer_version) -> count

    stats = {
        "files_total": 0,
        "files_broken": 0,
        "papers_processed": 0,
        "papers_skipped_broken": 0,
        "papers_skipped_missing_direction": 0,
        "papers_skipped_missing_priority": 0,
        "papers_skipped_missing_date": 0,
        "directions_seen": Counter(),
        "priorities_seen": Counter(),
        "scorer_versions_seen": Counter(),
    }

    t0 = time.perf_counter()
    for _path, bucket in _iter_buckets(daily_dir):
        stats["files_total"] += 1
        if isinstance(bucket, Exception) or not isinstance(bucket, dict):
            stats["files_broken"] += 1
            continue
        year, year_month = _year_and_month(bucket.get("date"))
        papers = bucket.get("papers")
        if not isinstance(papers, list):
            continue
        for paper in papers:
            if not isinstance(paper, dict):
                stats["papers_skipped_broken"] += 1
                continue
            if year is None:
                stats["papers_skipped_missing_date"] += 1
                continue
            direction = paper.get("direction")
            if not isinstance(direction, str) or not direction:
                stats["papers_skipped_missing_direction"] += 1
                continue
            llm = paper.get("llm")
            priority = llm.get("priority") if isinstance(llm, dict) else None
            if not isinstance(priority, str) or not priority:
                stats["papers_skipped_missing_priority"] += 1
                continue
            scorer_version = paper.get("scorer_version") or "unknown"
            if not isinstance(scorer_version, str):
                scorer_version = str(scorer_version)

            yearly[(year, direction, priority, scorer_version)] += 1
            monthly[(year_month, direction, priority, scorer_version)] += 1
            stats["papers_processed"] += 1
            stats["directions_seen"][direction] += 1
            stats["priorities_seen"][priority] += 1
            stats["scorer_versions_seen"][scorer_version] += 1
        # parsed bucket goes out of scope here — peak memory stays bounded.

    stats["wall_time_seconds"] = time.perf_counter() - t0
    stats["throughput_pps"] = (
        stats["papers_processed"] / stats["wall_time_seconds"]
        if stats["wall_time_seconds"] > 0 else 0.0
    )
    return {"yearly": yearly, "monthly": monthly, "stats": stats}


def write_csv_long(out_path: pathlib.Path, counter: Counter, time_field: str) -> None:
    """Write a long-format CSV: time_field, direction, priority, scorer_version, count."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(counter.items())
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([time_field, "direction", "priority", "scorer_version", "count"])
        for (t, direction, priority, scorer_version), count in rows:
            writer.writerow([t, direction, priority, scorer_version, count])


def _chart_direction(direction: str) -> str:
    return direction if direction in KNOWN_DIRECTIONS else OTHER_LABEL


def render_stacked_bar(yearly: Counter, out_path: pathlib.Path) -> None:
    """v3-only stacked bar: X=year, Y=papers, stacked by direction."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    per_year: dict[str, Counter] = defaultdict(Counter)
    for (year, direction, _priority, scorer), count in yearly.items():
        if scorer != PRIMARY_SCORER:
            continue
        per_year[year][_chart_direction(direction)] += count

    years = sorted(per_year.keys(), key=lambda s: (len(s), s))
    directions = [d for d in KNOWN_DIRECTIONS if any(d in per_year[y] for y in years)]
    if any(OTHER_LABEL in per_year[y] for y in years):
        directions.append(OTHER_LABEL)

    fig, ax = plt.subplots(figsize=(12, 5))
    bottom = [0.0] * len(years)
    for direction in directions:
        heights = [per_year[y].get(direction, 0) for y in years]
        ax.bar(years, heights, bottom=bottom, label=direction)
        bottom = [b + h for b, h in zip(bottom, heights)]
    ax.set_title(f"Papers per year by direction (scorer_{PRIMARY_SCORER} only)")
    ax.set_xlabel("Year")
    ax.set_ylabel("Paper count")
    fig.text(0.5, 0.01, FOOTNOTE, ha="center", va="bottom",
             fontsize=7, color="gray", wrap=True)
    if directions:
        ax.legend(loc="upper left", fontsize="small")
    if years:
        ax.tick_params(axis="x", rotation=45)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def render_priority_ratio(yearly: Counter, out_path: pathlib.Path) -> None:
    """v3-only line plot: (High + Medium) / total per direction per year."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # direction -> year -> [hm_count, total_count]
    by_dir: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for (year, direction, priority, scorer), count in yearly.items():
        if scorer != PRIMARY_SCORER:
            continue
        cell = by_dir[_chart_direction(direction)][year]
        cell[1] += count
        if priority in ("High", "Medium"):
            cell[0] += count

    all_years = sorted({y for inner in by_dir.values() for y in inner.keys()},
                       key=lambda s: (len(s), s))
    directions_present = [d for d in KNOWN_DIRECTIONS if d in by_dir]
    if OTHER_LABEL in by_dir:
        directions_present.append(OTHER_LABEL)

    fig, ax = plt.subplots(figsize=(12, 5))
    for direction in directions_present:
        ratios: list[float] = []
        for y in all_years:
            cell = by_dir[direction].get(y)
            if cell and cell[1] > 0:
                ratios.append(cell[0] / cell[1])
            else:
                ratios.append(float("nan"))
        ax.plot(all_years, ratios, marker="o", label=direction)
    ax.set_title(f"(High + Medium) / total per direction (scorer_{PRIMARY_SCORER} only)")
    ax.set_xlabel("Year")
    ax.set_ylabel("Share of High+Medium papers")
    ax.set_ylim(0.0, 1.0)
    fig.text(0.5, 0.01,
             "scorer_v3 only. Source: radar fetched corpus (see FINDING-2023-fetch-yield-drop.md).",
             ha="center", va="bottom", fontsize=7, color="gray", wrap=True)
    if directions_present:
        ax.legend(loc="best", fontsize="small")
    if all_years:
        ax.tick_params(axis="x", rotation=45)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def lightweight_scan(daily_dir: pathlib.Path) -> dict:
    """--dry-run path: count files + papers only, no aggregation, no rendering."""
    files = 0
    papers = 0
    broken = 0
    t0 = time.perf_counter()
    for path in sorted(daily_dir.glob("*.json")):
        files += 1
        try:
            with open(path, encoding="utf-8") as fh:
                bucket = json.load(fh)
        except (OSError, json.JSONDecodeError):
            broken += 1
            continue
        plist = bucket.get("papers") if isinstance(bucket, dict) else None
        if isinstance(plist, list):
            papers += len(plist)
    return {
        "files": files,
        "papers": papers,
        "broken_files": broken,
        "wall_time_seconds": time.perf_counter() - t0,
    }


def _format_counter(c: Counter) -> str:
    return ", ".join(f"{k}={v}" for k, v in c.most_common()) or "(none)"


def print_summary(stats: dict, file=sys.stdout) -> None:
    scorer = stats["scorer_versions_seen"]
    total = stats["papers_processed"]
    v3 = scorer.get(PRIMARY_SCORER, 0)
    v1 = scorer.get("v1", 0)
    other = total - v3 - v1
    print("=" * 60, file=file)
    print("Analytics scan summary (Phase A — A1 distribution)", file=file)
    print("-" * 60, file=file)
    print(f"files scanned        : {stats['files_total']} (broken: {stats['files_broken']})", file=file)
    print(f"papers processed     : {total}", file=file)
    print(f"  scorer v3          : {v3}", file=file)
    print(f"  scorer v1          : {v1}", file=file)
    print(f"  scorer other       : {other}", file=file)
    print(
        "papers skipped       : "
        f"broken={stats['papers_skipped_broken']}, "
        f"missing_direction={stats['papers_skipped_missing_direction']}, "
        f"missing_priority={stats['papers_skipped_missing_priority']}, "
        f"missing_date={stats['papers_skipped_missing_date']}",
        file=file,
    )
    print(f"directions seen      : {_format_counter(stats['directions_seen'])}", file=file)
    print(f"priorities seen      : {_format_counter(stats['priorities_seen'])}", file=file)
    print(f"scorer_versions seen : {_format_counter(stats['scorer_versions_seen'])}", file=file)
    print(f"wall time (s)        : {stats['wall_time_seconds']:.2f}", file=file)
    print(f"throughput (paper/s) : {stats['throughput_pps']:.1f}", file=file)
    print("=" * 60, file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Corpus analytics — Phase A (A1 distribution stats only).",
    )
    parser.add_argument("--daily-dir", default="data/daily", type=pathlib.Path,
                        help="Directory of v2 daily bucket JSONs.")
    parser.add_argument("--out-dir", default="docs/analytics", type=pathlib.Path,
                        help="Where to write CSV/PNG outputs.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan + count + report scale only; write nothing.")
    args = parser.parse_args(argv)

    daily_dir: pathlib.Path = args.daily_dir
    if not daily_dir.is_dir():
        print(f"ERROR: --daily-dir is not a directory: {daily_dir}", file=sys.stderr)
        return 2

    if args.dry_run:
        info = lightweight_scan(daily_dir)
        print(f"[dry-run] daily-dir   : {daily_dir}")
        print(f"[dry-run] out-dir     : {args.out_dir} (not written)")
        print(f"[dry-run] files       : {info['files']} (broken: {info['broken_files']})")
        print(f"[dry-run] papers      : {info['papers']}")
        print(f"[dry-run] wall time   : {info['wall_time_seconds']:.2f}s")
        return 0

    aggregate = scan_corpus(daily_dir)
    stats = aggregate["stats"]
    yearly = aggregate["yearly"]
    monthly = aggregate["monthly"]

    out_dir: pathlib.Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv_long(out_dir / "distribution_yearly.csv", yearly, "year")
    write_csv_long(out_dir / "distribution_monthly.csv", monthly, "year_month")
    render_stacked_bar(yearly, out_dir / "distribution_yearly.png")
    render_priority_ratio(yearly, out_dir / "distribution_priority_ratio.png")

    print_summary(stats)
    print(f"wrote: {out_dir}/distribution_yearly.csv")
    print(f"wrote: {out_dir}/distribution_monthly.csv")
    print(f"wrote: {out_dir}/distribution_yearly.png")
    print(f"wrote: {out_dir}/distribution_priority_ratio.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
