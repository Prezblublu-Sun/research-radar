# ADR-0026: Layered LLM summary aggregation (review-loop) — scope amendment

**Status**: Accepted (2026-05-27)
**Date**: 2026-05-27
**Supersedes**: —
**Related**: ADR-0012 (radar/lit-system separation), ADR-0018 (corpus analytics scope), ADR-0023 (review loop baseline), ADR-0024 (fea_surrogate scorer refinement), ADR-0025 (figshare/Zenodo DOI normalization)

---

## 1. Context

The radar repo now hosts two distinct LLM workloads:

1. **Corpus analytics** (ADR-0018). Descriptive statistics over scorer-emitted fields (counts, frequencies, Jaccard, deltas). **No multi-paper synthesis.** Implemented in `scripts/build_analytics.py`, outputs `docs/analytics/`.
2. **Review loop** (ADR-0023). Claude Code reads High/Medium papers, writes per-paper Chinese summaries, then aggregates them into weekly reports. Implemented in `review_harness.py` + `REVIEW_RUNBOOK.md`, outputs `data/review/summaries/*.md` + `reports/weekly/{YYYY-Www}_周报.md`.

The review loop has been producing LLM narrative summaries since pilot W19/W20/W21. SCOPE.md L56 ("Multi-paper synthesis beyond the weekly LLM meta-summary") and CLAUDE.md L44 ("Cross-paper synthesis beyond the weekly LLM meta-summary") were written in May 2026 to forbid this class of work in radar. **The original framing already carved out "the weekly LLM meta-summary" as the one exception, but that carve-out is too narrow for the actual review-loop product:** weekly reports exist, the next layer (monthly aggregation of weekly reports) is being asked for, and a multi-tier hierarchy (paper → weekly → monthly → quarterly → annual) is the explicit long-run design intent.

This ADR formally permits **layered aggregation of LLM-authored per-paper summaries within the radar repo**, defines exactly what "layered" means, and re-establishes the boundary with lit-system so the two systems still do not overlap.

This ADR also clarifies that ADR-0018 (corpus analytics) is **unaffected**: analytics remains descriptive-statistics-only over scorer-emitted fields, with no LLM narrative. The two workloads remain separate machines.

---

## 2. Decision

### 2.1 Permitted: layered LLM aggregation of review-loop artifacts

Within the radar repo, Claude Code (orchestrated by `review_harness.py`) may generate LLM-authored aggregate reports at the following layers:

| Layer | Input | Output | Cmd |
|-------|-------|--------|-----|
| 单篇 | radar v2 scorer record + downloaded PDF | `data/review/summaries/{id}.md` | `next` / `done` |
| 周报 | per-paper summaries within ISO week | `reports/weekly/{YYYY-Www}_周报.md` | `weekly` |
| 月报 | weekly reports within calendar month | `reports/monthly/{YYYY-MM}_月报.md` | `monthly` |
| 季报 | monthly reports within calendar quarter | `reports/quarterly/{YYYY-Q[1-4]}_季报.md` (future) | `quarterly` (future) |
| 年报 | quarterly reports within calendar year | `reports/annual/{YYYY}_年报.md` (future) | `annual` (future) |

**Hard rule: each layer consumes ONLY the layer immediately below it, not arbitrary underlying material.** Monthly reports read weekly reports, not raw summaries. Quarterly reports read monthly reports, not weekly reports. This is what makes the hierarchy a real compression hierarchy and bounds Claude Code's context load per session.

Annual / quarterly are future. This ADR implements the monthly layer.

### 2.2 Still prohibited (no change from SCOPE.md / ADR-0012 / ADR-0018)

The following remain out of scope for the radar repo and belong in lit-system:

- **PDF deep parsing pipeline** (Docling, GROBID, layout-aware extraction). The review loop's PDF download + text extraction is "shallow": `_looks_like_article()` gates landing pages, PyMuPDF / pdfplumber strip text. It is NOT structured parsing.
- **Embeddings / vector stores / RAG / chat-with-papers** of any form.
- **Knowledge graphs / citation graph analysis.**
- **Topic modeling, clustering, learned synonym merging** (ADR-0018 §3 carve).
- **Annotation UI on deep-parsed PDFs** (ADR-0016 carve preserved).
- **Cross-corpus synthesis that mixes data outside the review loop** (e.g. feeding raw v2 corpus into an LLM "what is happening in the field" prompt). The review loop is anchored on the per-paper summary chain; ad-hoc LLM surveys of the broader corpus remain out.

### 2.3 ADR-0018 (corpus analytics) compatibility

ADR-0018 §3 forbids "LLM-generated narrative synthesis" in the analytics workstream. **That prohibition stands.** The corpus analytics module (`scripts/build_analytics.py`, `docs/analytics/`) does NOT produce narrative reports under any circumstance. It produces CSV + PNG only.

The carve-out in this ADR-0026 applies exclusively to the review-loop workstream. The two are different code paths, different output directories, and different ADR governance. A future analytics request for narrative does NOT inherit any permission from this ADR.

---

## 3. Scope amendment text

