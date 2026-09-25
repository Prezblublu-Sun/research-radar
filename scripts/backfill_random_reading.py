"""Run the ADR-0035 serendipity pass over past days.

The pass normally runs at the end of each daily run, on the papers that run
scored. A backfill has to reconstruct that: every paper carries
``first_seen_at``, so the papers of run-day D are the corpus records stamped
with D — which is the same set the live pass saw, not "papers published on
D" (a run scores a 14-day publication window).

Two things are missing from old records and are recovered here:

* ``venue_id`` only exists on papers normalised after ADR-0035 shipped, so
  the journals are resolved from OpenAlex in batches of 50;
* the month window follows the *run day*, not today, so a backfill of an
  August day reads August.

Everything else — the draw, the 5%/floor-2/cap-5 rule, the seeding, the
scorer, the file layout — is the production code path, so a backfilled day
is indistinguishable from a live one.

    python -m scripts.backfill_random_reading --days 7
    python -m scripts.backfill_random_reading --from 2026-09-17 --to 2026-09-23
    python -m scripts.backfill_random_reading --days 7 --dry-run

A day that already has a file is skipped unless --force or --top-up is
given: the point is to fill gaps, not to pay for a second draw.

--top-up exists for a rule change. --force throws the day away and draws it
again, which also throws away whatever the old draw found — and since the
stream remembers its own picks, the redraw is guaranteed to be different
papers. --top-up instead keeps what is there and draws only the shortfall,
so raising a journal's allocation from two to five costs three papers and
loses nothing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetchers import openalex_fetcher  # noqa: E402
from pipeline import llm_scorer, random_reading, v2_schema as v2  # noqa: E402
import yaml  # noqa: E402

# A daily run only writes papers inside its fetch window (arXiv 5d, OpenAlex
# 14d) plus whatever publishers dated ahead. Observed spread over 2026-09 was
# at most 20 days back; 45 each way is slack, and it keeps a backfill from
# reading all 3,500 bucket files.
BUCKET_SLACK_DAYS = 45


def _print(message: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def run_days(from_date: str, to_date: str) -> list[str]:
    start, end = dt.date.fromisoformat(from_date), dt.date.fromisoformat(to_date)
    return [(start + dt.timedelta(days=n)).isoformat()
            for n in range((end - start).days + 1)]


def papers_by_run_day(data_dir: pathlib.Path, days: list[str]) -> dict[str, list[dict]]:
    """Corpus records grouped by the run that first saw them."""
    wanted = set(days)
    low = (dt.date.fromisoformat(min(days))
           - dt.timedelta(days=BUCKET_SLACK_DAYS)).isoformat()
    high = (dt.date.fromisoformat(max(days))
            + dt.timedelta(days=BUCKET_SLACK_DAYS)).isoformat()
    found: dict[str, list[dict]] = {day: [] for day in days}
    for path in sorted((data_dir / "daily").glob("*.json")):
        if not (low <= path.stem <= high):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for paper in doc.get("papers", []):
            day = (paper.get("first_seen_at") or "")[:10]
            if day in wanted:
                found[day].append(paper)
    return found


def high_papers_with_journals(papers: list[dict]) -> list[dict]:
    """The High papers of one run, with their journal filled back in."""
    high = [p for p in papers if (p.get("llm") or {}).get("priority") == "High"]
    need = [str(p.get("id") or "").rsplit("/", 1)[-1]
            for p in high
            if p.get("source") == "openalex" and not p.get("venue_id")]
    resolved = openalex_fetcher.resolve_sources([w for w in need if w.startswith("W")])
    for paper in high:
        if paper.get("venue_id"):
            continue
        info = resolved.get(str(paper.get("id") or "").rsplit("/", 1)[-1])
        if info:
            paper.update(info)
    return high


def existing_day(path: pathlib.Path) -> tuple[list[dict], dict[str, int]]:
    """Papers already recorded for a day, and how many each journal gave."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], {}
    papers = payload.get("papers") or []
    held: dict[str, int] = {}
    for paper in papers:
        venue = (paper.get("random_reading") or {}).get("venue_id") or ""
        if venue:
            held[venue] = held.get(venue, 0) + 1
    return papers, held


def merge_reports(old: list[dict], new: list[dict]) -> list[dict]:
    """Carry the earlier draw's positions into the refreshed journal report.

    Everything else comes from the new report, because it describes the
    current rule: `target_picks` and `month_works` would otherwise keep
    advertising whatever the file was built under.

    `skipped_known` is the one count that must NOT be summed. The two draws
    share an ordering prefix, so the second scan re-walks and re-skips most
    of the same papers; adding them produced "skipped 21 already in the
    library" for a journal that published 15 that month. The later scan
    covers a superset of the positions, so it is the count to keep.
    """
    before = {entry.get("venue_id"): entry for entry in old}
    merged = []
    for entry in new:
        previous = before.get(entry.get("venue_id")) or {}
        entry = dict(entry)
        seen_positions = list(previous.get("positions") or [])
        entry["positions"] = seen_positions + [
            position for position in entry["positions"]
            if position not in seen_positions
        ]
        entry["skipped_known"] = max(previous.get("skipped_known") or 0,
                                     entry["skipped_known"])
        merged.append(entry)
    return merged


