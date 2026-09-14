"""Aggregator: merges papers from all fetchers, deduplicates by DOI (strict),
and filters out papers already seen in previous days."""

from __future__ import annotations
import json
import pathlib
from typing import Iterable

from render import identity as _identity


def _norm_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d


def _legacy_dedup_key(paper: dict) -> str:
    """Pre-ADR-0031 key; still honoured when reading an older seen-state."""
    doi = _norm_doi(paper.get("doi", ""))
    if doi:
        return f"doi:{doi}"
    return f"{paper['source']}:{paper.get('id', '')}"


def _dedup_key(paper: dict, aliases: dict | None = None) -> str:
    """Canonical work identity (ADR-0031), falling back to the legacy key."""
    return _identity.canonical_key(paper, aliases) or _legacy_dedup_key(paper)


def aggregate(
    paper_lists: Iterable[list[dict]],
    seen_state_path: pathlib.Path | None = None,
    force: bool = False,
    aliases: dict | None = None,
) -> tuple[list[dict], set[str]]:
    seen: set[str] = set()
    if seen_state_path and seen_state_path.exists() and not force:
        seen = set(json.loads(seen_state_path.read_text()).get("keys", []))

    keep: dict[str, dict] = {}
    new_keys = set()

    for plist in paper_lists:
        for p in plist:
            key = _dedup_key(p, aliases)
            # A seen-state written before ADR-0031 holds legacy keys; honour
            # both so the switch does not re-score the whole window once.
            if key in seen or _legacy_dedup_key(p) in seen:
                continue
            if key in keep:
                existing = keep[key]
                if (not existing.get("abstract")) and p.get("abstract"):
                    p.setdefault("also_seen_in", existing["source"])
                    keep[key] = p
                elif (existing["source"] == "arxiv"
                      and p["source"] in ("openalex", "pubmed")
                      and _norm_doi(p.get("doi", ""))):
                    # The published version (it has a DOI) supersedes the
                    # preprint record. A DOI-less OpenAlex copy of the same
                    # arXiv id does not: the arXiv record is richer.
                    p["also_seen_in"] = existing["source"]
                    keep[key] = p
                else:
                    existing.setdefault("also_seen_in", p["source"])
                continue
            keep[key] = p
            new_keys.add(key)

    return list(keep.values()), seen | new_keys


def save_state(seen_keys: set[str], state_path: pathlib.Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(seen_keys)
    if len(keys) > 50000:
        keys = keys[-50000:]
    state_path.write_text(json.dumps({"keys": keys}, ensure_ascii=False))
