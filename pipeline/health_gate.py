"""Exit non-zero when a persisted run needs operator attention."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent


def evaluate(manifest: dict) -> list[str]:
    reasons: list[str] = []
    status = manifest.get("run_status")
    if status != "success":
        reasons.append(f"run_status={status or 'missing'}")
    for flag in manifest.get("quality_flags") or []:
        if flag == "scorer_failed" or flag.endswith("_failed"):
            reasons.append(flag)
    return list(dict.fromkeys(reasons))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument(
        "--manifests-dir", type=pathlib.Path,
        default=ROOT / "data" / "manifests",
    )
    args = parser.parse_args(argv)
    path = args.manifests_dir / f"{args.date}.json"
    if not path.exists():
        print(f"::error::run manifest is missing: {path}")
        return 1
    manifest = json.loads(path.read_text(encoding="utf-8"))
    reasons = evaluate(manifest)
    if reasons:
        print("::error::daily run persisted with health problems: "
              + ", ".join(reasons))
        return 1
    print("daily run health gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
