"""Run manifest: captures git commit, config hashes, package versions, LLM model,
and processing counts so any past day can be reproduced or explained."""

from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
from importlib import metadata


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _file_hash(path: pathlib.Path) -> str:
    if not path.exists():
        return "sha256:missing"
    return _sha256(path.read_text(encoding="utf-8"))


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return os.environ.get("GITHUB_SHA", "")[:7] or "unknown"


def _pkg_version(name: str) -> str:
    try:
        return metadata.version(name)
    except Exception:
        return "unknown"


def build_manifest(
    *,
    config_path: pathlib.Path,
    prompt_path: pathlib.Path,
    sources_used: dict,
    counts: dict,
    llm_responses: list[dict] | None = None,
    run_status: str = "success",
    quality_flags: list[str] | None = None,
) -> dict:
    snapshot = ""
    if llm_responses:
        for r in llm_responses:
            if r.get("_raw_model"):
                snapshot = r["_raw_model"]
                break

    return {
        "run_id": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "run_status": run_status,
        "quality_flags": quality_flags or [],
        "config": {
            "directions_yaml": _file_hash(config_path),
            "scorer_prompt": _file_hash(prompt_path),
            "scorer_prompt_file": prompt_path.name,
        },
        "llm": {
            "model_alias": os.environ.get("MODEL_NAME", "deepseek-v4-flash"),
            "model_snapshot_observed": snapshot,
            "base_url": os.environ.get("OPENAI_BASE_URL", ""),
            "temperature": float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        },
        "packages": {
            "arxiv":   _pkg_version("arxiv"),
            "openai":  _pkg_version("openai"),
            "pyzotero": _pkg_version("pyzotero"),
            "requests": _pkg_version("requests"),
            "PyYAML":  _pkg_version("PyYAML"),
        },
        "sources_used": sources_used,
        "counts": counts,
    }


def save_manifest(manifest: dict, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def check_config_changed(
    config_path: pathlib.Path,
    last_manifest_path: pathlib.Path | None,
) -> tuple[bool, str, str]:
    new_hash = _file_hash(config_path)
    if not last_manifest_path or not last_manifest_path.exists():
        return True, "sha256:none", new_hash
    try:
        old = json.loads(last_manifest_path.read_text())
        old_hash = old.get("config", {}).get("directions_yaml", "sha256:none")
        return old_hash != new_hash, old_hash, new_hash
    except Exception:
        return True, "sha256:unreadable", new_hash


def find_last_manifest(data_dir: pathlib.Path, before_date: str) -> pathlib.Path | None:
    manifests = sorted(data_dir.glob("manifests/*.json"))
    manifests = [m for m in manifests if m.stem < before_date]
    return manifests[-1] if manifests else None
