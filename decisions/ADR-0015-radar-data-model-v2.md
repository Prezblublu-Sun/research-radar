# ADR-0015: Radar data model v2 — date semantics, file scheme, scorer schema, calendar view

**Status**: Accepted
**Date**: 2026-05-14
**Decision-maker**: Weikang Sun
**Cross-reference**: ADR-0013 (Phase B source asymmetry); ADR-0014
(Phase C scoring baseline); commit `9716068` (DeepSeek model
migration); `data/historical/2024-01.json` (Phase C scored output);
`SCOPE.md` § "The Radar to lit-system contract"; `CLAUDE.md` § 1
"Optimization function: recall, not precision"; `CLAUDE.md` § 4
"Data-integrity guardrails come before features"

---

## 1. Context

Phase C surfaced three concrete data-model mismatches between the
daily and historical pipelines that have, until now, been tolerated as
"daily and historical are different modes." With Phase C complete and
both modes producing JSON consumed by overlapping downstream code
(`pipeline/export_candidates.py`, the docs site, scope_audit), the
mismatches are no longer free.

The three concrete mismatches:

- **(i) `date` field semantics differ across the three sources.**
  OpenAlex returns a month-only `publication_date` for roughly 30% of
  papers, and the fetcher silently falls back to `YYYY-MM-01` so
  downstream code can't tell a real first-of-month publication apart
  from a month-precision unknown. arXiv's `submittedDate` filter
  matches *any version's* submission, not specifically v1 — a paper
  revised in January 2024 will match a January 2024 window even if v1
  was posted in 2023. PubMed uses `EDAT` (Entrez Date — when the
  record entered PubMed), which is operationally distinct from the
  paper's actual publication date and can lag by months.
- **(ii) Top-level JSON schema differs.** Daily files are a flat list
  of paper dicts. Historical files are a dict with
  `schema_version` / `month` / `window` / `dry_run` / `completed_at` /
  `counts` / `papers`. Any consumer iterating one shape breaks on the
  other.
- **(iii) Scorer emits 12 fields in daily mode, 6 in historical
  mode** — the schema gap documented in ADR-0014 §5(b). Root cause is
  that the active `SCORER_PROMPT_FILE` differs by default between the
  two modes (daily uses `scorer_v3.txt` via the workflow env pin,
  historical defaults to `scorer_v1.txt`).

Concrete evidence from Phase C: of the 150 papers dated `2024-01-01`
in `data/historical/2024-01.json`, **138 are OpenAlex month-precision
fallbacks**, not actual New Year's Day publications. The current data
model gives a downstream consumer no way to distinguish these.

These three mismatches share a common downstream cost: any code that
walks the corpus end-to-end (calendar rendering, lit-system handoff,
search indexing) has to special-case the run mode, and any view that
groups papers by date is silently wrong for ~30% of OpenAlex hits. The
fix is one coordinated schema change.

---

## 2. Goals

In priority order:

- **(a) Unify the `date` field semantics** across all three sources,
  with explicit precision metadata so downstream consumers can decide
  whether to trust the day component.
- **(b) Reorganize the file scheme** so all paper JSON files use
  publication-date filenames in a single `data/daily/` directory —
  removing the daily-vs-historical directory split entirely.
- **(c) Unify the scorer output schema** so daily and historical
  produce identical field sets, closing the ADR-0014 §5(b) gap.
- **(d) Build a calendar view** on the docs site that lets the user
  browse all papers by publication date, exploiting (a) and (b).

---

## 3. Non-goals

This ADR does **not** propose:

- Any change to the existing direction routing logic
  (`pipeline/direction_router.py` or `config/directions.yaml`).
- Any change to the `scope_audit` rules or its allowed-imports list.
- Any change to the `export_candidates` handoff schema **beyond field
  additions** (new fields on each candidate are in scope; removing or
  renaming existing fields is not).
- Any change to how lit-system consumes the `candidates.jsonl`
  handoff. The Radar→lit-system contract from `SCOPE.md` is held
  intact; lit-system continues to receive the same shape it does
  today, plus optional new fields it can ignore.

---

## 4. Decisions

### 4.1 `date` field semantics

Adopt **option 1.a**: fetchers populate a best-effort publication date
string in `YYYY-MM-DD` format plus a new sibling field
`date_precision: "day" | "month" | "year"`. Month-precision papers
fill `day=01`; year-precision papers fill `month-day=01-01`. The
precision field tells downstream consumers what to trust.

Per-source rules:

- **OpenAlex fetcher** inspects the actual API response. If
  `publication_date` carries a day component, use it with
  `precision=day`. If only year + month are present, use
  `precision=month` with `day=01`. If only year is present, use
  `precision=year` with `month-day=01-01`.
