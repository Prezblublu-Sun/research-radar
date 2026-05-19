# ADR-0017: Scorer JSON-failure resilience + silent-Low rescore

**Status**: DRAFT (2026-05-19)
**Discovered via**: scripts/verify_doi_list.py audit (commit 0389d94)
**Related**: ADR-0014 (scorer baseline), ADR-0015 (v2 schema)

## Context

A DOI verification pass against a 35-paper ground truth surfaced that
3 must_read papers in the v2 corpus had priority Low but completely
empty LLM reasoning fields (relevance_to_user, summary_zh.motivation,
tags all empty). Full-corpus audit revealed this is widespread:

  **5479 of 34196 papers (16.0%)** carry priority Low with empty
  reasoning. 100% have a populated llm.priority_reason field with a
  Python exception trace.

Root cause: pipeline/llm_scorer.py line 145 catches all LLM-call
exceptions (primarily json.JSONDecodeError) and assigns priority Low
with the exception string saved as priority_reason. No retry. No flag.
The paper proceeds through the pipeline as a regular Low-priority paper.

Top error categories (covering ~90 percent):

- "Expecting value: line 1 column 1" (593 papers) — empty response or
  non-JSON output (e.g. plain text or markdown fence)
- "Unterminated string starting at ..." (~150) — response truncated
  mid-string
- "Expecting property name enclosed in double quotes ..." (~250) —
  unescaped quote inside Chinese fields or trailing comma

Failures concentrate in 2025-05 onward (66 percent+ silent ratio for
several months during the 10-year backfill window).

## Impact

- 16 percent of corpus mis-classified as Low. True priority distribution
  unknown.
- Downstream consumers (export_candidates, weekly_report,
  high-priority.html, medium-priority.html) treat silent Low identically
  to genuine Low.
- The auditor's "must_read recall = 21 percent" understates radar's real
  scoring quality — some misses are silent failures, not router gaps
  or scorer judgement disagreements.
- Lit-system never sees these papers because they don't pass the
  Medium+ candidate threshold.

## Decision

Two-pronged response:

**Decision 1 — scorer resilience.** Modify pipeline/llm_scorer.py so
that JSON-parse failures trigger a bounded retry rather than
silent-Low fallback:

1. On first failure, retry once with the same prompt (transient API
   hiccup tolerance).
2. On second failure, retry with a stricter instruction prefix
   ("Output ONLY valid JSON. No markdown fences. No commentary.").
3. On third failure, set priority = null (not Low) and write a
   scorer_failed = true flag. Downstream tools can then filter these
   papers explicitly rather than treating them as genuine Low.

Why null instead of Low: the current silent-Low contaminates
analyses. A null + flag makes the failure visible and filterable
without polluting priority statistics.

Why not scorer_v4 prompt now: introducing a v4 prompt mixes scorer
versions across the corpus during rescore. Resilience first, prompt
revision later (separate ADR if needed).

**Decision 2 — rescore the 5479 silent papers in place.** Run a
one-off scripts/rescore_silent.py that:

- Walks data/daily/20*.json and identifies silent papers (priority set
  plus reasoning empty plus priority_reason populated).
- For each, re-invokes the scorer (with the new retry logic) against
  the paper's existing title + abstract + direction context.
- Writes results atomically: write new daily JSON to tmp, fsync, mv.
- Resumable: if interrupted, skips already-rescored papers on restart.
- Estimated runtime: ~5 paper/sec × 5479 = **~8 hours** continuous run.
- DeepSeek cost: ~CNY 40-50 (within explicit operational envelope,
  single-shot one-off cost).

## Alternatives considered

1. **Do nothing, treat silent-Low as Low.** Rejected — 16 percent
   mis-classification including known-good must_read papers.
2. **Re-score whole corpus.** Rejected — 47-hour scorer run, large
   cost, and re-scoring already-correct papers risks introducing
   inconsistency.
3. **Move to scorer_v4 prompt first, then rescore.** Rejected for
   this ADR — bigger change, mixes versions, harder to attribute
   future quality changes. Prompt revision deferred.
4. **Skip retry, just write priority=null on first failure.** Rejected
   — many failures are transient (API hiccup, truncation), worth
   retrying.

## Implementation plan

Steps (this commit cluster):

- Patch pipeline/llm_scorer.py with 3-retry logic + null + flag on
  final failure. Add unit tests covering: retry on parse error,
  success after retry, null + flag after 3 failures.
- Add scripts/rescore_silent.py (CLI tool). Tests for: silent-paper
  detection, atomic write, resumability via a skip-already-scored
  check.
- Run rescore against the real corpus. Capture before/after stats
  (silent paper count to 0, priority distribution shift).
- Re-run scripts/verify_doi_list.py and commit the new report
  snapshot. Expected: must_read recall climbs significantly.

Not in scope (deferred):

- Fetcher gap (separate ADR if + when addressed).
- scorer_v4 prompt revision.
- Tighter validation in v2_schema.py.

## Verification

After implementation + rescore:

- Re-run silent-paper audit: count should drop to near-zero (only
  papers that hit all 3 retries on transient API issues).
- Re-run scripts/verify_doi_list.py: must_read papers previously
  reported under_scored with empty reasoning should now have either a
  real priority + reasoning, or priority null plus scorer_failed flag.
- Confirm priority distribution shift in counts: expect Low count to
  drop, Medium and High counts to rise.

## Risks

- DeepSeek API rate limiting during the 8-hour rescore. Mitigation:
  rescore script honours existing API client backoff; tmux runs
  survive SSH drops.
- 100 percent silent papers receive null+flag in worst case (DeepSeek
  service degraded during rescore window). Mitigation: resumable
  script, restart later.
- Mid-run scorer call may produce different priority for the same
  paper between rescore attempts (LLM nondeterminism). Acceptable:
  result is at least valid + reasoned, vs the empty silent fallback.
