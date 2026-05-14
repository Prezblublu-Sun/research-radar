# ADR-0013: Source precision/recall asymmetry in historical backfill

**Status**: Accepted
**Date**: 2026-05-14
**Decision-maker**: Weikang Sun
**Cross-reference**: commit `6a3ead9` (introduces `routed_by_source` field);
`pipeline/run_historical.py`; `SCOPE.md` § "The Radar to lit-system contract"

---

## 1. Context

Phase B of the C0 PoC plan was the first end-to-end live-API run of
`pipeline/run_historical.py` over a full calendar month (January 2024).
Phase A had delivered the runner itself plus the additive `from_date`/
`to_date` kwargs on all three fetchers, but until now we had no
production-shaped evidence of how the three sources (arXiv, OpenAlex,
PubMed) actually contribute to the routed candidate set.

Commit `6a3ead9` added a new `routed_by_source: {arxiv, openalex, pubmed}`
block to the per-month `counts` dict. This made the per-source routing
yield observable for the first time — `by_source` already reported how
many papers each source fetched, but until now we had no way to see how
many of those papers survived the keyword router. With both numbers in
hand we can finally compute per-source retention and answer "which
sources are precision-limited vs recall-limited?"

---

## 2. Observed data

Phase B dry-run, window 2024-01-01 → 2024-01-31, default historical caps
(arXiv `max_results=10000`, OpenAlex `max_pages=40`, PubMed `retmax=500`).
No LLM scoring (dry-run).

| Source   | Fetched | Routed | Retention |
|----------|--------:|-------:|----------:|
| arxiv    |    5647 |    133 |      2.4% |
| openalex |     414 |    258 |       62% |
| pubmed   |     148 |    104 |       70% |
| **total**| **6209**| **495**|  **8.0%** |