- **arXiv fetcher** uses the **v1 submission date** specifically (the
  paper's first appearance on arXiv) and always emits `precision=day`.
  *Implementation flag:* whether the current
  `result.published.date()` returns v1 or latest-revision date
  requires source-code verification during implementation. If it
  returns latest-revision, the fetcher must switch to whichever
  `arxiv` library field gives v1 — see §7(i).
- **PubMed fetcher** uses **EDAT** (Entrez Date — when the record
  entered PubMed) and always emits `precision=day`. EDAT is
  imperfect as a publication date but it is the only field PubMed
  reliably returns at day precision; documenting this trade-off here
  rather than papering over it.

### 4.2 File scheme

Adopt **option 2.c**: all paper JSON files live in
`data/daily/YYYY-MM-DD.json` where the filename is the **paper's
publication date**, not the radar discovery date.

Migration step **A.1** applies: existing `data/daily/*.json` files
(which currently use radar-discovery-date naming) and the Phase C
`data/historical/2024-01.json` file are redistributed paper-by-paper
into the new filename scheme based on each paper's `date` field. The
old `data/historical/` directory and its gitignore entries are removed
once migration completes.

### 4.3 Discovery log

The old discovery-date filenames carried real information — *when did
radar first observe this paper* — that publication-date filenames
discard. To preserve it, add a sibling directory:

```
data/discovery_log/YYYY-MM-DD.json
```

Each file contains minimal records of the form:

```json
{
  "doi_or_arxiv_id": "...",
  "first_seen_at": "2026-05-14T22:21:03Z",
  "run_type": "daily" | "historical_backfill"
}
```

— one line per paper observed in the run, regardless of whether the
paper was already known. This is a separate concern from the paper
data itself and lives in its own directory.

### 4.4 Dedup across runs

Paper identity key is `doi or arxiv_id` (DOI preferred; arXiv ID is
the fallback for preprints with no DOI yet — matches the existing
`doi:` prefix convention from `CLAUDE.md` §4).

When the same paper appears in multiple radar runs (e.g. once in a
daily run, once in a historical backfill), the paper JSON in
`data/daily/<publication_date>.json` is **written once on first
observation**; subsequent observations only append to the discovery
log. The paper record gains a `first_seen_at` field set on first
write, frozen thereafter.

### 4.5 Top-level JSON schema

Unify to the dict form currently used by historical:

```json
{
  "schema_version": "v2",
  "date": "YYYY-MM-DD",
  "date_precision": "day" | "month" | "year",
  "papers": [...],
  "counts": {...}
}
```

Daily flat-list files migrate to this format. The `counts` dict
mirrors historical's structure: `fetched_total` / `by_source` /
`after_dedup` / `after_routing` / `by_direction` / `routed_by_source`
/ `scored` / `priority_counts`.

### 4.6 Scorer output schema

Adopt **option 3.a**: historical scorer migrates to `scorer_v3.txt`
to align with daily.

Per migration constraint **B.3**: Phase C's existing `2024-01.json`
(scored under v1) is **not** re-scored. During migration, the
v1-scored papers gain a `scorer_version: "v1"` field, and the
v3-only fields (`relevance_level`, `read_action`, `why_not_core`,
`validation_kind`, `summary_en`, `key_terms` — see ADR-0014 §5(b))
are emitted as `null`. Going forward, all runs use v3 and emit
`scorer_version: "v3"`.

Downstream HTML render must tolerate `scorer_version: "v1"` papers
gracefully: show what's available, omit v3-only sections rather than
rendering empty placeholders.

### 4.7 Calendar view

Add `docs/calendar.html`: a year/month grid where each cell is a
publication date and clicking opens that date's paper list.

- **Day-precision papers** (`date_precision == "day"`) appear in
  their actual day cell.
- **Month-precision papers** (`date == YYYY-MM-01` with
  `precision == "month"`) cluster on day 1 of their month with a
  visible `"month-precision, N papers"` label so they are visually
  distinct from genuine `YYYY-MM-01` publications. This directly
  addresses the 138/150 problem from §1.
- **Year-precision papers** (`precision == "year"`) get a separate
  "year-only" bucket per year, outside the month grid.

The existing `docs/daily.html` stays but its meaning shifts from
"papers discovered today" to "papers published today (and routed in
by radar)". The existing `docs/search.html` stays and gains a
`date_precision` filter so users can exclude month/year-precision
results when wanting day-accurate views.

---

## 5. Migration plan

Five steps, in order:

### 5.1 Archive the v1 data

