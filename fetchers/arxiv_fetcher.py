"""arXiv fetcher: pulls papers in specified categories submitted in the last N days.
Uses the `arxiv` package which wraps the official arXiv API."""

from __future__ import annotations
import datetime as dt
import arxiv


def fetch(categories: list[str], days_back: int = 1, max_results: int = 500) -> list[dict]:
    """Returns a list of normalized paper dicts for papers in the given
    arxiv categories submitted within the last `days_back` days."""
    if not categories:
        return []

    query = " OR ".join(f"cat:{c}" for c in categories)
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    # cutoff is a DATE, not a timestamp: include all papers from
    # (today - days_back) onwards. This is more intuitive than "last N*24 hours".
    cutoff_date = dt.date.today() - dt.timedelta(days=days_back)
    client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)

    out: list[dict] = []
    for result in client.results(search):
        if result.published.date() < cutoff_date:
            break
        out.append(_normalize(result))
    return out


def _normalize(r) -> dict:
    """Map arxiv.Result to our unified schema."""
    doi = r.doi or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    return {
        "source": "arxiv",
        "id": r.entry_id,
        "doi": doi,
        "arxiv_id": r.entry_id.rsplit("/", 1)[-1],
        "title": r.title.replace("\n", " ").strip(),
        "abstract": r.summary.replace("\n", " ").strip(),
        "authors": [a.name for a in r.authors],
        "venue": "arXiv preprint",
        "year": r.published.year,
        "date": r.published.date().isoformat(),
        "url": r.entry_id,
        "cited_by_count": 0,
        "concepts": [],
        "categories": [c for c in r.categories],
        "raw_type": "preprint",
    }


if __name__ == "__main__":
    sample = fetch(["cs.LG", "cs.CV"], days_back=1, max_results=20)
    print(f"Fetched {len(sample)} papers")
    for p in sample[:3]:
        print(f"  - {p['title'][:80]}  [{p['arxiv_id']}]")
