"""OpenAlex fetcher: pulls papers published in the last N days matching
concept IDs or keywords. Free API, no key required (polite pool via email)."""

from __future__ import annotations
import os
import datetime as dt
import requests

OPENALEX_BASE = "https://api.openalex.org/works"
POLITE_EMAIL = os.environ.get("OPENALEX_EMAIL", "your-email@ucl.ac.uk")


def _abstract_from_inverted_index(inv: dict | None) -> str:
    """OpenAlex returns abstracts as an inverted index. Reconstruct text."""
    if not inv:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def _build_filter(concepts: list[str], from_date: str) -> str:
    parts = [f"from_publication_date:{from_date}", "type:article"]
    if concepts:
        parts.append("concepts.id:" + "|".join(concepts))
    return ",".join(parts)


def fetch(
    concepts: list[str],
    keywords: list[str],
    days_back: int = 1,
    per_page: int = 50,
    max_pages: int = 4,
) -> list[dict]:
    """Returns a list of normalized paper dicts."""
    from_date = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
    flt = _build_filter(concepts, from_date)
    search_query = " OR ".join(f'"{k}"' for k in keywords) if keywords else None

    results: list[dict] = []
    cursor = "*"
    for _ in range(max_pages):
        params = {
            "filter": flt,
            "per-page": per_page,
            "cursor": cursor,
            "mailto": POLITE_EMAIL,
        }
        if search_query:
            params["search"] = search_query

        r = requests.get(OPENALEX_BASE, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for work in data.get("results", []):
            results.append(_normalize(work))

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

    return results


def _normalize(work: dict) -> dict:
    doi = work.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    authors = [
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
    ]

    concepts = [
        c.get("display_name", "")
        for c in work.get("concepts", [])
        if c.get("score", 0) > 0.3
    ]

    venue = (work.get("primary_location") or {}).get("source") or {}

    return {
        "source": "openalex",
        "id": work.get("id", ""),
        "doi": doi,
        "title": work.get("title", "") or "",
        "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")),
        "authors": authors,
        "venue": venue.get("display_name", ""),
        "year": work.get("publication_year"),
        "date": work.get("publication_date", ""),
        "url": work.get("doi") or work.get("id", ""),
        "cited_by_count": work.get("cited_by_count", 0),
        "concepts": concepts,
        "categories": [],
        "raw_type": work.get("type", ""),
    }


if __name__ == "__main__":
    sample = fetch(
        concepts=[],
        keywords=["bioprinting", "bioink"],
        days_back=7,
    )
    print(f"Fetched {len(sample)} papers")
    for p in sample[:3]:
        print(f"  - {p['title'][:80]}  [{p['doi']}]")
