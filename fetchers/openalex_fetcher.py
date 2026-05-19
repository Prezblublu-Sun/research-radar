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


def _build_filter(concepts: list[str], from_date: str,
                  to_date: str | None = None) -> str:
    parts = [f"from_publication_date:{from_date}", "type:article|review"]
    if to_date:
        parts.append(f"to_publication_date:{to_date}")
    if concepts:
        parts.append("concepts.id:" + "|".join(concepts))
    return ",".join(parts)


def _fetch_one(flt: str, search_query: str | None, per_page: int,
               max_pages: int) -> list[dict]:
    """One cursor-paginated OpenAlex query → list of normalised paper dicts.

    Extracted so the AND→OR dispatch in :func:`fetch` can issue two
    independent queries and union their results without duplicating the
    pagination loop.
    """
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


def fetch(
    concepts: list[str],
    keywords: list[str],
    days_back: int = 1,
    per_page: int = 50,
    max_pages: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Returns a list of normalized paper dicts.

    Two modes:
      - Daily (default): from_date computed from `days_back`, no upper
        bound. Default `max_pages` is 4 (~200 papers/day).
      - Historical (when both from_date and to_date are set as 'YYYY-MM-DD'):
        both bounds passed to the OpenAlex filter. Default `max_pages` is
        bumped to 40 internally (~2000 papers/month).

    Dispatch — changed from AND to OR semantics on 2026-05-19 after the
    DOI verifier surfaced 4 must_read papers that were concept-relevant
    but slipped past the narrow ``concepts.id`` clause when combined with
    ``search=``:

      - concepts AND keywords (the normal direction config): issue TWO
        queries — query A = concept-filter only, query B = search-only
        on the OR-joined keyword string — then union the result lists and
        deduplicate by OpenAlex paper id. Result counts may roughly
        double for directions that supply both signals.
      - concepts only OR keywords only: the original single-query path
        (preserves behaviour for direction configs that intentionally
        provide just one signal).

    Cursor pagination, per_page, polite mailto, daily/historical mode
    selection, and `max_pages` semantics are unchanged — each query in
    the fan-out is capped at `effective_max_pages` independently.
    Callers may always override `max_pages` explicitly.
    """
    historical = bool(from_date and to_date)
    if historical:
        effective_from = from_date
        effective_to = to_date
        effective_max_pages = max_pages if max_pages is not None else 40
    else:
        effective_from = (dt.date.today() - dt.timedelta(days=days_back)).isoformat()
        effective_to = None
        effective_max_pages = max_pages if max_pages is not None else 4

    has_concepts = bool(concepts)
    has_keywords = bool(keywords)

    if has_concepts and has_keywords:
        # Two-query fan-out: recover papers that match concepts XOR keywords.
        flt_concepts = _build_filter(concepts, effective_from, effective_to)
        flt_no_concepts = _build_filter([], effective_from, effective_to)
        search_query = " OR ".join(f'"{k}"' for k in keywords)
        rows_a = _fetch_one(flt_concepts, None, per_page, effective_max_pages)
        rows_b = _fetch_one(flt_no_concepts, search_query, per_page, effective_max_pages)
        # Union with stable A-first ordering, dedup by OpenAlex work id.
        seen: set[str] = set()
        merged: list[dict] = []
        for r in rows_a + rows_b:
            rid = r.get("id") or ""
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            merged.append(r)
        return merged

    # Single-query path (keywords-only or concepts-only) — unchanged.
    flt = _build_filter(concepts, effective_from, effective_to)
    search_query = " OR ".join(f'"{k}"' for k in keywords) if has_keywords else None
    return _fetch_one(flt, search_query, per_page, effective_max_pages)


def _normalize(work: dict) -> dict:
    doi = work.get("doi") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    # Extract author names + first author affiliation + corresponding author info
    authorships = work.get("authorships", [])
    authors = [a.get("author", {}).get("display_name", "") for a in authorships]

    def _aff(a: dict) -> str:
        """Best-effort affiliation string: prefer raw, fallback to first institution."""
        raw = a.get("raw_affiliation_strings") or []
        if raw:
            return raw[0]
        insts = a.get("institutions") or []
        if insts:
            return insts[0].get("display_name", "")
        return ""

    first_author_affiliation = _aff(authorships[0]) if authorships else ""

    # Corresponding authors (may be multiple, may be the first author)
    corresponding = [
        {
            "name": a.get("author", {}).get("display_name", ""),
            "affiliation": _aff(a),
        }
        for a in authorships if a.get("is_corresponding")
    ]

    concepts = [
        c.get("display_name", "")
        for c in work.get("concepts", [])
        if c.get("score", 0) > 0.3
    ]

    venue = (work.get("primary_location") or {}).get("source") or {}

    # ADR-0015 §4.1: OpenAlex always emits publication_date as YYYY-MM-DD,
    # even when the source record is month-only or year-only. Infer precision
    # heuristically from the trailing suffix.
    raw_date = work.get("publication_date", "") or ""
    if not raw_date:
        date_str, date_precision = "", "year"
    elif raw_date.endswith("-01-01"):
        date_str, date_precision = raw_date, "year"
    elif raw_date.endswith("-01"):
        date_str, date_precision = raw_date, "month"
    else:
        date_str, date_precision = raw_date, "day"

    return {
        "source": "openalex",
        "id": work.get("id", ""),
        "doi": doi,
        "title": work.get("title", "") or "",
        "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")),
        "authors": authors,
        "first_author_affiliation": first_author_affiliation,
        "corresponding_authors": corresponding,
        "venue": venue.get("display_name", ""),
        "year": work.get("publication_year"),
        "date": date_str,
        "date_precision": date_precision,
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