Move `data/daily/*.json` and `data/historical/*.json` to
`data/_archive_v1/` (preserving the original directory structure
under the archive root). Add `data/_archive_v1/` to `.gitignore`. The
archive is the rollback target (§9) and the input to step 5.2.

### 5.2 Write `scripts/migrate_to_schema_v2.py`

Read the archived files, redistribute papers by publication date,
write new v2-schema files into `data/daily/`. Each migrated paper
gets:

- `schema_version: "v2"`
- `date_precision` **inferred** from the old date string: any
  `day != 01` implies `precision=day` (genuine day-precise
  publication); `day == 01` is conservatively treated as
  `precision=month` for ALL sources, not just OpenAlex. *Caveat:*
  this is a lossy inference for old data — papers genuinely
  published on the 1st of a month will be mis-tagged as
  month-precision. The reverse error (silently treating a
  month-fallback as day-precision) is judged worse because it
  propagates invisibly downstream, whereas a month-precision
  mis-tag is explicit and surfaces in UI filters. Document this
  trade-off in the migration script's docstring and in the v1→v2
  changelog entry.
- `scorer_version` set to `"v1"` for Phase C papers, and to whatever
  the actual prompt version was for daily papers. *Implementation
  flag:* the daily prompt version requires verification — likely the
  `SCORER_PROMPT_FILE` env in `.github/workflows/daily.yml` is
  authoritative, but historic workflow runs may have used different
  values; check `git log` on the workflow file before assuming
  uniformity.

### 5.3 Update fetchers to emit v2 schema natively

Modify `arxiv_fetcher.py`, `openalex_fetcher.py`, `pubmed_fetcher.py`
so fresh runs produce v2 directly (no migration step on new data). No
behavior change to direction routing or scoring beyond adding
`date_precision` to each paper record.

### 5.4 Update HTML renderers

Update `docs/daily.html` and `docs/search.html` to consume the v2
dict-shaped JSON. Add the new `docs/calendar.html`. All renderers
must tolerate `scorer_version: "v1"` papers (see §4.6).

### 5.5 Verify

- `scope_audit` must remain at 0/0 violations.
- Existing pytest suite must pass unchanged.
- New tests added for v2 schema invariants: every paper has
  `date_precision`, every file's filename matches its `date` field,
  every paper has either DOI or arXiv ID, `scorer_version` is one of
  `{"v1", "v3"}`.

---

## 6. Breaking changes

What breaks for existing consumers, by category:

- **(a) `data/daily/YYYY-MM-DD.json` filename semantics change.** Old
  consumers expecting "papers fetched on this date" will now see
  "papers published on this date". A consumer reading
  `data/daily/2026-05-14.json` to get yesterday's radar-run output
  will instead get papers published on 2026-05-14, which may include
  zero papers from yesterday's run.
- **(b) Top-level JSON shape changes from list to dict.** Any
  consumer doing `papers = json.load(f)` and iterating directly
  breaks; the new form requires `json.load(f)["papers"]`.
- **(c) Scorer output may have null fields for Phase C papers.**
  Consumers must handle `field is None` for the six v3-only fields
  on records where `scorer_version == "v1"`.
- **(d) `data/historical/` directory removed.** Any path string
  referencing it (in code, configs, workflows, or docs) breaks.

Affected consumers — must be updated in lockstep with the migration:

- `pipeline/export_candidates.py` — reads daily/historical JSON,
  produces `candidates.jsonl`. Both shape change (b) and path change
  (d) hit it.
- `pipeline/search_index_builder.py` (or wherever
  `data/exports/search-index.json` is generated — locate during
  implementation if that filename is wrong) — same shape and path
  concerns.
- `docs/daily.html` — shape change (b), filename-semantics change (a).
- `docs/search.html` — shape change (b), needs the new
  `date_precision` filter from §4.7.
- `.github/workflows/daily.yml` — any path references to
  `data/historical/` or any logic that assumes a single-file daily
  output (the new scheme writes to one file per publication date the
  run touched — see §7(iv)).
- Any documentation referencing the old paths: `README.md`,
  `SCOPE.md`, `TODO.md`, prior ADRs (left as-is for historical
  accuracy; new ADRs reference v2 paths).

---

## 7. Open implementation questions

Five questions deferred to implementation time:

- **(i) arXiv v1 vs. latest-revision date.** Does the current arXiv
  fetcher's `result.published.date()` return v1 or latest? Source-code
  verification required before deciding whether arXiv handling needs
  further changes beyond §4.1's stated intent.
- **(ii) Commit policy for `data/discovery_log/`.** Should these
  files be committed to git, or gitignored? Leaning gitignored — they
  are append-only run records and the per-paper `first_seen_at`
  field on the paper itself is the durable record — but bears
  discussion. Either way the `data/_archive_v1/` precedent (§5.1) of
  gitignoring regenerable artifacts applies.
