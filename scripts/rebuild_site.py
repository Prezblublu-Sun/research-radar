"""Deterministically rebuild the static Research Radar site from local data.

This command only reads the corpus/configuration and writes generated site
artifacts.  It does not fetch papers, call an LLM, or update Zotero.
"""

from __future__ import annotations

import argparse
import pathlib

import yaml

from render import build_pages


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
    args = parser.parse_args(argv)

    directions = load_directions(args.directions_yaml)
    build_pages.build(args.docs_dir, directions, data_dir=args.data_dir)
    print(f"rebuilt site: {args.docs_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