def known_keys(data_dir: pathlib.Path) -> set[str]:
    try:
        state = json.loads((data_dir / "seen_dois.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {k for k in state.get("keys", []) if isinstance(k, str)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=pathlib.Path, default=ROOT / "data")
    parser.add_argument("--days", type=int,
                        help="how many days back from yesterday")
    parser.add_argument("--from", dest="from_date", help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", help="YYYY-MM-DD")
    parser.add_argument("--force", action="store_true",
                        help="throw away days that already have a file and redraw")
    parser.add_argument("--top-up", dest="top_up", action="store_true",
                        help="keep what a day already has and draw only the "
                             "shortfall against the current rule")
    parser.add_argument("--dry-run", action="store_true",
                        help="pick and report, but score nothing and write nothing")
    args = parser.parse_args(argv)

    if args.days:
        end = dt.date.today() - dt.timedelta(days=1)
        start = end - dt.timedelta(days=args.days - 1)
        days = run_days(start.isoformat(), end.isoformat())
    elif args.from_date and args.to_date:
        days = run_days(args.from_date, args.to_date)
    else:
        parser.error("give --days N, or both --from and --to")

    cfg = yaml.safe_load((ROOT / "config" / "directions.yaml").read_text(encoding="utf-8"))
    directions, exclusions = cfg["directions"], cfg.get("exclusions", {})
    data_dir = args.data_root
    out_dir = data_dir / "random_reading"

    _print(f"Backfilling {len(days)} run-day(s): {days[0]} .. {days[-1]}")
    grouped = papers_by_run_day(data_dir, days)
    seen = known_keys(data_dir) | random_reading.drawn_keys(data_dir)
    totals = {"days": 0, "journals": 0, "papers": 0, "skipped": 0, "errors": 0}

    for day in days:
        target = out_dir / f"{day}.json"
        held_papers: list[dict] = []
        held_counts: dict[str, int] = {}
        held_report: list[dict] = []
        if target.exists():
            if args.top_up:
                held_papers, held_counts = existing_day(target)
                held_report = (json.loads(target.read_text(encoding="utf-8"))
                               .get("journals") or [])
            elif not args.force:
                _print(f"{day}: already has a file, skipping")
                totals["skipped"] += 1
                continue
        papers = grouped.get(day) or []
        if not papers:
            _print(f"{day}: no run found in the corpus")
            continue
        high = high_papers_with_journals(papers)
        if not high:
            _print(f"{day}: {len(papers)} paper(s), no High")
            continue

        picks, report = random_reading.collect(
            high, seen, day, directions, exclusions, have=held_counts)
        # `collect` adds each pick to the set, so later days in this same
        # backfill will not draw them again either.
        names = ", ".join(
            f"{j['venue']}({j['month_works']}→{j['target_picks']}"
            + (f", 已有{held_counts.get(j['venue_id'], 0)}"
               if held_counts.get(j["venue_id"]) else "") + ")"
            for j in report["journals"]) or "(none)"
        _print(f"{day}: {len(high)} High, {len(report['journals'])} journal(s) "
               f"-> {len(picks)} new paper(s) [{names}]")
        totals["journals"] += len(report["journals"])
        totals["errors"] += report["errors"]
        if not picks:
            if not held_papers:
                continue
            # Nothing new to buy, but the stored journal metadata may still
            # be advertising the rule the day was drawn under. Refreshing it
            # costs a file write and keeps the page honest.
            refreshed = merge_reports(held_report, report["journals"])
            if refreshed != held_report:
                v2.atomic_write_json(target, random_reading.build_file(
                    day, held_papers, refreshed,
                    v2.scorer_version_from_active_prompt(), v2.utc_now_iso()))
                _print("    nothing to add; refreshed the journal metadata")
            else:
                _print("    nothing to add; the day already meets the rule")
            continue
        totals["papers"] += len(picks)
        if args.dry_run:
            for paper in picks:
                _print(f"    - {paper.get('title', '')[:88]}")
            continue

        scored, _raw = llm_scorer.score_batch(picks, directions)
        out_dir.mkdir(parents=True, exist_ok=True)
        v2.atomic_write_json(target, random_reading.build_file(
            day, held_papers + scored, merge_reports(held_report, report["journals"]),
            v2.scorer_version_from_active_prompt(), v2.utc_now_iso()))
        counts: dict[str, int] = {}
        for paper in scored:
            key = (paper.get("llm") or {}).get("priority") or "Unscored"
            counts[key] = counts.get(key, 0) + 1
        kept = f" (kept {len(held_papers)})" if held_papers else ""
        _print(f"    scored {counts}{kept} -> {target}")
        totals["days"] += 1
        if llm_scorer.budget_exhausted():
            _print("::warning::DeepSeek balance exhausted; stopping the backfill")
            break

    _print(f"Done: {totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
