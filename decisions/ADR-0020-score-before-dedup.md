# ADR-0020: Score-before-dedup waste — pre-filter corpus duplicates before LLM scoring

**Status**: Proposed (2026-05-23)
**Related**: ADR-0015 (v2 daily buckets, first-seen-wins on identity_key),
ADR-0017 (scorer resilience), ADR-0019 (scorer throughput / concurrency)

## Context

The 10-year refetch surfaced a measurable, avoidable LLM cost. Over the
full run, pipeline.run_historical scored 86351 papers but only wrote
67581 as new — **18770 papers (22%) were scored and then discarded**
because they already existed in the corpus.

Cause: run_historical scores BEFORE deduplicating against the corpus.

  - line ~274  routed = filter_routed(papers)        # keyword filter
  - line ~284  scored = score_batch(routed, ...)      # scores ALL routed
  - line ~318  load_existing_v2(target); first-seen-wins skips on write

The within-run dedup (line ~256, against _dedup_key + dois_seen) only
prevents re-scoring the same paper twice WITHIN one run. It does not
check what is already on disk. So every paper already in the corpus from
a prior run/backfill/daily-cron gets re-scored, then dropped at write
time by first-seen-wins.

Real cost of the 18770 wasted calls (DeepSeek deepseek-v4-flash, billing
data 2026-05): output ~650 tok/call x 18770 x CNY2/M ~= CNY24; input-miss
~300 tok/call x 18770 x CNY1/M ~= CNY6. About **CNY30 per large backfill**,
plus the wall-clock time of ~19k needless LLM calls.

## Decision

Filter routed papers against the corpus BEFORE calling score_batch.

Insert between filter_routed (line ~274) and score_batch (line ~284):

  - Group routed papers by bucket date (paper["date"]).
  - For each bucket, load the existing daily file once
    (v2.load_existing_v2) and build the set of existing identity_keys.
  - Drop any routed paper whose v2.identity_key is already present.
  - Score only the survivors ("novel" papers).

Critical key-function constraint: pre-dedup MUST use **v2.identity_key**,
the same function used at write time (line ~324) and by the corpus. It
must NOT use run_historical._dedup_key, which differs in two ways:
(a) _dedup_key lowercases the DOI, identity_key does not; (b) _dedup_key
has an id:<pid> fallback, identity_key returns "" when there is no
doi/arxiv. Using identity_key on both sides keeps pre-dedup consistent
with what first-seen-wins will actually compare on write.

first-seen-wins at write time is RETAINED unchanged as a safety net (for
in-run races, year-precision bucket reshuffling, and any paper with no
identity_key that pre-dedup cannot key on). Pre-dedup is a cost
optimization layered in front of it, not a replacement.

dry_run is unaffected: dry_run does not write to disk and is used for
pure fetch/route statistics, so it skips both scoring and pre-dedup
(keeps reporting after_routing as the full routed count).

Papers with empty identity_key (no DOI, no arxiv_id) cannot be
corpus-deduped and fall through to scoring exactly as today.

## Semantic contract change

After this change, **run_historical will never re-score a paper already
in the corpus.** Its job becomes strictly "fetch + score papers NEW to
the corpus."

Re-scoring existing papers (e.g. after a scorer prompt upgrade) is NOT
run_historical's responsibility — that is what scripts/rescore_silent.py
exists for. This is an intentional separation of concerns:
  - run_historical: add papers not yet in the corpus.
  - rescore_silent: re-score papers already in the corpus.

If a future need arises to force re-scoring via the historical path, it
should be an explicit opt-in flag (e.g. --rescore-existing) that bypasses
pre-dedup; not the default. Not implemented now (YAGNI).

## New per-month counter

Add skipped_existing to the month summary counts (number of routed
papers dropped by pre-dedup), so the savings are observable in
_progress.json and logs, mirroring how missing_date is surfaced today.
Log line suggestion:
  -> N routed, M already in corpus (skipped), K scored

## Consequences

  - ~22% fewer LLM calls on large backfills (one-time and recurring),
    ~CNY30 saved per 10-year-scale run, proportional savings on smaller
    backfills.
  - Daily cron benefits too: papers re-surfaced within the 14-day
    OpenAlex lookback that are already stored get skipped before scoring
    rather than scored-then-discarded.
  - Extra disk reads: one load_existing_v2 per distinct bucket date in
    the routed set. Buckets are already loaded at write time, so this is
    a second read per bucket per month — cheap relative to an LLM call.
  - Output token volume per genuinely-new paper is unchanged (bilingual
    summaries retained — out of scope here; see ADR-0019 deferred
    follow-up for a possible zh-only scorer_v4).

## Out of scope

  - Reducing per-call output tokens (zh-only scorer_v4). Deliberately not
    touched: the user opted to keep bilingual output and address only the
    dedup waste.
  - The identity_key DOI case-sensitivity asymmetry: the corpus may hold
    case-variant duplicate DOIs, and pre-dedup keyed on identity_key will
    not collapse them, so a small number of case-variant re-scores may
    persist. The user has explicitly accepted this minor residual waste;
    it is not addressed here.

## Testing

  - A routed paper whose identity_key is already in the target bucket is
    dropped before scoring (score_batch called with the novel subset
    only — assert via a spy/mock on score_batch).
  - A routed paper not in the corpus is scored and written as today.
  - A routed paper with empty identity_key (no doi/arxiv) is always
    scored (cannot be deduped).
  - dry_run path does not pre-dedup and does not call score_batch.
  - skipped_existing count is correct and surfaced in the returned
    month-summary dict.
  - first-seen-wins at write time still drops a duplicate that slips
    through (e.g. two papers with same key in the same novel batch).
