# ADR-0023: OpenAlex backfill silent-zero — root cause of low recall

**Status**: Accepted — root cause confirmed; fix pending (2026-05-24)
**Related**: ADR-0020 (score-before-dedup), openalex_fetcher fan-out,
run_historical, the femoral-stem DOI-verify recall investigation
(2026-05-19 .. 2026-05-24)

## Context — the symptom

The DOI verifier showed low recall on femoral-stem ground-truth must_read
papers. The 10-year refetch (2026-05-20..23, +68k papers -> 103k corpus)
barely moved it (21% -> 26%, +1 paper). Three hypotheses were tested and
the first two falsified:

  1. "Router too strict" — FALSIFIED. Live-testing route() on the 4 missing
     must_reads showed the router PASSES 3 of 4 (only one has too-weak an
     abstract). Not the cause.
  2. "Fetcher pagination truncation (>2000/query)" — MOSTLY FALSIFIED. The
     target papers' concept months were 1765 / 219 / 2321; only one slightly
     exceeds the 40-page x 50 = 2000 cap. And re-running the fetcher today
     (OpenAlex recovered to HTTP 200) returned ALL THREE target papers in the
     concept-only query results. The fetcher logic is correct.
  3. "OpenAlex source silently failed during backfill" — CONFIRMED below.

## Root cause (confirmed by progress.json by_source counts)

data/historical/_progress.json records per-month by_source counts. For the
target months:

    2024-04: openalex 0 (arxiv 6691, pubmed 168) — status "complete"
    2024-05: openalex 0 (arxiv 7703, pubmed 156) — status "complete"
    2025-03: openalex 0 (arxiv 9556, pubmed 195) — status "complete"

Across all 137 backfilled months, 47 have openalex=0 — and they are almost
all the RECENT ones: 2022-12 through 2026-05 is a near-continuous run of
zeros (plus a few scattered earlier: 2017-06, 2018-09/10, 2019-02/03).
Early months (2015..2022) mostly have ~3000 OpenAlex papers/month.

Mechanism (run_historical.py ~line 229-240):

    if openalex terms:
        try:
            r = openalex_fetcher.fetch(...)
            by_source["openalex"] = len(r)
        except Exception as e:
            log(f"  ! openalex fetch failed: {e}")   # swallowed
        # no raise, no retry, no incomplete-marking

When the backfill exhausted OpenAlex's free-tier daily budget partway
through (it processes many months per run), every subsequent month's
OpenAlex query hit HTTP 429. openalex_fetcher._fetch_one calls
r.raise_for_status(), which raises; run_historical catches it, logs one
line, leaves by_source["openalex"]=0, and STILL marks the month complete.
So ~3.5 years of OpenAlex data silently never landed, with no error
surfaced and no resume flag.

## Why this destroyed recall

OpenAlex is the only source covering published journal articles (MDPI,
Nature, Elsevier, Springer, etc.); arxiv is preprints, pubmed is a narrow
keyword slice. The user's ground-truth must_reads are mostly recent (2024-
2025) journal papers — exactly the OpenAlex-only records in the 47 zero
months. The corpus has 103k papers but is heavily arxiv preprints for the
last 3.5 years, missing the journal literature the user actually cites.

This also explains why the refetch did not help: during 2026-05-20..23 the
OpenAlex budget was again exhausted (429 all session), so the refetch's
OpenAlex source was also ~0 for the recent months.

## Decision — fix in two parts

### Part 1 — Code hardening (MUST precede any re-run)

a) openalex_fetcher._fetch_one: on HTTP 429 / 5xx, RETRY with exponential
   backoff (respect Retry-After if present) instead of letting
   raise_for_status abort the whole month. Cap retries; on final failure,
   raise a typed error the caller can distinguish from "0 results".

b) run_historical: do NOT mark a month complete when an expected source
   ERRORED. Distinguish "source returned 0" from "source raised". On a
   source error, mark the month status="incomplete" (or
   "partial:openalex") with the error, so a resume pass re-runs only those
   months. Optionally fail loudly if a normally-populated source returns 0.

c) Politeness/rate: pace OpenAlex requests to stay under the free-tier
   budget (mailto already set; add inter-request sleep and/or detect the
   daily-limit response and pause rather than hammering into 429s).

### Part 2 — Data repair (after Part 1)

Re-run the 47 openalex=0 months (concentrated in 2022-12..2026-05) now that
OpenAlex is reachable. first-seen-wins means existing arxiv/pubmed papers
are untouched; only the missing OpenAlex journal papers get added.
Sequence the re-run to respect the budget (batch by a few months, or run
across days) so it does not re-trigger the silent-zero failure — which Part
1(a/b) will now surface and retry rather than swallow.

The 47 months:
  2017-06, 2018-09, 2018-10, 2019-02, 2019-03,
  2022-12, 2023-01..2023-12 (all), 2024-01..2024-12 (all),
  2025-01..2025-12 (all), 2026-01..2026-05 (all)

## Consequences

  - Recall should rise substantially once the recent-year OpenAlex journal
    papers are present (the ground-truth must_reads live there).
  - Re-running 47 months costs LLM scoring tokens for the genuinely new
    OpenAlex papers (arxiv/pubmed already in corpus are skipped by
    score-before-dedup, ADR-0020). Estimate before running (per-month
    OpenAlex ~1500-3000 raw -> routed subset -> scored).
  - The hardening prevents the failure mode recurring and makes "month
    complete" trustworthy.

## Lessons

  - The progress.json by_source counts recorded openalex:0 from day one;
    reading them first would have located this immediately instead of after
    three wrong hypotheses (router, pagination, generic fetch-interrupt).
    "Inspect the data you already have before forming hypotheses."
  - A pipeline that catches an exception, logs it, and still reports success
    is worse than one that fails — the silent success hid a 3.5-year data
    hole behind a 103k-paper count that looked healthy.
