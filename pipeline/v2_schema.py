"""ADR-0015 v2 schema helpers shared by daily and historical producers.

Single source of truth for the field/file conventions the v2 corpus relies on.
`pipeline.run_daily` and `pipeline.run_historical` both import from here; the
one-off `scripts/migrate_to_schema_v2.py` keeps its own internal copies so
that script stays import-light.

Identity-key format and date_precision rules must stay aligned with
ADR-0015 §4.4 and §5.2; if you change one of these helpers, also check the
migration script for drift.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re


def identity_key(paper: dict) -> str:
    """ADR-0015 §4.4 dedup key: `doi:<doi>` or `arxiv:<arxiv_id>` or ''."""
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"doi:{doi}"
    arxiv = (paper.get("arxiv_id") or "").strip()
    if arxiv:
        return f"arxiv:{arxiv}"
    return ""


def infer_date_precision(date_str: str) -> str:
    """ADR-0015 §5.2: '*-01-01' -> year, '*-01' -> month, otherwise day.

    Empty/None gets treated as 'year' (matches migration-script behavior for
    fully-missing date fields).
    """
    if not date_str:
        return "year"
    if date_str.endswith("-01-01"):
        return "year"
    if date_str.endswith("-01"):
        return "month"
    return "day"


def atomic_write_json(path: pathlib.Path, data) -> None:
    """Write JSON to `<path>.tmp` then `os.replace` — atomic on POSIX.

    Used by both producers so a crash mid-write can never leave a daily
    bucket file half-overwritten (the 2026-05-12 incident class).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def load_existing_v2(path: pathlib.Path) -> tuple[list[dict], dict]:
    """Return (papers, meta) for an existing v2 bucket file.

    Returns ([], {}) if the file is absent or unreadable. Tolerates a stray
    v1 list-of-papers shape for any file that predates migration.
    """
    if not path.exists():
        return [], {}
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


def build_v2_counts(papers: list[dict]) -> dict:
    """Reconstruct a counts dict from a v2 bucket's papers.

    Every paper in a v2 bucket is post-dedup + post-routing by construction,
    so fetched_total == after_dedup == after_routing.
    """
    by_source: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    scored = 0
    for p in papers:
        src = p.get("source", "")
        by_source[src] = by_source.get(src, 0) + 1
        d = p.get("direction") or p.get("direction_name")
        if d:
            by_direction[d] = by_direction.get(d, 0) + 1
        llm = p.get("llm")
        if isinstance(llm, dict):
            scored += 1
            pr = llm.get("priority")
            if pr:
                priority_counts[pr] = priority_counts.get(pr, 0) + 1
    return {
        "fetched_total": len(papers),
        "by_source": by_source,
        "after_dedup": len(papers),
        "after_routing": len(papers),
        "by_direction": by_direction,
        "routed_by_source": dict(by_source),
        "scored": scored,
        "priority_counts": priority_counts if priority_counts else None,
    }


def build_v2_file(date_str: str, papers: list[dict]) -> dict:
    """Wrap a list of papers as the v2 bucket file dict (ADR-0015 §4.5)."""
    return {
        "schema_version": "v2",
        "date": date_str,
        "date_precision": infer_date_precision(date_str),
        "papers": papers,
        "counts": build_v2_counts(papers),
    }


def utc_now_iso() -> str:
    """Seconds-precision ISO 8601 UTC timestamp with Zulu suffix."""
    return (dt.datetime.now(dt.timezone.utc)
              .isoformat(timespec="seconds")
              .replace("+00:00", "Z"))


_SCORER_RX = re.compile(r"^scorer_(v\d+)\.txt$")


def scorer_version_from_active_prompt() -> str:
    """Parse `pipeline.llm_scorer.ACTIVE_PROMPT_FILE` into a `vN` tag.

    Returns 'unknown' if the filename doesn't match `scorer_vN.txt`.
    Imported lazily so v2_schema stays cheap to import in scripts that
    don't otherwise pull in the OpenAI client constructed at llm_scorer
    import time.
    """
    from pipeline import llm_scorer
    m = _SCORER_RX.match(llm_scorer.ACTIVE_PROMPT_FILE or "")
    return m.group(1) if m else "unknown"