(Total fetched 6209, after cross-source dedup 6181; retention column for
the total row uses the deduped denominator. Per-source retention uses
each source's raw fetched count.)

`by_direction` distribution of the 495 routed papers:

| Direction        | Routed |
|------------------|-------:|
| am_biomedical    |    163 |
| ai_bioprinting   |    148 |
| fea_surrogate    |    115 |
| hip_implant      |     69 |

---

## 3. Decision / finding

**arXiv behaves as a low-precision high-recall source. OpenAlex and PubMed
behave as high-precision lower-recall sources.** This shape is durable
enough to plan around (subject to §6).

The retention asymmetry is consistent with how each source pre-filters
papers before they reach our keyword router:

- **arXiv** is queried by category (`cs.LG`, `cs.CV`, `cs.RO`,
  `physics.med-ph`, `q-bio.TO`, …). Categories like `cs.LG` cast a very
  wide net across all of machine learning regardless of biomedical
  relevance. Almost none of the upstream filtering encodes our research
  directions — the directional filtering is done by *our* keyword router
  downstream. 2.4% retention is the cost of this design choice.
- **OpenAlex** is queried by `concepts.id` plus keyword search. Concept
  IDs (`C2779718196` = "3D bioprinting", `C49892992` = "Tissue
  engineering", etc.) encode topical relevance at the source. Most
  papers that reach our router already match a direction; the router's
  job is mainly to assign the correct one. Hence 62% retention.
- **PubMed** is queried by MeSH terms and Title/Abstract phrases scoped
  to biomedical literature by construction. 70% retention is the result.

The asymmetry is a feature, not a bug. arXiv exists in the pipeline
specifically to widen recall on the ML-methods side (where OpenAlex
concept coverage of preprints is thin and PubMed doesn't index them at
all). The corresponding precision cost is paid by the router rather than
by the upstream query.

---

## 4. Falsified hypotheses

After the smoke test (single-day, 2024-01-15) and the first Phase B run
(arXiv cap = 2000), `hip_implant`'s routed count looked low relative to
the daily baseline (Phase B run: 17% of routed; recent daily runs: ≈27%).
At the time the working hypothesis was: arXiv's 2000-paper cap was
truncating January's traffic and squeezing out the small slice of
`physics.med-ph` / `q-bio.TO` papers that `hip_implant` pulls from.

The cap-bump experiment (commit `6a3ead9` — arXiv historical default
2000 → 10000) **falsified that hypothesis.** Comparison:

| Run             | arxiv fetched | hip_implant routed |
|-----------------|--------------:|-------------------:|
| Phase B (2000)  |          2000 |                 69 |
| Phase B (10000) |          5647 |                 69 |

`hip_implant` routed count stayed at exactly 69 despite arXiv fetching
~2.8× more papers. The daily-vs-historical share gap (27% vs 14% of
total routed) is therefore **not** explained by arXiv cap truncation. The
remaining candidate explanations are:

- Month-specific characteristics — January 2024 may simply have had
  fewer hip/femoral-stem publications than the rolling daily average
  we measured in 2026.
- `hip_implant`'s signal comes predominantly from OpenAlex and PubMed
  (its arxiv categories `physics.med-ph` and `q-bio.TO` are small,
  ~tens of papers/month total), and both those sources have limited
  monthly volume.

In either case, the lever is not arXiv. Bumping the arXiv cap further
will not move `hip_implant`.

---

## 5. Implications for future work

### (a) Per-month cost shape

For Phase C and beyond, keep arXiv as the broad-net source but recognize
that approximately **95% of its papers will be filtered out by the
router**. Per-month arXiv cost dominates wall time and API usage
(Phase B: ~7.5 minutes wall time, ~5647 papers paginated at
`delay_seconds=3` per 100-paper page) despite contributing only roughly
one-third of routed candidates (133 / 495 ≈ 27%). This is acceptable for
backfill, but it is the dominant scaling factor.

### (b) Where the high-leverage tuning lives

For 10-year backfill scale, **OpenAlex and PubMed are the higher-leverage
sources to optimize.** Adding more OpenAlex concept IDs or PubMed MeSH
terms yields more signal per query unit than tuning arXiv keywords —
those sources already have ~60–70% retention, so each additional fetched
paper has a high probability of routing. By contrast, broadening arXiv
keywords would mostly add to the 95% that gets thrown away.

Specifically: OpenAlex concept IDs and PubMed MeSH terms are where
future query-side tuning effort should focus first.

### (c) `routed_by_source` as a regression signal

The `routed_by_source` field should be checked in every future
historical month run as a sanity signal. Sudden retention drops on any
source indicate either:

- an upstream API change (concept IDs renamed, MeSH terms deprecated,
  arXiv date-filter semantics changing), or
- the keyword router regressing (a `must_pair_with` rule accidentally
  tightened, a new direction added with bad keywords, etc.).

Phase B's observed retention was arXiv 2.4%, OpenAlex 62%, PubMed 70%.
Sudden drops in subsequent runs warrant investigation, but absolute
alert thresholds should not be set until at least 3 months of historical
runs are in.

---

## 6. Open questions to defer

- **Single-month data.** All ratios in this ADR derive from one month
  (2024-01). Months with different publication patterns (summer
  conferences, end-of-year journal pushes, COVID-era anomalies, etc.)
  may shift the ratios. Phase C should re-measure.

- **Daily baseline stability.** The "daily mode" shape used as
  comparison (ai 34 / hip 34 / fea 16 / am 40 papers per day) is itself
  drawn from recent 2026 runs and may be inflated by specific 2026
  research trends (e.g. an active period for hip implant
  publications). It is not necessarily a durable target.

- **Per-direction sub-asymmetry.** This ADR aggregates retention at the
  source level. Each direction also has its own source mix
  (`hip_implant` is OpenAlex/PubMed-heavy; `fea_surrogate` is
  arxiv-heavy). A future ADR could break `routed_by_source` down by
  direction if Phase C reveals direction-specific outliers.

Any Feb/Mar 2024 historical runs done before Phase C should re-measure
the per-source retention before treating these ratios as durable
planning numbers.

---

## Related

- `pipeline/run_historical.py` — implementation
- `pipeline/direction_router.py` — the keyword router whose precision
  cost is paid here
- `config/directions.yaml` — source query terms per direction
- `SCOPE.md` § "The Radar to lit-system contract" — recall-over-precision
  optimization function (lit-system trusts the LLM scorer to handle
  noise downstream)
- `CLAUDE.md` § 1 "Optimization function: recall, not precision"
- `TODO.md` § T2.3 (real OpenAlex concept IDs) — informed by this ADR's evidence
- commit `6a3ead9` — adds `routed_by_source`, bumps arxiv historical cap
  2000 → 10000
- commit `34ad938` — adds `pipeline/run_historical.py` (Phase A)
