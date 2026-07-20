"""Audit or repair stale derived ``counts`` blocks in v2 daily buckets.

Dry-run is the default. ``--apply`` rewrites only buckets whose derived
counts differ from ``pipeline.v2_schema.build_v2_counts(papers)`` and uses the
same atomic writer as the daily pipeline.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from pipeline import v2_schema as v2


ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DAILY_DIR = ROOT / "data" / "daily"


def audit_counts(daily_dir: pathlib.Path, *, apply: bool = False,
                 verbose: bool = True) -> dict:
    stats = {"scanned": 0, "mismatched": 0, "repaired": 0, "skipped": 0}

    for path in sorted(daily_dir.glob("20*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stats["skipped"] += 1
            continue
        if not isinstance(data, dict) or not isinstance(data.get("papers"), list):
            stats["skipped"] += 1
            continue

        stats["scanned"] += 1
        expected = v2.build_v2_counts(data["papers"])
        if data.get("counts") == expected:
            continue

        stats["mismatched"] += 1
        old_priority = (data.get("counts") or {}).get("priority_counts")
        if verbose:
            print(f"{path.name}: priority_counts {old_priority!r} -> "
                  f"{expected.get('priority_counts')!r}")
        if apply:
            data["counts"] = expected
            v2.atomic_write_json(path, data)
            stats["repaired"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit/rebuild derived counts in data/daily v2 buckets."
    )
    parser.add_argument("--daily-dir", type=pathlib.Path,
                        default=DEFAULT_DAILY_DIR)
    parser.add_argument("--apply", action="store_true",
                        help="Atomically rewrite mismatched counts blocks.")
    parser.add_argument("--quiet", action="store_true",
                        help="Print only the final summary.")
    args = parser.parse_args(argv)

    stats = audit_counts(args.daily_dir, apply=args.apply,
                         verbose=not args.quiet)
    mode = "applied" if args.apply else "dry-run"
    print(f"{mode}: scanned={stats['scanned']} "
          f"mismatched={stats['mismatched']} repaired={stats['repaired']} "
          f"skipped={stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
