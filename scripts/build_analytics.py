"""scripts/build_analytics.py — corpus analytics, Phases A + B (A1 distribution, A2 tag trends).

Governed by ADR-0018 (decisions/ADR-0018-corpus-analytics.md). This script is
permitted to compute **descriptive statistics over scorer-emitted fields**.
It is NOT permitted to do topic modeling, embedding, knowledge / keyword
graph construction, citation-graph analysis, LLM narrative synthesis, or any
other operation that invents new semantic structure. Synonym merging is
governed by the hard-coded ALIAS_MAP below ONLY — no inferred / learned
synonymy. If you want any of those, stop and re-read ADR-0018 section 3.

Implemented:
  A1 — distribution stats over (year, direction, priority, scorer_version):
    - distribution_yearly.csv   (long: year, direction, priority, scorer_version, count)
    - distribution_monthly.csv  (long: year_month, direction, priority, scorer_version, count)
    - distribution_yearly.png         (v3 ONLY, stacked bar by direction across years)
    - distribution_priority_ratio.png (v3 ONLY, (High+Medium)/total per direction per year)
  A2 — tag-frequency trends (v3 papers ONLY; v1 dropped from A2 entirely):
    - tag_frequency_by_year_by_direction.csv (long: year, direction, tag, count)
    - tag_top<N>_trends_<direction>.png   (one per direction; N from --top-n, default 12)
    - tag_emerging_terms.csv     (count_year >= 5 AND count_year >= 2 * count_prev_year)
    - methodology_showdown.png   (FEM family vs Neural-operator/PINN family, v3, all directions)

scorer_version handling:
  - A1: v1 and v3 priority calibrations are NOT comparable; CSVs carry
    scorer_version as a column so v1 / v3 rows live side-by-side; the A1
    PNGs render v3 only. Summary reports total / v3 / v1 / other split.
  - A2: v1 papers are dropped entirely; tag-trend analysis is v3-only.

A2 priority filter (default = High+Medium):
  By default, A2 tag aggregation counts ONLY v3 papers whose llm.priority is
  "High" or "Medium". This excludes Low/Exclude contamination (e.g. the
  ~11000 Excluded education papers routed into fea_surrogate). Pass
  --include-all-priorities to count all priorities (useful for inspecting
  contamination). A1 distribution stats are NOT affected by this flag.

TODO (subsequent phases — DO NOT implement here):
  - Phase C (A3): tag x direction co-occurrence + direction Jaccard heatmaps
  - Phase D:      docs/analytics/index.html summary page + link from index.html
  - Aggregate cache: persist the compact aggregate to
    docs/analytics/_aggregate_cache.json keyed on (bucket count, max mtime)
    so phases C/D can skip the scan. We intentionally do NO caching now
    — correctness first, no premature cache-invalidation logic.

Performance shape:
  - SINGLE pass over data/daily/*.json builds ALL aggregates (A1 + A2)
  - Stream one bucket at a time; never hold the full corpus resident
  - One in-memory Counter per output family; CSVs and PNGs derive from
    those Counters with no second disk scan

CLI:
    python scripts/build_analytics.py [--daily-dir data/daily] \\
                                      [--out-dir docs/analytics] \\
                                      [--top-n 12] \\
                                      [--include-all-priorities] [--dry-run]
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

# ----------------------------------------------------------------------------
# A2 (tag frequency) — hard-coded alias / exclude / family definitions.
# These are deterministic, embedded constants. NO inferred synonymy of any
# kind (no embeddings, no string-similarity, no clustering). If a tag is not
# in ALIAS_MAP it is kept verbatim with its original casing.
# ----------------------------------------------------------------------------

# canonical -> list of variant strings (matched case-insensitively, after strip)
ALIAS_MAP: dict[str, list[str]] = {
    "selective laser melting": ["slm", "lpbf", "laser powder bed fusion", "selective laser melting"],
    "physics-informed NN":     ["pinn", "physics-informed neural network", "physics-informed neural networks"],
    "surrogate modeling":      ["surrogate model", "surrogate modeling"],
    "Gaussian process":        ["gaussian process", "gaussian process regression"],
    "additive manufacturing":  ["additive manufacturing", "3d printing"],
}
# NOTE: "3D bioprinting" is intentionally NOT aliased into "bioprinting".

# Meta / paper-type tags dropped before counting (case-insensitive).
EXCLUDE_TAGS: set[str] = {"review", "no ai", "clinical study", "clinical outcomes"}

# Methodology-showdown families. Hard-coded explicit sets / predicate per
# ADR-0018: deterministic string match, NOT semantic / inferred synonymy.
# The widened defs cover the common phrasing variants we have observed in
# scorer-emitted tags so the showdown does not undercount either line.
FEM_FAMILY: set[str] = {
    "finite element analysis",
    "finite element method",
    "finite element",
    "finite element simulation",
    "finite element model",
    "finite element modeling",
}
# NEURAL_OP_PINN_FAMILY (predicate-based): a canonical tag belongs if its
# lowercased/stripped form contains the substring "neural operator" (covers
# "neural operator", "Fourier neural operator", "DeepONet neural operator",
# etc.) OR matches one of the physics-informed NN alias variants below.
# Substring matching here is a deterministic string operation, not semantic
# inference — see ADR-0018 sec 3.
NEURAL_OP_PINN_ALIASES: set[str] = {
    "pinn",
    "physics-informed neural network",
    "physics-informed neural networks",
    "physics-informed nn",
}

# Emerging-term arithmetic thresholds (no statistical modeling).
EMERGING_MIN_COUNT = 5
EMERGING_MIN_RATIO = 2


def _build_alias_lookup() -> dict[str, str]:
    """Flatten ALIAS_MAP into {normalized_variant: canonical}."""
    out: dict[str, str] = {}
    for canonical, variants in ALIAS_MAP.items():
        for variant in variants:
            out[variant.strip().lower()] = canonical
    return out


_ALIAS_LOOKUP = _build_alias_lookup()
_EXCLUDE_NORMALIZED = {t.strip().lower() for t in EXCLUDE_TAGS}
_FEM_FAMILY_NORM = {t.strip().lower() for t in FEM_FAMILY}
_NEURAL_OP_PINN_ALIASES_NORM = {t.strip().lower() for t in NEURAL_OP_PINN_ALIASES}


def _is_neural_op_pinn(tag: str) -> bool:
    """Predicate for NEURAL_OP/PINN family membership (case-insensitive)."""
    norm = tag.strip().lower()
    if "neural operator" in norm:
        return True
    return norm in _NEURAL_OP_PINN_ALIASES_NORM


def _canonicalize_tag(raw) -> tuple[str | None, str]:
    """Return (canonical_or_None, reason).

    reason is "ok" (emit canonical), "excluded" (drop via EXCLUDE_TAGS),
    or "invalid" (not a non-empty string). Canonicalization is by exact
    case-insensitive match on the alias map; unaliased tags keep their
    original casing (stripped of surrounding whitespace).
    """
    if not isinstance(raw, str):
        return None, "invalid"
    stripped = raw.strip()
    if not stripped:
        return None, "invalid"
    norm = stripped.lower()
    if norm in _EXCLUDE_NORMALIZED:
        return None, "excluded"
    if norm in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[norm], "ok"
    return stripped, "ok"


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


def scan_corpus(daily_dir: pathlib.Path,
                include_all_priorities: bool = False) -> dict:
    """Single streaming pass. Build the compact in-memory aggregate.

    Iterates files one at a time and discards parsed buckets after counting
    so peak memory stays bounded regardless of corpus size. Returns a dict
    with two Counters (yearly, monthly) plus run statistics.

    A2 tag aggregation honors the High+Medium-only default: a v3 paper's
    tags are counted only when priority in {High, Medium}, unless
    include_all_priorities is True (which reverts to the legacy behavior).
    A1 (yearly/monthly distribution counters) is unaffected.
    """
    yearly: Counter = Counter()    # (year, direction, priority, scorer_version) -> count
    monthly: Counter = Counter()   # (year_month, direction, priority, scorer_version) -> count
    yearly_tags: Counter = Counter()  # (year, direction, canonical_tag) -> count   (v3 only)

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
        # A2 counters
        "include_all_priorities": include_all_priorities,
        "tags_processed": 0,
        "tags_excluded": 0,
        "tags_invalid": 0,
        "v3_papers_in_a2_slice": 0,
        "v3_papers_with_tags": 0,
        "v3_papers_missing_tags": 0,
        "v3_papers_outside_a2_slice": 0,
        "v1_papers_dropped_from_a2": 0,
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

            # A2 — tag accumulation. v3 only; v1 papers are dropped from
            # tag-trend analysis entirely (calibration differs from v3).
            # Default: only count tags from High/Medium papers (HM slice).
            # The HM gate is just a condition inside this same per-paper
            # loop — there is no second scan.
            if scorer_version == PRIMARY_SCORER:
                eligible_for_a2 = (
                    include_all_priorities or priority in ("High", "Medium")
                )
                if eligible_for_a2:
                    stats["v3_papers_in_a2_slice"] += 1
                    tags = llm.get("tags") if isinstance(llm, dict) else None
                    if isinstance(tags, list):
                        stats["v3_papers_with_tags"] += 1
                        for raw_tag in tags:
                            canonical, reason = _canonicalize_tag(raw_tag)
                            if reason == "excluded":
                                stats["tags_excluded"] += 1
                                continue
                            if reason == "invalid":
                                stats["tags_invalid"] += 1
                                continue
                            yearly_tags[(year, direction, canonical)] += 1
                            stats["tags_processed"] += 1
                    else:
                        stats["v3_papers_missing_tags"] += 1
                else:
                    stats["v3_papers_outside_a2_slice"] += 1
            else:
                stats["v1_papers_dropped_from_a2"] += 1
        # parsed bucket goes out of scope here — peak memory stays bounded.

    stats["wall_time_seconds"] = time.perf_counter() - t0
    stats["throughput_pps"] = (
        stats["papers_processed"] / stats["wall_time_seconds"]
        if stats["wall_time_seconds"] > 0 else 0.0
    )
    return {
        "yearly": yearly,
        "monthly": monthly,
        "yearly_tags": yearly_tags,
        "stats": stats,
    }


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


# ----------------------------------------------------------------------------
# A2 — tag-frequency CSV writers and PNG renderers
# ----------------------------------------------------------------------------

def write_tag_frequency_csv(out_path: pathlib.Path, tag_counter: Counter) -> None:
    """Long-format CSV: year, direction, tag, count (v3-only tags, canonicalized)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(tag_counter.items())
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["year", "direction", "tag", "count"])
        for (year, direction, tag), count in rows:
            writer.writerow([year, direction, tag, count])


