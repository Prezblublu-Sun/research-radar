# Phase B revision note — provenance correction

**Date**: 2026-05-27
**Subject**: ADR-0018 Phase B revision (A2 HM-priority default + showdown family widening)

## What happened

The Phase B revision of `scripts/build_analytics.py` and `tests/test_build_analytics.py`
— described below — was committed as part of `cfcc4f012`:

    "data: manual daily run 2026-05-24 — backfill missed papers + era-split index"

That commit's title and message describe data + index work and do NOT mention Phase B,
the A2 priority filter, FEM_FAMILY widening, or the new tests. The Phase B code
modifications were swept into that commit incidentally during another working session.

This note exists so a future reader doing `git log --grep "phase B"` or
`git log --follow scripts/build_analytics.py` can locate the actual provenance of
the Phase B revision rather than being misled by the dominant commit title.

## What the Phase B revision contains (now in HEAD)

1. **A2 defaults to High+Medium priority.** Tag aggregation (`(year, direction,
   canonical_tag)` Counter) counts only papers whose `llm.priority` ∈ {High, Medium}.
   Eliminates the ~11000 education / flipped-classroom contamination in fea_surrogate
   (scorer Excluded them all; HM filter drops them cleanly).
2. **`--include-all-priorities` CLI flag** reverts A2 to legacy all-priority
   behavior (default off).
3. **FEM_FAMILY widening**: explicit set
   {"finite element analysis", "finite element method", "finite element",
    "finite element simulation", "finite element model", "finite element modeling"}.
4. **NEURAL_OP_PINN family**: predicate that matches tags containing the substring
   "neural operator" OR in the PINN alias set
   {"pinn", "physics-informed neural network", "physics-informed neural networks",
    "physics-informed nn"}.
5. **Two new tests**: `test_hm_default_filters_low`, `test_showdown_family_variants`.
   Existing A2 tests updated to use High/Medium synth papers under the new default.
6. Chart titles/footnotes updated to state "High+Medium papers only" or
   "all priorities" depending on flag.
7. A1 (distribution) behavior unchanged.

Test suite at the time: 201 passed.

## Scope

This revision remains within ADR-0018 section 3 — `llm.priority` is a scorer-emitted
field, so filtering by it is descriptive statistics, not synthesis. Family definitions
are explicit (set membership + substring rule), not inferred. No embeddings, clustering,
or topic models were introduced.

## Why this is being filed now rather than at the time of `cfcc4f012`

The Phase B revision was code-reviewed in the analytics workstream session
(2026-05-23 night), passed 201 tests, was smoke-tested into /tmp, and both the
`methodology_showdown.png` and `tag_top12_trends_fea_surrogate.png` outputs were
human-reviewed and approved. The intended commit cadence at that time was a clean
two-commit split (code + docs), with a precise commit message. That cadence was not
followed: the changes were instead bundled into `cfcc4f012` under an unrelated title,
without a corresponding docs render to `docs/analytics/`. This note + the upcoming
HM-priority render commit close out the Phase B work properly.
