# ADR-0018: Corpus analytics — descriptive statistics over scorer outputs

**Status**: Proposed (2026-05-20)
**Date**: 2026-05-20
**Supersedes**: —
**Related**: ADR-0012 (radar/lit-system separation), ADR-0015 (v2 schema), ADR-0016 (paper curation UI)

---

## 1. Context

After the 10-year backfill completed 2026-05-19, the v2 corpus contains ~34000 scored papers across 3554 daily bucket files spanning 2015-01..2024-12 plus 2025-04..2026-04. Every paper carries scorer_v3-emitted fields: `llm.priority`, `direction`, `llm.tags`, `llm.key_terms`, plus standard metadata (date, source).

At this corpus size three questions become operationally useful but currently require ad-hoc grepping:

**Question A — Distribution**: how many papers per direction per year/month? How does the High/Medium ratio shift over time? Which directions are accelerating, which are saturating?

**Question B — Theory trends**: which tags and key_terms are gaining or losing frequency over the years, per direction?

**Question C — Cross-direction overlap**: which tags span multiple directions (hinting at interdisciplinary clusters)? How content-similar are the four directions to each other?

The user wants these answered systematically rather than re-running ad-hoc queries each time.

This ADR is needed because the surface phrasing of these questions ("analytics", "trends", "research map", "keyword graph") triggers SCOPE.md prohibitions on "Knowledge graph construction" (L51), "Citation graph analysis" (L52), and "Multi-paper synthesis beyond the weekly LLM meta-summary" (L56). Without an explicit interpretive boundary, future Claude Code sessions will (correctly) reject this work. This ADR establishes the boundary.

---

## 2. Decision

Implement **descriptive statistics over existing scorer-emitted fields** as a new analytics module in radar. Three sub-features, all read-only against the v2 corpus, all producing static artifacts.

### A1: Distribution statistics

Per-year and per-month counts of scored papers, broken down by `direction` and `llm.priority`. Outputs:
- `docs/analytics/distribution_yearly.csv`
- `docs/analytics/distribution_monthly.csv`
- `docs/analytics/distribution_yearly.png` (stacked bar by direction, with High/Medium overlay)
- `docs/analytics/distribution_priority_ratio.png` (High+Medium share over time, one line per direction)

### A2: Theory frequency tables

Per-year frequency tables of `llm.tags` and `llm.key_terms`, sliced by `direction`. Plus a simple "delta" view: top N tags whose frequency in year T exceeds their frequency in T-1 by some threshold. No topic modeling, no embeddings, no clustering — just counts and arithmetic deltas.

Outputs:
- `docs/analytics/tag_frequency_by_year_by_direction.csv`
- `docs/analytics/key_term_frequency_by_year_by_direction.csv`
- `docs/analytics/tag_top20_per_direction_per_year.png` (small-multiples line plot)
- `docs/analytics/tag_emerging_terms.csv` (terms with positive year-over-year delta above threshold)

### A3: Cross-direction co-occurrence (reduced "research map")

A `tag × direction` co-occurrence matrix (cell = count of papers in that direction carrying that tag), plus pairwise direction-to-direction Jaccard overlap on the tag set. Rendered as heatmaps.

Outputs:
- `docs/analytics/tag_direction_cooccurrence.csv`
- `docs/analytics/tag_direction_heatmap.png`
- `docs/analytics/direction_jaccard.csv`
- `docs/analytics/direction_jaccard_heatmap.png`

### Implementation shape

- One CLI entry point: `scripts/build_analytics.py`
- Pure read against `data/daily/*.json`
- Outputs go to `docs/analytics/`
- One link added from `docs/index.html` to an `docs/analytics/index.html` summary page that embeds the PNGs and links the CSVs
- No new render dependency from `build_pages.py`; analytics is a separate offline script the user runs when they want fresh numbers

---

## 3. Scope boundary — what this ADR DOES and DOES NOT permit

This is the central purpose of this ADR. Read carefully.

### Permitted under this ADR

- `Counter()`, `groupby`, frequency tables, cross-tabulation matrices over existing scorer fields
- Year-over-year arithmetic deltas (`freq(t, year_n) - freq(t, year_n-1)`)
- Jaccard / set-overlap arithmetic between pre-existing direction labels
- Matplotlib / seaborn static PNG charts (bar, line, heatmap, small-multiples)
- CSV / JSON outputs of the above
- One static HTML summary page that embeds the PNGs

### Still prohibited (no change from SCOPE.md / ADR-0012)

