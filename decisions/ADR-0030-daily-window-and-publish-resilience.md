# ADR-0030: Daily fetch windows, page caps, and publish resilience

**Status**: Accepted (2026-09-14)
**Related**: ADR-0013 (source asymmetry), ADR-0023 (OpenAlex silent zero),
ADR-0028 (Pages artifact), FINDING-2023-fetch-yield-drop.md,
CLAUDE.md §1 (recall, not precision), §4 (data-integrity guardrails)

## Context — what the manifests showed

An audit of the 119 daily manifests (2026-05-12 .. 2026-09-13) and the live
OpenAlex API on 2026-09-14 surfaced five independent recall / reliability
leaks. None of them is a scorer problem; all sit in fetch, publish, or state.

1. **OpenAlex returned its page cap every day.** Daily mode used
   `max_pages=4 x per_page=100` per query, two queries → ≤ 800 works. Every
   run since 2026-07-27 reported 771–789 OpenAlex works, weekday or weekend.
   The 14-day window it queries actually held **3,679** works for the concept
   query and **3,905** for the keyword query (live `meta.count`). Without an
   explicit sort the same top-400 came back each day; `after_dedup` on
   2026-09-13 was 286 of 790 for exactly that reason. The remaining ~90 % of
   the window was never fetched. This is the most likely mechanism behind
   the 2023+ per-day yield drop recorded in FINDING-2023 and behind 7 of the
   15 in-window must-read papers that never entered the corpus in the
   2026-05-23 femoral-stem ground-truth check.
2. **arXiv never fetched Fri–Sun submissions.** `days_back=1` filters on the
   v1 submission date, but a submission only becomes visible once announced
   (20:00 ET, Sun–Thu; submissions after the 14:00 ET cutoff wait an extra
   day, weekends wait until Monday night). By the time a weekend submission
   is visible the 1-day window has moved past it. Manifests confirm it:
   `arxiv_returned_zero` fired on 46 of 48 Sat/Sun/Mon runs and on 1 of 71
   Tue–Fri runs. The flag was therefore calendar noise, and the papers were
   lost, not late.
3. **Health gate failed the workflow after the data was committed.** Any
   `*_failed` flag or `partial_success` status made `health_gate` exit 1.
   `pages.yml` deploys only when the daily workflow concludes `success`, so
   2026-09-08 (OpenAlex error) and 2026-09-13 (arXiv HTTP 429 with 782
   OpenAlex papers saved) both left the public site stale.
4. **A single failed `git push` lost a whole day.** 2026-09-12: transient
   "Failed to connect to github.com port 443" at push time, no retry, no
   manifest, nothing published, and `days_back=1` meant the next run did not
   revisit the window.
5. **`seen_dois.json` was truncated as an unordered set.** `save_state` kept
   the "last" 50,000 keys of a `set`, i.e. an arbitrary subset. Which
   already-scored papers were forgotten (and re-scored on the next fetch)
   was random; `--force` additionally overwrote the state with the current
   run's keys only.

Also observed but left for a later batch: cron `0 3 * * *` runs actually
started 07:19–08:14 UTC in September because GitHub queues top-of-hour
schedules.

## Decision

1. **OpenAlex daily mode**: `DAILY_MAX_PAGES = 60` per query (6,000 works,
   ~1.6x the measured window), explicit `sort=publication_date:desc` so a
   capped window degrades to "newest first" instead of "same 400 forever",
   and a `stats` out-parameter that reports pages/results and whether any
   query still had a `next_cursor`. `run_daily` records the stats under
   `source_status.openalex.fetch_stats` and raises the quality flag
   `openalex_truncated` when the window was capped. Historical mode is
   unchanged.
2. **arXiv lookback floor**: `run_daily` uses
   `max(days_back, ARXIV_MIN_LOOKBACK_DAYS=5)`. Five days keeps every
   submission inside the window until it has been announced (worst case:
   Friday after the cutoff → Monday 20:00 ET, plus one holiday day).
   `arxiv_fetcher` scales its daily `max_results` with the lookback
   (2,000 per day) so the wider window is not silently capped. DOI/arXiv-id
   dedup absorbs the repeats. With this floor a zero arXiv return is a real
   anomaly on every weekday, so `arxiv_returned_zero` needs no calendar
   exemption.
