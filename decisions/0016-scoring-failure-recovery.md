# ADR-0016: Scoring failure recovery — capture raw responses, raise max_tokens cap

**Status**: Accepted
**Accepted-by**: Weikang Sun on 2026-05-15 after review by Web Claude
**Date**: 2026-05-15
**Author**: Weikang Sun
**Related**: ADR-0014 (Phase C LLM scoring baseline), CLAUDE.md §4 (data-integrity guardrails), CLAUDE.md §1 (recall over precision)

---

## Context

A `data/daily/*.json` audit on 2026-05-15 showed that **246 of 939 scored papers (26.2 %) carry `llm.priority_reason` strings beginning with `"scoring failed: …"`**, and all 246 are silently downgraded to `priority = "Low"` by the fallback branch in `pipeline/llm_scorer.py:score_batch`.

The failure-mode breakdown is overwhelmingly Python `json` decoder errors:

| Count | Failure mode (truncated) | Interpretation |
|---|---|---|
| 23  | `Expecting property name enclosed in doub…` | JSON ends mid-key (truncated property name) |
| 22  | `Expecting value: line 1 column 1 (char 0)` | empty completion (different bug class) |
| 12  | `Unterminated string starting at: line 25` | truncated string value in a deeply nested field |
| 8   | `Unterminated string starting at: line 24` | same class |
| 7   | `Unterminated string starting at: line 23` | same class |
| 7   | `Unterminated string starting at: line 7`  | truncated earlier in the response |
| ... | (further `Unterminated string` cases)       | all same class |

Distinct sub-causes:

1. **Truncation (~93 % of failures)** — the model emits structurally valid JSON until it hits a token cap, then the response is cut off inside a quoted string or property name. The cap in `pipeline/llm_scorer.py:58` is hardcoded at `max_tokens=800`. `prompts/scorer_v3.txt` (4 799 bytes, 97 lines) asks for **14 top-level fields** including two four-key nested summary objects (`summary_zh`, `summary_en`) and a list of 5–10 EN-ZH `key_terms` pairs. A complete schema-conforming response budgets at ~650–800 tokens including JSON whitespace under DeepSeek's pretty-printed `response_format=json_object` mode. Papers with a long `why_not_core` sentence, denser `key_terms`, or `summary_zh` running to the 40-char ceiling routinely exceed the cap.

2. **Empty completion (~22 cases, 9 %)** — the API returned a blank response. This is a distinct upstream bug (API error path, billing fallback, content filter, or transport hiccup) and is **not** fixed by this ADR.

A second, compounding problem: `score_batch` discards the raw LLM text on failure. `raws.append({})` on the except branch loses `resp.choices[0].message.content`, so the 246 historical failures cannot be diagnosed further without re-running each paper. This is a violation of the spirit of CLAUDE.md §4 data-integrity guardrails (the run produced output that "succeeded" structurally but lost information needed to audit it).

This ADR captures the two minimum fixes needed to (a) unblock the largest failure class and (b) make the remaining failure class debuggable without re-running.

---

## Decision

Two fixes, both in `pipeline/llm_scorer.py`. Nothing else changes — the prompt is **not** modified (per CLAUDE.md §4, scorer prompts are versioned; bumping to `scorer_v4.txt` would be a separate ADR).

### Fix 1 — Raw-response logging on failure

When `json.loads(resp.choices[0].message.content)` fails inside `score()`, attach the raw text to the exception and re-raise. In `score_batch`'s except block, call a best-effort `_log_scoring_failure(paper, raw_response, exc)` helper that writes:

```
data/llm_cache/failures/YYYY-MM-DD_<doi-slug>.json
```

Slug = DOI with `/` → `_` (so `10.3390/polym17070917` → `10.3390_polym17070917`). Fallbacks: `arxiv_id`, then `paper["id"]`, then `"noid"`.

Payload fields: `timestamp_utc`, `doi`, `arxiv_id`, `title` (truncated to 300), `direction`, `direction_name`, `error_class`, `error_message`, `raw_response`, `raw_response_captured` (bool — false for pre-`resp` errors like network failures), `model`, `prompt_file`.

**Append-only**: if a file already exists for the same (date, DOI) — i.e. the same paper failed twice in one day — a counter suffix `_1`, `_2`, … is appended so prior payloads are never overwritten.

The logger is wrapped in a bare `try / except: return None` so a filesystem error never breaks the scoring loop. Logging is observability, not load-bearing.

### Fix 2 — env-overridable `max_tokens`, default raised to 2000

```python
max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000"))
```

Rationale for 2000: a 14-field schema with 5–10 `key_terms` pairs and DeepSeek's pretty-printed JSON-mode whitespace consumes ~650–800 tokens at the median; outliers go to ~1200–1500. 2000 leaves ~30 % headroom while staying well below DeepSeek-v4-flash's per-call context budget, and the daily cost impact is bounded by the fact that successful responses naturally stop emitting tokens once the JSON closes.