- **Topic modeling** of any kind: LDA, NMF, BERTopic, or any algorithm that infers latent topics beyond what scorer_v3 has already labeled
- **Embeddings** of papers, tags, or terms — no word2vec, no sentence-transformers, no vector representations
- **Knowledge graph or keyword graph construction** — including node-edge visualizations of tag relationships. A heatmap of a co-occurrence matrix is permitted; a force-directed graph of the same data is not. The distinction is: matrices are tabular summaries, graphs are structural claims about the field.
- **Citation graph analysis** — no traversal of references / citations between papers
- **LLM-generated narrative synthesis** — no "summarize how the field evolved" prompts, no per-cluster LLM descriptions. The weekly_report meta-summary remains the only LLM-authored cross-paper artifact in radar.
- **Emerging-term detection** beyond simple arithmetic delta. No change-point detection, no Mann-Kendall, no statistical novelty modeling.
- **Author / institution analytics** — no author-network, no institution-ranking. OpenAlex-provided affiliation strings may appear in raw outputs but are not analyzed.

The principle: **descriptive statistics summarize what is already in the data; topic modeling, embeddings, and graphs invent new structure.** This ADR permits the former, not the latter.

If a future analytics request would require any prohibited operation, that request belongs in lit-system or requires its own new ADR — not a stretch of this one.

---

## 4. Why this is in scope despite the SCOPE.md surface-language conflict

SCOPE.md L51-56 prohibits "Knowledge graph construction", "Citation graph analysis", and "Multi-paper synthesis beyond the weekly LLM meta-summary". A naive reading of the request "build analytics with trend visualization and a research map" trips all three.

A careful reading shows the prohibitions are about **methods that invent new semantic structure** (graphs, synthesized narratives), not about **statistical descriptions of existing fields**. The weekly_report already aggregates across papers and is explicitly permitted; this ADR extends the same principle to year-level and direction-level aggregates.

The user explicitly clarified during scope discussion (2026-05-20) that the analytics module should remain in radar rather than be pushed to lit-system, because:
- The inputs are scorer-emitted fields, which live in radar
- The outputs are operational ("which direction is accelerating?") rather than research-synthesis ("what is the intellectual structure of the field?")
- lit-system's deep-PDF / RAG layer is the wrong stack for groupby-and-count work

---

## 5. Out of scope (for this ADR specifically)

- Interactive dashboards (Plotly, Bokeh, Dash) — static PNGs only
- Jupyter notebook delivery — CLI + static artifacts only
- Per-paper analytics surfaces (e.g. "papers similar to this one") — fully prohibited, belongs in lit-system if anywhere
- Tag-graph visualization (force-directed, network layout) — recorded here as a possible lit-system candidate, not implemented in radar
- Mining `llm.relevance_to_user` or `llm.flags` free-text fields with NLP — these fields are LLM rationale strings, not structured data; out
- Cross-corpus analytics that mix in lit-system data — radar analytics reads radar corpus only

---

## 6. Implementation phases

Phase A: `scripts/build_analytics.py` with A1 (distribution) only. CSV + PNG outputs, no HTML page yet. Single commit.

Phase B: Extend script with A2 (theory frequency). Adds CSV + PNG outputs.

Phase C: Extend with A3 (co-occurrence / Jaccard). Adds CSV + PNG.

Phase D: `docs/analytics/index.html` summary page + link from `docs/index.html`. Either hand-written template or extension of `build_pages.py` (decided at implementation time, lean toward standalone template to avoid coupling).

Each phase is a separate commit (code commit + a docs commit if `docs/analytics/` is regenerated, per the lessons-learned split convention).

---

## 7. Reversibility

`scripts/build_analytics.py` is a read-only offline script. To revert: delete the script and the `docs/analytics/` tree. No data is affected. No downstream consumer (lit-system, weekly_report, export_candidates) reads analytics outputs.

The one persistent change is the link from `docs/index.html` to `docs/analytics/index.html`, removed by undoing the relevant render-template diff.

---

## 8. Open questions

- Q1: Tag frequency aggregation — should we count `llm.tags` (scorer-emitted tags) only, or also `llm.key_terms` (free-text key terms)? Decision: both, in separate CSVs; key_terms are noisier but more granular.
- Q2: Should `priority=Exclude` papers be counted in distribution stats? Decision: separate column in CSV, omitted from default PNG views. They are part of the corpus but not part of "what radar surfaced".
- Q3: How many top-N tags in the small-multiples per-direction plot? Default 20, configurable.
- Q4: For the emerging-terms CSV, what delta threshold? Specified at implementation time; start with "appears 5+ times in year T and 2x its frequency in T-1".
- Q5: Should analytics regenerate on cron or only on manual invocation? Decision: manual only for now. Adding it to `daily.yml` is a future ADR if usage justifies the runtime cost.

---

## 9. No SCOPE.md or CLAUDE.md amendment required

Unlike ADR-0016 which carved a new exception, this ADR clarifies the interpretation of existing scope language rather than amending it. SCOPE.md L51 ("Knowledge graph construction") and L56 ("Multi-paper synthesis beyond the weekly LLM meta-summary") remain unchanged.

Future Claude Code sessions should treat this ADR as the controlling interpretation when proposing analytics work: descriptive statistics over scorer-emitted fields are permitted; graphs / embeddings / topic models / LLM synthesis are not.

If a future analytics request requires operations this ADR prohibits, it requires its own new ADR or amendment, not a stretch of this one.
