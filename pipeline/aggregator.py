"""Aggregator: merges papers from all fetchers, deduplicates by DOI (strict),
and filters out papers already seen in previous days."""

from __future__ import annotations
import json
import pathlib
from typing import Iterable


def _norm_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d


def _dedup_key(paper: dict) -> str:
    doi = _norm_doi(paper.get("doi", ""))
    if doi:
        return f"doi:{doi}"
    return f"{paper['source']}:{paper.get('id', '')}"


def aggregate(
    paper_lists: Iterable[list[dict]],
    seen_state_path: pathlib.Path | None = None,
    force: bool = False,
) -> tuple[list[dict], set[str]]:
    seen: set[str] = set()
    if seen_state_path and seen_state_path.exists() and not force:
        seen = set(json.loads(seen_state_path.read_text()).get("keys", []))

    keep: dict[str, dict] = {}
    new_keys = set()

    for plist in paper_lists:
        for p in plist:
            key = _dedup_key(p)
            if key in seen:
                continue
            if key in keep:
                existing = keep[key]
                if (not existing.get("abstract")) and p.get("abstract"):
                    keep[key] = p
                elif existing["source"] == "arxiv" and p["source"] in ("openalex", "pubmed"):
                    p["also_seen_in"] = existing["source"]
                    keep[key] = p
                continue
            keep[key] = p
            new_keys.add(key)

    return list(keep.values()), seen | new_keys


# Upper bound on remembered dedup keys (ADR-0030). The corpus is ~108k
# works; the old cap (50k) sliced a *set*, so which keys survived each save
# was arbitrary and already-scored papers could be re-fetched and re-scored.
# Keys are now kept in first-seen order and the oldest are dropped first.
MAX_SEEN_KEYS = 150_000


def save_state(seen_keys: set[str], state_path: pathlib.Path) -> None:
    """Persist the dedup state, preserving first-seen order.

    Keys already in the file keep their position; keys new to this run are
    appended (sorted, for determinism). Keys previously on disk are never
    dropped by a run that did not see them, so a ``--force`` run no longer
    wipes the history it bypassed.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    previous: list[str] = []
    if state_path.exists():
        try:
            loaded = json.loads(state_path.read_text(encoding="utf-8")).get("keys", [])
            previous = [k for k in loaded if isinstance(k, str)]
        except (json.JSONDecodeError, OSError, AttributeError):
            previous = []
    known = set(previous)
    ordered = list(previous)
    ordered.extend(sorted(k for k in set(seen_keys) if k not in known))
    if len(ordered) > MAX_SEEN_KEYS:
        ordered = ordered[-MAX_SEEN_KEYS:]
    state_path.write_text(json.dumps({"keys": ordered}, ensure_ascii=False),
                          encoding="utf-8")
