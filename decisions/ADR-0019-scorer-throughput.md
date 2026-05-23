# ADR-0019: Scorer throughput — concurrent score_batch

**Status**: Accepted (2026-05-23)
**Related**: ADR-0017 (scorer resilience — retry/null-flag), ADR-0014 (scorer baseline)
**Implemented**: commit 8bde2306

## Context

A 10-year fetcher refetch (2015-01..2026-05, broadened OpenAlex recall
per commit 17bd08a) exposed a throughput problem that had been latent
since the scorer was first written.

Measured from data/historical/_progress.json timestamps over the first
72 completed months:

  - 49161 papers scored in 69.1 hours of wall time
  - 5.1 seconds per paper, averaged
  - ~90 percent of per-month wall time was the LLM scoring loop;
    fetcher (arxiv + openalex + pubmed) was only ~3-7 minutes/month

Root cause: pipeline.llm_scorer.score_batch scored papers strictly
serially — a plain `for p in papers: score(p)` loop — even though
DeepSeek tolerates heavy concurrency. A direct probe confirmed 10
concurrent chat-completions calls returned with zero 429s and a wall
time equal to a single call.

At 5.1 s/paper serial, the remaining ~65 months (each ~1000 scored
papers in the 2021+ era) would have taken ~3-4 more days.

## Why this was not caught earlier (retrospective)

This optimization was cheap (stdlib ThreadPoolExecutor, ~30 lines,
SDK is thread-safe) yet went unmade for a long time. Honest account:

1. **Serial was the correct design for the daily cron.** score_batch
   was written for run_daily, which scores ~160 papers/run. At 5 s
   each that is ~13 minutes — comfortably inside the 90-minute
   Actions timeout. Serial code is simpler and easier to debug; for
   that workload it was a reasonable engineering choice.

2. **Backfill reused score_batch without re-evaluating the assumption.**
   run_historical called the same score_batch but at a totally
   different scale (137 months x ~1000 papers = ~50k LLM calls). The
   "serial is fine" premise (small batch) silently stopped holding.
   Nobody recomputed the order-of-magnitude for the new scale.

3. **A prior 10-year backfill (commit 35dd35e) also ran serially and
   "succeeded"** in ~69 hours. "It finished" masked "it was 10x
   slower than necessary." Completion hid the inefficiency.

4. **Repeated time-estimate misses were rationalized, not diagnosed.**
   Estimates drifted (initial guess ~16h, then ~4 days) and each miss
   was explained away with "later months have more papers" instead of
   triggering an actual profile. The estimate error WAS the signal to
   measure; it was treated as noise.

5. **The clearest missed window was the scorer-timeout fix.** When the
   backfill hung 38 minutes on a no-timeout DeepSeek call, we edited
   score_batch's neighbourhood to add a client timeout. The serial
   `for p in papers` loop was right there on screen and went unnoticed
   — fixing one property of a function without auditing its obvious
   adjacent cost.

The optimization only ever cost the idea of doing it; the mechanism was
trivial. The lesson is about when to profile, not about how to thread.

## Decision

Make score_batch concurrent via concurrent.futures.ThreadPoolExecutor.

  - Per-paper logic extracted into _score_one_paper(p, configs): the
    ADR-0017 3-attempt retry loop, null + scorer_failed fallback, and
    _log_scoring_failure — all unchanged.
  - score_batch dispatches _score_one_paper across LLM_CONCURRENCY
    workers (default 8, env-overridable). Futures are mapped back to
    input index, so output ordering is identical to input ordering
    regardless of completion order — required for deterministic
    downstream bucket-writing.
  - LLM_CONCURRENCY=1 preserves the exact original serial path (for
    debugging and to keep the 1-paper unit tests on a stable code path).
  - The OpenAI SDK client is thread-safe; each worker runs its own
    independent retry loop. No shared mutable state between workers
    beyond the client connection pool.

Concurrency level 8 chosen conservatively: a 10-way probe was clean,
8 leaves margin, and the same score_batch is shared by the daily cron
where we do not want to push DeepSeek aggressively.

## Measured impact

  - Probe: 8 real papers scored in 4.1 s at concurrency=8
    (serial estimate 40 s) — ~10x, order preserved, all papers got a
    priority + reasoning, no scorer_failed.
  - Production: month 2021-01 (1644 papers scored) completed in
    ~15-18 minutes of scorer wall time, versus a ~140-minute serial
    estimate (1644 x 5.1 s) — ~8-9x, consistent with 8 workers.
  - Effective rate fell from ~5.1 s/paper serial to ~0.55 s/paper.
  - Daily cron (~160 papers/run) drops from ~13 minutes of scoring to
    well under 2 minutes.

## Not in scope (deferred follow-ups)

These were identified during the same bottleneck analysis but not
implemented, to avoid expanding the change while a backfill was mid-run:

  1. **Score-before-dedup waste.** run_historical scores all routed
     papers, then applies first-seen-wins at write time — so papers
     already in the corpus are re-scored and then discarded. Measured
     ~15 percent of calls wasted (2183 of 14180 over 25 months);
     could reach ~20-24 percent. A pre-score identity_key filter
     against the existing corpus would eliminate this. Cheap in money
     (~CNY 2) but real in time.
  2. **Output-token reduction.** The scorer emits bilingual (zh+en)
     8-field summaries per paper (~800-1200 output tokens), the main
     driver of per-call latency. A leaner scorer_v4 prompt (zh-only,
     en on demand) could roughly halve per-call time. Trades away the
     stored English summary; needs a separate ADR since it touches the
     versioned prompt (CLAUDE.md L157).

Combining concurrency + pre-dedup + leaner output could bring a future
full backfill from ~69 hours toward single-digit hours.

## Lessons (carried forward)

  - Before launching a bulk job, compute the order-of-magnitude
    (count x per-item cost). "137 months x 1000 papers x 5 s" is a
    one-line multiplication that surfaces "days, not hours" before any
    code runs.
  - Reusing a function in a new context invalidates its original
    performance assumptions. score_batch was fine for 160 papers and
    wrong for 50000; the interface hid the regime change.
  - A repeatedly-wrong time estimate is itself a profiling trigger, not
    something to explain away.
  - When editing a hot function for one reason (a timeout fix), audit
    its obvious adjacent costs while you are already there.
