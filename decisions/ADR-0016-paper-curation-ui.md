# ADR-0016: Paper curation UI — quality-day filtering + reading marks

**Status**: Accepted (2026-05-19)
**Date**: 2026-05-18
**Supersedes**: —
**Related**: ADR-0015 §7 (deferred UI work)

---

## 1. Context

After the 10-year backfill completes (2015-01 to 2024-12 + 2025-04 to 2026-04), the v2 corpus contains ~30000 scored papers across ~3000 publication-date HTML pages. Two usability problems emerge at this scale:

**Problem A — sparse daily pages**: Roughly half of daily pages contain zero papers above the Low priority floor. Clicking a random date often yields no actionable content. The user reports: "I keep landing on days with no Medium or High results."

**Problem B — no reading trail**: As the user browses, papers of interest get re-discovered. There is no way to mark "I read this", "I want to read this later", "this is interesting for X". With 30000 papers in the corpus the absence of any persistence layer makes the radar increasingly hard to use as more papers accumulate.

This ADR specifies the minimum-viable UI affordances to address both.

---

## 2. Decision

Implement five separate UI affordances, grouped into two themes. All implementations are client-side; no producer changes; no schema changes.

### Theme 1 — Quality-day filtering

**D1: priority-count badges on the calendar / index page**
Each daily entry in docs/index.html (and any calendar view) displays a count breakdown of the day's papers: (2H, 5M, 12L) style, where H/M/L correspond to High/Medium/Low. Days with zero Medium+ are visually de-emphasized (greyed-out text or a softer color). Pure-Exclude days may be hidden behind a "Show all" toggle.

**D2: cross-corpus high-priority page** at docs/high-priority.html
A single flat list of every High-priority paper across all directions, sortable by date (newest first) and direction. Acts as a "skip the calendar and just give me the best hits" entry point. Mirror at docs/medium-priority.html for completeness.

**D3: in-page filter toggle on each daily page**
Each docs/YYYY-MM-DD.html gains a small header control: a row of priority toggles (default: High + Medium on, Low + Exclude off). The DOM is rendered with all papers, JavaScript hides/shows based on toggle state. No re-render needed; client-side filter only.

### Theme 2 — Reading trail

**D4: localStorage-backed reading marks**
Per-paper UI controls allow marking each card as one of: to-read / read / interesting / ignore. State persists in localStorage keyed by paper identity-key (doi:... or arxiv:...). Marks render as a small colored stripe on the paper card so the state is immediately visible without clicking. A "filter to my marks" toggle at the daily-page level (similar to D3) lets the user see only their marked papers.

A free-text notes field per paper is also localStorage-backed, with a textarea that appears on click. Notes auto-save on blur.

Limitations the user accepts explicitly:
- Marks and notes live in one browser only; clearing cache or switching device loses them
- No multi-device sync
- No git history of marks
- No backup; export-to-JSON button provided as a manual escape hatch

The trade-off is intentional: zero backend work in exchange for fully ephemeral state. If a future ADR upgrades this to a sync backend, the localStorage schema is forward-compatible (records will simply migrate).

**D5: "Promote to lit-system" button**
A separate action button per paper: "Send to lit-system". On click, the paper identity-key + minimal metadata is appended to a manual queue file. Two implementation options:

- D5.A (preferred): localStorage queue, exposed as a "Copy promoted papers" button that emits a JSON array the user paste-imports on the lit-system side.
- D5.B (deferred): write directly into data/exports/promoted_candidates.jsonl via a GitHub-Action-triggered workflow. Requires designing the trigger surface (issue creation? Form submission?) — out of scope for this ADR.

Start with D5.A. Re-evaluate after a month of usage.

---

## 3. Schema / data contract notes

No producer schema change. All affordances read from existing v2 paper fields (schema_version, doi, arxiv_id, llm.priority, etc).

Calendar count badge (D1) requires the render step to compute per-day priority counts. The v2 bucket files already contain counts.priority_counts. Use that.

High-priority cross-corpus page (D2) requires the render step to scan all daily files and collect High-priority papers. This is a new render pass, similar to the directional pages.

localStorage schema (D4) — to be specified at implementation time. Likely:
  key:   radar:mark:<identity_key>
  value: { state, at, note }

---

## 4. Out of scope

- Multi-device mark sync
- Server-side state
- LLM-assisted "papers similar to my marks" recommendations
- Direct write-back to git from the browser
- Editing scoring decisions (no human-override of llm.priority)
- date_precision badges (still deferred to a separate Phase 4.4 ADR)
- calendar view layout (deferred)

---

## 5. Implementation phases

Phase A (after backfill completes 2026-05-19/20):
- D1: priority count badges in index/calendar
- D2: high-priority cross-corpus page
- D3: daily-page filter toggle

Phase B (after Phase A is stable, ~1 week later):
- D4: localStorage marks + notes
- D4 export-to-JSON escape hatch

Phase C (~1 month after Phase B usage):
- D5: lit-system promote queue (D5.A first)
- Evaluate D4 storage backend upgrade based on actual usage pain

Each phase is a single commit or small commit cluster. Phase A landings will require a second docs/ regenerate.

---

## 6. Reversibility

All five affordances are client-side. To revert any of them, remove the JavaScript / HTML additions and re-render docs/. Data is unaffected. No downstream consumer (lit-system, weekly_report, export_candidates) reads anything written by these affordances.

---

## 7. Open questions

- Q1: For D1 priority count badges, should "no Medium+" days be hidden by default with a "Show all days" toggle, or merely greyed? Decision: grey only; user retains the ability to land on any date. Hiding defeats the calendar.
- Q2: Should D4 marks contribute to D2's high-priority page? E.g., "interesting" papers also appear there. Deferred to Phase B implementation.
- Q3: For D5.A (localStorage queue), what exactly should the JSON include? Minimum: identity_key, title, date, direction, priority. Specified at Phase C implementation.


---

## 8. Scope amendment rationale (2026-05-19)

When SCOPE.md was originally written (2026-05-14), it placed all curation/annotation/mark UI under "What Radar is NOT", redirecting them to lit-system. That was correct at the time: the v2 corpus was small, lit-system was the obvious place for any per-paper user state.

After the 10-year backfill completed 2026-05-19, the corpus is ~34000 papers across 3554 daily pages. The user reports that browsing the radar surface without any per-paper reading trail is no longer sustainable: papers get re-discovered, decisions get re-made. The pain is real and Radar-specific (it happens at the browse-and-triage step, not at the deep-reading step).

Crucially, the user clarified the two systems do not actually conflict:
- lit-system runs automatic LLM annotation on already-ingested PDFs. The user does not hand-edit those annotations.
- Radar is where the user manually browses, marks, and notes during triage, before deciding what to send to lit-system.

The two layers have non-overlapping responsibilities: lit-system = machine annotation of deep-parsed PDFs; Radar = human curation of the discovery feed. Both can co-exist without violating the original separation-of-concerns intent.

SCOPE.md and CLAUDE.md are amended in the same commit as this ADR's Accepted promotion to reflect the new boundary.
