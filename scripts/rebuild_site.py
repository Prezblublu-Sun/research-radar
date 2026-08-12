"""Deterministically rebuild the static Research Radar site from local data.

This command only reads the corpus/configuration and writes generated site
artifacts.  It does not fetch papers, call an LLM, or update Zotero.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil

import yaml

from render import build_pages
from pipeline import weekly_report


ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_directions(path: pathlib.Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    directions = config.get("directions")
    if not isinstance(directions, dict) or not directions:
        raise ValueError(f"no directions mapping found in {path}")
    return directions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild static site pages and JSON indexes from local data."
    )
    parser.add_argument("--docs-dir", type=pathlib.Path,
                        default=ROOT / "docs")
    parser.add_argument("--data-dir", type=pathlib.Path,
                        default=ROOT / "data")
    parser.add_argument("--directions-yaml", type=pathlib.Path,
                        default=ROOT / "config" / "directions.yaml")
    parser.add_argument(
        "--sharded-daily", action="store_true",
        help=("write lightweight day shells and 20-card JSON shards; "
              "use for disposable Pages artifacts after source switching"),
    )
    args = parser.parse_args(argv)

    directions = load_directions(args.directions_yaml)
    build_pages.build(
        args.docs_dir, directions, data_dir=args.data_dir,
        sharded_daily=args.sharded_daily,
    )
    weekly_reports = []
    if args.sharded_daily:
        # A disposable Pages artifact must be complete when built from an
        # empty directory.  The legacy writer target already owns its weekly
        # archive, so a manual site rebuild must not gain an unrelated weekly
        # failure mode or rewrite those reports.
        weekly_reports = weekly_report.rebuild_all_weekly(
            data_dir=args.data_dir,
            output_dir=args.docs_dir / "weekly",
            directions_cfg=directions,
        )

    source_docs = ROOT / "docs"
    source_analytics = source_docs / "analytics"
    try:
        is_legacy_target = args.docs_dir.resolve() == source_docs.resolve()
    except OSError:
        is_legacy_target = False
    if not is_legacy_target and source_analytics.is_dir():
        shutil.copytree(
            source_analytics,
            args.docs_dir / "analytics",
            dirs_exist_ok=True,
        )

    args.docs_dir.mkdir(parents=True, exist_ok=True)
    (args.docs_dir / ".nojekyll").write_text("", encoding="utf-8")
    if args.sharded_daily:
        print(f"rebuilt weekly reports: {len(weekly_reports)}")
    print(f"rebuilt site: {args.docs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
