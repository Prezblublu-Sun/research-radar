# ADR-0014: Phase C LLM scoring baseline (2024-01)

**Status**: Accepted
**Date**: 2026-05-14
**Decision-maker**: Weikang Sun
**Cross-reference**: `pipeline/run_historical.py`; commit `9716068`
(DeepSeek model migration); `prompts/scorer_v1.txt`;
`data/historical/2024-01.json`; ADR-0013 (Phase B source asymmetry)

---

## 1. Context

Phase C of the C0 PoC plan was the first non-dry-run invocation of
`pipeline/run_historical.py`. It scored January 2024's 495 routed
candidates (the same set characterized in ADR-0013) against the live
DeepSeek API. Two purposes:

- **Validate** that the full historical-mode pipeline end-to-end
  produces lit-system-handoff-ready JSON — i.e. that the runner's
  fetch → dedup → route → score → write loop actually completes against
  a paid API at month scale, not just in dry-run.
- **Establish a baseline** for what fraction of monthly candidates
  survive scoring at High or Medium priority. Until now we had per-source
  retention numbers (ADR-0013) but no measurement of post-LLM yield.

This was also the first run after the DeepSeek model migration in
commit `9716068` (`deepseek-chat` → `deepseek-v4-flash`, ahead of the
2026-07-24 retirement of the old endpoint), so the run doubled as a
smoke test that the new model returns parseable schema-conformant
output at scale.

---

## 2. Run configuration

- **Model**: `deepseek-v4-flash` (non-thinking mode)
- **Scorer prompt**: `prompts/scorer_v1.txt` — the default. The `v2`
  and `v3` variants exist in `prompts/` but require an explicit
  `SCORER_PROMPT_FILE` env var override, which was not set for this
  run.
- **Window**: 2024-01-01 → 2024-01-31
- **Output path**: `data/historical/2024-01.json`
- **Wall time**: approximately 44 minutes — roughly 6–7 minutes for
  fetching (matching the Phase B dry-run profile in ADR-0013), the
  remainder spent in LLM scoring.

---

## 3. Observed counts

Priority distribution over the 495 scored papers:

| Priority | Count | % of 495 |
|----------|------:|---------:|
| High     |     2 |     0.4% |
| Medium   |    57 |    11.5% |
| Low      |   245 |    49.5% |
| Exclude  |   191 |    38.6% |
| **High + Medium** | **59** | **11.9%** |

`scored == after_routing == 495` — zero papers dropped between routing
and scoring. Every routed candidate received a priority label.

---

## 4. Quality spot checks

**High-priority papers (n=2):** both were direct hits on research-core
topics, not noise.

- Paper 1: an SLM gradient-porosity Ti-15Mo corrosion fatigue study,
  aligned with the `am_biomedical` direction and with the daily-mode
  DLP gradient TPMS interest.
- Paper 2: a finite-element analysis of hip-implant failure mechanisms,
  aligned with the `hip_implant` direction.

**Medium-priority sample (n=5):** the `priority_reason` field carried
coherent, content-specific judgments — naming concrete gaps such as
lack of biomechanical context, missing experimental validation, and
missing UQ — rather than generic "moderate relevance" boilerplate.
This indicates the scorer is making real content judgments and not
just topic-matching against the routing keywords that already got the
paper here.

---

## 5. Findings worth flagging

### (a) Scorer schema actually emitted

For each paper, the historical-mode scorer emitted:

- `priority`
- `priority_reason`
- `summary_zh` — a structured dict with `motivation` / `method` /
  `result` / `validation`
- `tags`
- `flags` — a four-boolean dict
- `relevance_to_user`

This is sufficient for lit-system pre-ingest triage at the candidate
boundary defined in `SCOPE.md`.

### (b) Daily-mode schema has fields that historical mode does not emit

The daily-mode pipeline emits additional fields not present in this
Phase C run, listed below. Whether these fields come from a different
active prompt (daily may run under a different `SCORER_PROMPT_FILE` env
via GitHub Actions), a post-processing step downstream of the scorer,
or model-behavior differences between the `deepseek-chat` alias daily
historically used and the explicit `deepseek-v4-flash` used here is not
investigated in this ADR — it is a question for §6.

- `relevance_level`
- `read_action`
- `why_not_core`
- `validation_kind`
- `summary_en`
- `key_terms`

These are HTML-render-side fields used by the daily site and are not
required by the lit-system handoff. Their absence in historical mode is
not blocking, but it is a quiet schema difference between the two run
modes worth tracking — anyone diffing daily JSON against historical JSON
will see it.

### (c) Active prompt vs. newest prompt

`scorer_v1.txt` is the active prompt by default for historical mode,
while `scorer_v3.txt` is the newest version present in `prompts/`.
Whether to migrate the historical-mode default to `v3` (which would
also pull in the daily-mode-only fields above) is open and is **not**
decided here.

---

## 6. Open items deferred

- **Re-run Phase C with `scorer_v3.txt`** to compare priority
  distributions against the v1 baseline established here. Without the
  comparison there is no way to tell whether v3's added fields shift
  the `High` / `Medium` / `Low` / `Exclude` split or just add output
  columns.
- **Whether the daily-vs-historical schema difference should be
  unified** (see §5(b) and §5(c)). Decision deferred until a second
  month is scored, so the choice isn't made on n=1.
- **Calibrating the Medium-vs-Low boundary** across more months once
  Feb/Mar 2024 data exists. With a single month, 11.9% High+Medium
  yield is a data point, not a baseline; cross-month variance is
  unknown.
- **Investigate the source of the daily-vs-historical schema gap**
  flagged in §5(b) — whether it is prompt-version-driven,
  post-processing-driven, or model-behavior-driven. Until this is
  known, the §6 bullet about unifying the schema cannot be acted on
  responsibly.

---

## Related

- `pipeline/run_historical.py` — runner used for this Phase C run
- `prompts/scorer_v1.txt` — active prompt for this run
- `prompts/scorer_v3.txt` — newest version, not used here
- `data/historical/2024-01.json` — full scored output (gitignored;
  regenerable artifact)
- `data/historical/2024-01_summary.json` — committed counts-only
  summary, the durable PoC baseline future work can diff against
- ADR-0013 — Phase B source precision/recall asymmetry (same 495
  routed candidates, pre-scoring view)
- commit `9716068` — DeepSeek `deepseek-chat` → `deepseek-v4-flash`
  migration, in effect for this run
- `SCOPE.md` § "The Radar to lit-system contract" — defines what the
  scored handoff JSON must contain
- `CLAUDE.md` § 1 "Optimization function: recall, not precision" —
  frames why High+Medium yield matters less than not-missing