3. **CLI default `days_back=2`** (the `run()` signature already said 2; the
   CLI said 1) so a lost run is re-covered by the next one. The manifest now
   records the *effective* per-source lookback plus `requested_days_back`.
4. **Health gate semantics**: block only when `run_status` is not
   success/partial_success, when `fetched_zero`, or when at least half of the
   routed papers failed to score. `partial_success`, single-source
   `*_failed`, `openalex_truncated`, and low-count flags are emitted as
   `::warning::` annotations. The Pages deploy therefore runs whenever the
   day's data was actually written.
5. **Push with retry**: writers call `scripts/git_push_retry.sh` (5 attempts,
   30 s backoff steps, rebase onto `origin/main` between attempts). Used by
   `daily.yml`, `weekly.yml`, and `manual-backfill.yml`.
6. **Ordered dedup state**: `save_state` keeps keys in first-seen order,
   appends new keys deterministically, never drops keys it did not see, and
   caps at 150,000 (the whole corpus fits).
7. **Cron moved to `17 3 * * *`** to leave the crowded :00 slot.
8. **arXiv backoff** 60 / 300 / 900 s (4 attempts): the 09-13 and 09-14
   runs both exhausted the old 60 s + 180 s schedule on HTTP 429.
9. **Historical OpenAlex cap** 40 → 60 pages per query and month window
   (`HISTORICAL_MAX_PAGES`): the concept query alone holds ~4.2k works per
   month in every year 2018–2025, above the old 4,000 cap. Needed before the
   2022-12 .. 2026-05 OpenAlex re-backfill that ADR-0023 left pending.
10. **OpenAlex budget handling (2026-09-14, after backfill run 34857448578).**
    OpenAlex bills per call ($1 / 1,000 `search=` calls, $0.10 / 1,000
    filter calls; anonymous $0.10/day, free key $1/day). The first backfill
    month (2025-01: 11,314 works, 3,427 scored) consumed the anonymous
    budget and month two failed with `Retry-After` ≈ 8.8 h; the workflow's
    commit step only ran on success, so the scored month was discarded.
    Now: `PER_PAGE = 200` (API maximum, halves calls), `run_historical`
    parks the month on `OpenAlexRateLimitError`, records `stopped_early`
    and exits 0 with a warning, the workflow commits completed months even
    after a failure, and the progress directory is keyed by date range so a
    re-dispatch resumes. A free API key is required for multi-month
    backfills (README).

## Consequences

- First run after merge: OpenAlex surfaces up to ~7k never-seen works from
  the current window; at the observed 20 % routing ratio that is ~1.4k
  papers to score once (~¥3 at ¥0.0023/paper, ~10 min at 10-way scorer
  concurrency), then ~500 new works/day (~¥0.3/day). CLAUDE.md §1 accepts
  this explicitly.
- arXiv volume per run rises from ~1 day to 5 days of listings (mostly
  already-seen ids); the API delay is 3 s/page, so ≤ 5 extra minutes.
- The `Zotero ✓/eligible` and status page keep working unchanged; the new
  `openalex_truncated` flag appears in the quality column when it fires.
- `sources_used.*.days_back` in manifests changes meaning from "requested"
  to "effective"; `requested_days_back` preserves the old value.

## Rollback

Set `DAILY_MAX_PAGES` back to 4 and `ARXIV_MIN_LOOKBACK_DAYS` to 1 to
restore the previous fetch behaviour; revert `health_gate.py` to fail on any
`*_failed` flag to restore the old gate. Data files are append-only under
both behaviours, so no data migration is involved either way.

## Verification

- `tests/test_daily_source_windows.py` pins the arXiv floor, the scaled
  `max_results`, the OpenAlex sort/cap/truncation reporting, the
  `openalex_truncated` flag, the effective-lookback manifest fields, and the
  ordered dedup state.
- `tests/test_health_gate.py` pins the new blocking vs warning split.
- `tests/test_workflow_contracts.py` pins the retry script and off-hour cron.
- After the first two live runs: `source_status.openalex.fetch_stats`
  should show `truncated: false` and `after_dedup` should fall well below
  `fetched` once the backlog is scored.
