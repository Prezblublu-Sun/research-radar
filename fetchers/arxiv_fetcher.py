"""arXiv fetcher: pulls papers in specified categories submitted in the last N days.
Uses the `arxiv` package which wraps the official arXiv API."""
from __future__ import annotations
import datetime as dt
import time
import arxiv


def fetch(categories: list[str], days_back: int = 1, max_results: int = 2000) -> list[dict]:
    """Returns a list of normalized paper dicts for papers in the given
    arxiv categories submitted within the last `days_back` days.

    Outer retry: if arxiv returns 429 (rate limit), wait 60/180 seconds
    between attempts (3 total). The arxiv package's internal num_retries
    only does ~10 second waits which arxiv often rejects.
    """
    if not categories:
        return []
    query = " OR ".join(f"cat:{c}" for c in categories)
    cutoff_date = dt.date.today() - dt.timedelta(days=days_back)

    wait_seconds = [0, 60, 180]
    last_error = None

    for attempt, wait in enumerate(wait_seconds, 1):
        if wait > 0:
            print(f"  arxiv attempt {attempt}/3 after {wait}s wait...")
            time.sleep(wait)
        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            client = arxiv.Client(page_size=100, delay_seconds=3, num_retries=3)
            out: list[dict] = []
            for result in client.results(search):
                if result.published.date() < cutoff_date:
                    break
                out.append(_normalize(result))
            return out
        except Exception as e:
            last_error = e
            err_str = str(e)
            if "429" in err_str or "HTTPError" in err_str:
                if attempt < len(wait_seconds):
                    print(f"  arxiv hit 429 on attempt {attempt}, will retry...")
                    continue
            else:
                raise

    raise RuntimeError(f"arxiv failed after {len(wait_seconds)} attempts: {last_error}")


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