`.github/workflows/daily.yml` is **not** edited (CLAUDE.md §6, user-owned). The workflow currently sets no `LLM_MAX_TOKENS` env var, so the new 2000 default takes effect automatically on the next CI run. If we later want a CI-specific override, the user adds it manually.

---

## Rationale

### Why raise the cap rather than tighten the prompt

The scorer prompt explicitly asks for both Chinese and English summaries, plus 5–10 key-term pairs. The recall-first calibration in CLAUDE.md §1 ("not miss valuable papers") plus the fact that 26 % of papers were being silently mis-prioritised both argue for fitting the prompt, not the other way around. Trimming the schema (e.g., dropping `summary_en` or `key_terms`) would be a downstream-visible behaviour change that should ride on its own ADR + new `scorer_v4.txt`, not be smuggled in as a "bug fix."

### Why best-effort, not load-bearing, failure logging

A filesystem error in the failure logger should not turn a single bad paper into a batch-level failure. The cost of losing one raw response (it can be regenerated by re-scoring) is far smaller than the cost of breaking the daily run.

### Why a `_1`, `_2` counter suffix rather than JSON-lines append

Per-paper files are easier to grep, diff, and selectively re-process. JSON-lines would mean the entire day's failures must be parsed to extract one paper. Same-DOI-twice-in-one-day is rare enough that the counter suffix is acceptable.

### Why no prompt bump

CLAUDE.md §4: "Scorer prompts are versioned (`prompts/scorer_vN.txt`) and never overwritten. A change means a new vN+1 file." This ADR changes only the calling code's max-token budget and failure-handling — the prompt text is identical to v3. No new version warranted.

---

## Consequences

### Positive
- Truncation-class failures (currently ~93 % of all failures) should drop to ~0 % on the next daily run, raising effective recall by ~25 percentage points without touching any other component.
- All future failures are forensically inspectable from the working tree (no need to re-run or look at OpenAI/DeepSeek dashboards).
- Backward compatible: the schema of `data/daily/*.json` is unchanged; only a new sibling directory `data/llm_cache/failures/` appears.

### Negative
- Per-call cost rises modestly (output tokens billed) but only when the model would have been truncated anyway — i.e., this is paying for tokens we previously wasted by discarding the output.
- A new directory (`data/llm_cache/failures/`) needs gitignore consideration. Per CLAUDE.md, daily runs are not committed but the structure should probably be ignored — to be decided when promoting this ADR to Accepted.

### Risks
- The 22 "empty completion" failures are **not** fixed. They will now write a failure log file with `raw_response: null` and `raw_response_captured: false`, which is the desired observable but does not change paper priority. A follow-up ADR may be needed once the captured logs reveal the upstream cause.
- DeepSeek-v4-flash latency increases slightly with longer `max_tokens` when the API streams; daily-run wall time should be monitored on the first post-fix run.

---

## Follow-up TODO

1. **Retry the 246 historically failed papers.** Build a one-shot script (e.g., `scripts/retry_failed_scoring.py`) that:
   - Enumerates `data/daily/*.json`
   - Selects papers where `llm.priority_reason` starts with `"scoring failed:"`
   - Re-invokes `llm_scorer.score()` on each
   - Writes back `llm.*` in place on success; on persistent failure, leaves the existing entry and lets the new failure-log path capture the raw text.
   - Updates `data/manifests/<today>.json` with a `retry_run` flag.

   Decision needed before running: which historical date snapshots get retroactive priority updates? The recall-correct choice is "all of them," but the user should sign off — overwriting historical state slightly muddies time-series analytics.

2. **Triage the empty-completion class** once the new failure logs surface 1–2 fresh examples. Likely candidates: DeepSeek content filter, billing fallback, transient API errors.

3. **CHANGELOG.md entry** capturing this ADR's acceptance and the max_tokens=2000 + failure-logging changes (prompt text unchanged at scorer_v3.txt), per CLAUDE.md §4.

4. **TODO.md Decision Log row** with date, decision summary, and link back to this ADR, per CLAUDE.md §5.

5. **gitignore decision** for `data/llm_cache/failures/`. Probably ignore — these are debug artefacts, not part of the daily-manifest contract.

---

## Status notes

- Accepted 2026-05-15 — code changes landed in the working tree pending commit. Next step is committing pipeline/llm_scorer.py + this ADR + .gitignore together. Follow-up TODO: retry script for the 246 historical scoring-failed papers from data/daily/.
- The PROMPT version (`scorer_v3.txt`) is unaffected.
- Empty-completion failures (22 cases) acknowledged but explicitly deferred to a separate ADR once their raw responses have been captured.