def write_emerging_terms_csv(out_path: pathlib.Path, tag_counter: Counter) -> None:
    """Year-over-year arithmetic emergence.

    For each (direction, tag, year) we look up (direction, tag, year-1) and
    emit a row when count_year >= EMERGING_MIN_COUNT AND
    count_year >= EMERGING_MIN_RATIO * count_prev_year. Tags whose previous
    year is 0 (first appearance) still qualify when count_year >= MIN_COUNT.
    """
    by_dt: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for (year, direction, tag), count in tag_counter.items():
        by_dt[(direction, tag)][year] = count

    rows: list[tuple[str, str, str, int, int, int]] = []
    for (direction, tag), year_counts in by_dt.items():
        for year, count_year in year_counts.items():
            try:
                prev_year_int = int(year) - 1
            except (TypeError, ValueError):
                continue
            prev_year = str(prev_year_int)
            count_prev = year_counts.get(prev_year, 0)
            if count_year >= EMERGING_MIN_COUNT and count_year >= EMERGING_MIN_RATIO * count_prev:
                rows.append((tag, direction, year, count_year, count_prev, count_year - count_prev))

    rows.sort(key=lambda r: (r[2], r[1], -r[3], r[0]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tag", "direction", "year", "count_year", "count_prev_year", "delta"])
        for row in rows:
            writer.writerow(row)


def _a2_scope_label(include_all_priorities: bool) -> str:
    return "all priorities" if include_all_priorities else "High+Medium papers only"


def render_tag_trends_per_direction(tag_counter: Counter,
                                    out_dir: pathlib.Path,
                                    top_n: int,
                                    include_all_priorities: bool = False,
                                    ) -> list[pathlib.Path]:
    """One line-plot PNG per KNOWN direction: top-N tags by total count.

    Returns the list of files written so the caller can report them. Directions
    with no tag data are skipped (no empty PNG).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_dir_tag_year: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for (year, direction, tag), count in tag_counter.items():
        by_dir_tag_year[direction][tag][year] += count

    scope_label = _a2_scope_label(include_all_priorities)
    written: list[pathlib.Path] = []
    for direction in KNOWN_DIRECTIONS:
        per_tag = by_dir_tag_year.get(direction)
        if not per_tag:
            continue
        tag_totals = Counter({tag: sum(years.values()) for tag, years in per_tag.items()})
        top_tags = [tag for tag, _ in tag_totals.most_common(top_n)]
        if not top_tags:
            continue
        all_years = sorted(
            {y for tag in top_tags for y in per_tag[tag]},
            key=lambda s: (len(s), s),
        )

        fig, ax = plt.subplots(figsize=(12, 6))
        for tag in top_tags:
            counts = [per_tag[tag].get(y, 0) for y in all_years]
            ax.plot(all_years, counts, marker="o", label=tag)
        ax.set_title(
            f"Top {len(top_tags)} tag trends — {direction} "
            f"(scorer_{PRIMARY_SCORER}; {scope_label}; tag-occurrence counts)"
        )
        ax.set_xlabel("Year")
        ax.set_ylabel("Tag occurrences")
        fig.text(0.5, 0.01, FOOTNOTE, ha="center", va="bottom",
                 fontsize=7, color="gray", wrap=True)
        ax.legend(loc="best", fontsize="x-small", ncol=2)
        if all_years:
            ax.tick_params(axis="x", rotation=45)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
        out_path = out_dir / f"tag_top{top_n}_trends_{direction}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        written.append(out_path)
    return written


def compute_showdown_aggregates(tag_counter: Counter) -> tuple[Counter, Counter]:
    """Year-keyed aggregates for FEM family and NO/PINN family.

    Uses the hard-coded FEM_FAMILY set and the _is_neural_op_pinn predicate
    (deterministic string match per ADR-0018). Exposed so tests and ad-hoc
    inspection scripts can read the same totals the showdown PNG renders.
    """
    fem_per_year: Counter = Counter()
    pinn_per_year: Counter = Counter()
    for (year, _direction, tag), count in tag_counter.items():
        norm = tag.strip().lower()
        if norm in _FEM_FAMILY_NORM:
            fem_per_year[year] += count
        elif _is_neural_op_pinn(tag):
            pinn_per_year[year] += count
    return fem_per_year, pinn_per_year


def render_methodology_showdown(tag_counter: Counter,
                                out_path: pathlib.Path,
                                include_all_priorities: bool = False) -> None:
    """FEM family vs Neural-operator/PINN family, summed across directions.

    The title and footnote make explicit this is a frequency comparison of
    tag occurrences, not a structural claim about the field.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fem_per_year, pinn_per_year = compute_showdown_aggregates(tag_counter)

    all_years = sorted(set(fem_per_year) | set(pinn_per_year),
                       key=lambda s: (len(s), s))
    scope_label = _a2_scope_label(include_all_priorities)
    fig, ax = plt.subplots(figsize=(12, 5))
    fem_counts = [fem_per_year.get(y, 0) for y in all_years]
    pinn_counts = [pinn_per_year.get(y, 0) for y in all_years]
    ax.plot(all_years, fem_counts, marker="o", label="FEM family")
    ax.plot(all_years, pinn_counts, marker="s", label="Neural-operator/PINN family")
    ax.set_title(
        "Methodology tag-frequency comparison "
        f"(scorer_{PRIMARY_SCORER}, all directions; {scope_label}; "
        "tag-occurrence counts, not a field-trend claim)"
    )
    ax.set_xlabel("Year")
    ax.set_ylabel("Tag occurrences")
    fig.text(0.5, 0.01, FOOTNOTE, ha="center", va="bottom",
             fontsize=7, color="gray", wrap=True)
    if all_years:
        ax.legend(loc="best", fontsize="small")
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
    print("=" * 64, file=file)
    print("Analytics scan summary (Phases A + B — A1 distribution, A2 tag trends)", file=file)
    print("-" * 64, file=file)
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
    a2_slice_label = (
        "all priorities" if stats["include_all_priorities"] else "High+Medium only"
    )
    print(f"-- A2 tag stats (v3 only; A2 slice = {a2_slice_label}) --", file=file)
    print(f"v3 papers in A2 slice: {stats['v3_papers_in_a2_slice']}", file=file)
    print(f"  with tags          : {stats['v3_papers_with_tags']}", file=file)
    print(f"  without tags       : {stats['v3_papers_missing_tags']}", file=file)
    print(f"v3 papers OUTSIDE    : {stats['v3_papers_outside_a2_slice']}"
          " (Low/Exclude, dropped from A2)", file=file)
    print(f"v1 dropped from A2   : {stats['v1_papers_dropped_from_a2']}", file=file)
    print(f"tag occurrences kept : {stats['tags_processed']}", file=file)
    print(f"tags excluded (meta) : {stats['tags_excluded']}", file=file)
    print(f"tags invalid/empty   : {stats['tags_invalid']}", file=file)
    print("-- timing --", file=file)
    print(f"wall time (s)        : {stats['wall_time_seconds']:.2f}", file=file)
    print(f"throughput (paper/s) : {stats['throughput_pps']:.1f}", file=file)
    print("=" * 64, file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Corpus analytics — Phases A + B (A1 distribution + A2 tag trends).",
    )
    parser.add_argument("--daily-dir", default="data/daily", type=pathlib.Path,
                        help="Directory of v2 daily bucket JSONs.")
    parser.add_argument("--out-dir", default="docs/analytics", type=pathlib.Path,
                        help="Where to write CSV/PNG outputs.")
    parser.add_argument("--top-n", type=int, default=12,
                        help="Top-N tags plotted per direction (A2, default 12).")
    parser.add_argument("--include-all-priorities", action="store_true", default=False,
                        help="A2 only: count tags from ALL priorities. Default is "
                             "High+Medium papers only (removes Low/Exclude "
                             "contamination, e.g. routed-then-Excluded education "
                             "papers). A1 is unaffected.")
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

    aggregate = scan_corpus(daily_dir, include_all_priorities=args.include_all_priorities)
    stats = aggregate["stats"]
    yearly = aggregate["yearly"]
    monthly = aggregate["monthly"]
    yearly_tags = aggregate["yearly_tags"]

    out_dir: pathlib.Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- A1 outputs (unchanged — counts all priorities across all scorer_versions) ---
    write_csv_long(out_dir / "distribution_yearly.csv", yearly, "year")
    write_csv_long(out_dir / "distribution_monthly.csv", monthly, "year_month")
    render_stacked_bar(yearly, out_dir / "distribution_yearly.png")
    render_priority_ratio(yearly, out_dir / "distribution_priority_ratio.png")

    # --- A2 outputs (default: High+Medium slice; --include-all-priorities flips) ---
    write_tag_frequency_csv(out_dir / "tag_frequency_by_year_by_direction.csv", yearly_tags)
    trend_pngs = render_tag_trends_per_direction(
        yearly_tags, out_dir, args.top_n,
        include_all_priorities=args.include_all_priorities,
    )
    write_emerging_terms_csv(out_dir / "tag_emerging_terms.csv", yearly_tags)
    render_methodology_showdown(
        yearly_tags, out_dir / "methodology_showdown.png",
        include_all_priorities=args.include_all_priorities,
    )

    print_summary(stats)
    print(f"wrote: {out_dir}/distribution_yearly.csv")
    print(f"wrote: {out_dir}/distribution_monthly.csv")
    print(f"wrote: {out_dir}/distribution_yearly.png")
    print(f"wrote: {out_dir}/distribution_priority_ratio.png")
    print(f"wrote: {out_dir}/tag_frequency_by_year_by_direction.csv")
    for path in trend_pngs:
        print(f"wrote: {path}")
    print(f"wrote: {out_dir}/tag_emerging_terms.csv")
    print(f"wrote: {out_dir}/methodology_showdown.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
