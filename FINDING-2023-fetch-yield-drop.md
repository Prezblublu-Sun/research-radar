# FINDING: per-day fetch yield dropped ~50% starting 2023

**Discovered**: 2026-05-23, during ADR-0018 Phase A analytics (distribution_yearly).
**Discovered by**: corpus analytics workstream (build_analytics.py A1).
**Owner for fix**: fetcher / data-acquisition workstream (the "研究雷达-2" line —
fetcher, backfill, run_historical). NOT the analytics workstream.

## Observation

distribution_yearly over the v3 corpus shows total paper count per year:

  year   bucket_files   papers
  2020      366         13186
  2021      365         13691
  2022      365         13714
  2023      363          5030   <-- ~63% drop vs 2022
  2024      366          5988
  2025      365          7425   <-- partial recovery
  2026      (partial year, expected low)

Bucket FILE counts are normal (~365/year = one per day, nothing missing).
The drop is in papers-PER-FILE, not missing days. So this is NOT a backfill
gap (no days skipped) — it is a systematic decline in how many papers were
fetched per day starting 2023.

## Why this matters

1. The distribution_yearly chart's absolute counts reflect what radar FETCHED,
   not what the field actually published. The 2023-2024 dip is a fetch artifact,
   not a real decline in field output. (priority-ratio chart, being a ratio, is
   not distorted by this and remains reliable.)

2. More importantly for the fetcher line: if ~half the per-day papers are
   missing for 2023+, radar may be MISSING large numbers of recent relevant
   papers — exactly the years the user cares most about. This is the same class
   of problem that motivated commit 17bd08a (broaden OpenAlex recall) after DOI
   verification found missing ground-truth papers.

## Candidate causes (for the fetcher workstream to investigate)

- OpenAlex/arXiv per-day recall behaving differently for 2023+ vs 2020-2022
  (API behavior, index coverage, or query-construction interaction by year).
- The 10-year refetch may have used the broadened fetcher (17bd08a) but still
  under-fetches recent years for some reason.
- Possible rate-limiting / pagination cap hit more often on denser recent days.

## Suggested next step (fetcher workstream)

Compare per-source (arxiv / openalex / pubmed) per-day yield for a sample of
2022 vs 2023 days to localize which source dropped. e.g.:

  for d in 2022-06-15 2023-06-15; do
    python3 -c "import json; c=json.load(open('data/daily/'+'$d'+'.json'))['counts']; print('$d', c.get('by_source'))"
  done

## Analytics-side action taken

Per decision (a): distribution_yearly.png/charts are rendered as-is but
annotated with a footnote stating counts reflect the fetched corpus, not
field output, and that per-day yield dropped ~2023 (fetcher behavior). No
attempt to correct or backfill from the analytics side — that is the fetcher
workstream's call.