Applied in the same commit as this ADR.

### 3.1 SCOPE.md L56 replacement

Existing line: `Multi-paper synthesis beyond the weekly LLM meta-summary`

Replaced with: `Multi-paper synthesis beyond what the review loop produces (per-paper → weekly → monthly → quarterly → annual, each layer consuming only the layer below; ADR-0026). Ad-hoc multi-paper synthesis outside this chain remains out of scope.`

### 3.2 CLAUDE.md L44 replacement

Existing line: `Cross-paper synthesis beyond the weekly LLM meta-summary`

Replaced with: `Cross-paper synthesis outside the review-loop layered chain (per-paper → weekly → monthly → quarterly → annual; ADR-0026)`

### 3.3 ADR-0018 §3 update note

Append to the "Still prohibited" block:

> **2026-05-27 update (ADR-0026):** The "LLM-generated narrative synthesis" prohibition above remains in force for the analytics workstream. ADR-0026 permits layered LLM aggregation in the review-loop workstream only; that permission does NOT propagate to analytics. `scripts/build_analytics.py` remains narrative-free.

---

## 4. Implementation phases

**Phase M (monthly aggregation)** — this ADR's headline:

- Extend `review_harness.py` with `cmd_monthly(year_month)`. Output: JSON manifest listing the weekly reports in that month + paper counts + report output path. Pattern is identical to `cmd_weekly`: harness selects and names, Claude Code writes the markdown.
- Add `reports/monthly/` directory.
- Update `REVIEW_RUNBOOK.md` with a monthly cadence section.
- First production monthly report when at least 3 weekly reports exist in a given month.

**Phase Q / A (quarterly / annual)** — DEFERRED. Re-evaluate after 2-3 monthly reports are in flight.

**Phase M.5 — Render injection for existing weekly HTML (added 2026-05-27).**

The `docs/weekly/{YYYY-Www}.html` pages generated by `pipeline.weekly_report` (cron) currently carry a "Trend analysis and LLM weekly summary coming soon" placeholder. When the corresponding `reports/weekly/{YYYY-Www}_周报.md` exists (an ADR-0026 layer-2 artifact), an out-of-band script `scripts/inject_weekly_summary_to_html.py` rewrites that placeholder with the rendered markdown content.

Scope clarification: this is rendering configuration of an ADR-0026 layered artifact (the weekly markdown report) into a pre-existing radar surface, NOT a new computation. The script does NOT modify `pipeline/weekly_report.py`, does NOT change cron behavior, does NOT alter the markdown source-of-truth in `reports/weekly/*.md`. It only updates the HTML view of weeks for which a markdown report exists.

One-way coupling: future cron-generated weekly HTML files will continue to display the "coming soon" placeholder until and unless this injection script is run against them. cron does not re-render historical weeks (verified 2026-05-27 by inspecting weekly.yml + git log of docs/weekly/*.html). Therefore manual injections are not at risk of being overwritten.

Phase M (monthly aggregation, `cmd_monthly` in `review_harness.py`) is unchanged by this addition. M.5 operates independently and can be developed/deployed before, after, or in parallel with M.

---

## 5. Why this stays sound vs the radar/lit-system separation (ADR-0012)

ADR-0012 is about NOT duplicating lit-system inside radar. The review loop already inhabits that gray zone (it reads PDFs, writes LLM summaries). This ADR formalizes what was already happening rather than expanding it. Critically:

- The review loop reads only papers radar already scored High/Medium. lit-system reads everything in its own corpus.
- The review loop's parsing is shallow; lit-system does Docling-grade structured parsing.
- The review loop produces narrative summaries indexed by paper-id; lit-system produces vector-indexed knowledge stores.
- Layered aggregation in this ADR operates on review-loop summaries only; it does NOT pull from lit-system stores or vice versa.

The two systems remain non-overlapping. If a future capability blurs them (e.g. "give me lit-system embeddings of review-loop summaries"), that requires a new ADR.

---

## 6. Reversibility

`cmd_monthly` is one new function in one harness file. Reports live as markdown files. To revert: remove the function, remove the `reports/monthly/` tree, restore SCOPE.md and CLAUDE.md to their pre-ADR-0026 wording. No data is touched; review summaries and weekly reports remain.

---

## 7. Open questions

- **Q1**: Should `cmd_monthly` enforce "all weeks present"? Decision: YES, refuse by default with a list of missing weeks; provide `--allow-partial` to override.
- **Q2**: Monthly manifest field shape — include per-week paper counts? Decision: YES, include `papers_count_by_week`.
- **Q3**: Should monthly reports be committed via Claude Code or by the user? Decision: by the user (consistent with weekly).

---

## 8. Companion artifacts

This ADR is committed together with:

- `SCOPE.md` amendment (single line replacement at L56)
- `CLAUDE.md` amendment (single line replacement at L44)
- ADR-0018 §3 update note (one paragraph addition)

A follow-on commit extends `review_harness.py` + `REVIEW_RUNBOOK.md` to implement Phase M. A third commit (later) lands the first monthly report once Claude Code has been invoked to write it.
