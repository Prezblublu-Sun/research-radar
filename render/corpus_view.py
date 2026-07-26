"""Canonical, read-only corpus view used by the public site renderer.

The persisted ``data/daily`` buckets are an append-only evidence layer. A
small number of papers occur in more than one publication-date bucket because
different sources supplied different dates during historical migrations. We
keep those source records intact, but public aggregate views must obey the v2
identity contract: one DOI/arXiv identity, one visible paper.

This module deliberately has no dependency on ``pipeline`` so the render layer
remains stdlib-only and can be imported in lightweight tests and rebuilds.
"""

from __future__ import annotations

from dataclasses import dataclass


PRIORITIES = ("High", "Medium", "Low", "Exclude")


def identity_key(paper: dict) -> str:
    """Return the strict ADR-0015 identity key, or ``""`` when unavailable."""
    doi = (paper.get("doi") or "").strip()
    if doi:
        return f"doi:{doi}"
    arxiv = (paper.get("arxiv_id") or "").strip()
    if arxiv:
        return f"arxiv:{arxiv}"
    return ""


def priority_counts(papers: list[dict]) -> dict[str, int]:
    """Recompute visible priority counts from paper records."""
    counts = {priority: 0 for priority in PRIORITIES}
    for paper in papers:
        llm = paper.get("llm") or {}
        if llm.get("scorer_failed") is True:
            counts["Unscored"] = counts.get("Unscored", 0) + 1
            continue
        priority = llm.get("priority")
        if priority:
            counts[priority] = counts.get(priority, 0) + 1
    return counts


@dataclass(frozen=True)
class CorpusStats:
    raw_total: int
    unique_total: int
    duplicates_suppressed: int
    priority_counts: dict[str, int]

    def as_dict(self) -> dict:
        return {
            "raw_total": self.raw_total,
            "unique_total": self.unique_total,
            "duplicates_suppressed": self.duplicates_suppressed,
            "priority_counts": dict(self.priority_counts),
        }


def _canonical_rank(bucket_date: str, paper: dict, position: int) -> tuple:
    """Stable first-seen-wins rank for duplicate identity records.

    Migrated legacy records may not carry ``first_seen_at``. Treat them as
    predating timestamped records, then use publication bucket, source and
    original position only as deterministic tie-breakers. No title similarity
    or other fuzzy criterion is ever used.
    """
    first_seen = (paper.get("first_seen_at") or "").strip()
    return (
        0 if not first_seen else 1,
        first_seen,
        bucket_date,
        str(paper.get("source") or ""),
        position,
    )


def canonicalize_buckets(
    buckets: dict[str, list[dict]],
) -> tuple[dict[str, list[dict]], CorpusStats]:
    """Return per-date papers with duplicate identities suppressed.

    Papers without a DOI/arXiv identity are retained independently. This is
    important: the project explicitly forbids fuzzy deduplication, so an
    identity-less record must never be merged by title or date.
    """
    winners: dict[str, tuple[tuple, str, int]] = {}
    raw_total = 0

    for bucket_date in sorted(buckets):
        for position, paper in enumerate(buckets[bucket_date]):
            if not isinstance(paper, dict):
                continue
            raw_total += 1
            key = identity_key(paper)
            if not key:
                continue
            candidate = (_canonical_rank(bucket_date, paper, position),
                         bucket_date, position)
            current = winners.get(key)
            if current is None or candidate[0] < current[0]:
                winners[key] = candidate

    visible: dict[str, list[dict]] = {date: [] for date in buckets}
    visible_total = 0
    for bucket_date in sorted(buckets):
        for position, paper in enumerate(buckets[bucket_date]):
            if not isinstance(paper, dict):
                continue
            key = identity_key(paper)
            if key:
                winner = winners[key]
                if (bucket_date, position) != (winner[1], winner[2]):
                    continue
            visible[bucket_date].append(paper)
            visible_total += 1

    all_visible = [paper for papers in visible.values() for paper in papers]
    stats = CorpusStats(
        raw_total=raw_total,
        unique_total=visible_total,
        duplicates_suppressed=raw_total - visible_total,
        priority_counts=priority_counts(all_visible),
    )
    return visible, stats