- **(iii) Per-source date precedence on conflict.** When multiple
  sources return the same paper with different publication dates
  (e.g. OpenAlex says 2024-01-15, PubMed says 2024-01-22 for the
  same DOI), the resolution rule is deferred to implementation.
  Note that this is a question about which source is most reliable
  *for the publication-date field specifically*, distinct from
  overall source quality. ADR-0013's finding that arXiv is
  low-precision-high-recall applies to routing, not to date-field
  semantics. Plausible heuristics to evaluate during
  implementation: prefer day-precision over month-precision when
  one source has each, prefer OpenAlex's `publication_date` (when
  at day-precision) over PubMed's EDAT (entry-date, not
  publication-date), use arXiv's `published.date()` only after
  §7(i) verifies its semantics. Decide after surveying a sample of
  conflicting records from the migrated corpus rather than
  committing to a precedence rule now.
- **(iv) Daily workflow with multi-file writes.** The daily workflow
  has a 14-day OpenAlex lookback. Under v2, papers from 14 different
  publication dates land in 14 different files in one run. Need to
  verify the commit step in `.github/workflows/daily.yml` handles
  multi-file diffs cleanly (it currently assumes a single
  `data/daily/<today>.json` write). Per `CLAUDE.md` §6 the user owns
  workflow edits, so this is a design check, not an autonomous fix.
- **(v) Calendar view rendering scale.** Does `docs/calendar.html`
  need lazy-loading for large date ranges, or can it render the full
  10-year backfill window inline? Decide once a realistic upper
  bound on per-cell paper count is known from the migrated corpus.

---

## 8. Estimated implementation scope

Phased work, no hour estimates:

- **Phase 1 — fetchers.** 3 files: `arxiv_fetcher.py`,
  `openalex_fetcher.py`, `pubmed_fetcher.py`. Plus tests.
- **Phase 2 — scorer schema unification.** Set `SCORER_PROMPT_FILE`
  default to `scorer_v3.txt` in `llm_scorer.py`, `manifest.py`,
  `conftest.py`, and `README.md`.
- **Phase 3 — write `scripts/migrate_to_schema_v2.py`** and run it
  on the archived data from §5.1.
- **Phase 4 — search index builder + HTML render changes.** Update
  `daily.html`, `search.html`; add new `calendar.html`.
- **Phase 5 — workflow verification.** `.github/workflows/daily.yml`
  exercised with the new file scheme — owned by the user per
  `CLAUDE.md` §6.
- **Phase 6 — `scope_audit` + pytest regression.**

---

## 9. Rollback plan

The archived v1 data at `data/_archive_v1/` is preserved indefinitely
(not regenerated, not pruned). Rollback is therefore:

1. `git revert` the implementation commits.
2. Restore `data/daily/` and `data/historical/` from
   `data/_archive_v1/`.

No live data is destroyed at any point in the migration; the worst
case is that v1 consumers see the v2 schema until rollback completes.

---

## 10. Decision finalization

This ADR was approved on 2026-05-14. Status converted from DRAFT to
Accepted, filename dropped the DRAFT prefix. The five
implementation-time flags in §7 remain deferred to their respective
implementation phases (see §8) and are not resolved by this approval
— they will be addressed in the commits that close out each phase.

---

## Related

- ADR-0013 — Phase B source precision/recall asymmetry (the
  per-source retention numbers that motivated thinking about source
  semantics in the first place)
- ADR-0014 — Phase C scoring baseline (§5(b) is the schema-gap
  finding this ADR closes)
- commit `9716068` — DeepSeek `deepseek-chat` → `deepseek-v4-flash`
  migration (relevant to §4.6's `scorer_version` provenance)
- `data/historical/2024-01.json` — Phase C scored output, the
  138/150 OpenAlex month-fallback evidence in §1
- `pipeline/run_historical.py` — historical-mode runner, will emit
  v2 directly after Phase 1
- `pipeline/export_candidates.py` — primary downstream consumer
  affected by §6
- `SCOPE.md` § "The Radar to lit-system contract" — the contract
  this ADR holds intact (per §3)
- `CLAUDE.md` § 1 "Optimization function: recall, not precision" —
  v2 changes nothing about recall optimization
- `CLAUDE.md` § 4 "Data-integrity guardrails come before features" —
  the migration plan in §5 and rollback in §9 honor this
- `CLAUDE.md` § 6 "Should / Shouldn't" — workflow file edits in §7(iv)
  and Phase 5 are user-owned, not autonomous
