# CLAUDE.md — Research Radar

Guidance for Claude Code working in this repository. Read this before
proposing or making changes. Sources of truth: `SCOPE.md`, `TODO.md`,
`README.md`. If those conflict with this file, they win — and this file
should be updated.

---

## 1. Optimization function: recall, not precision

Radar's job is to **not miss valuable papers**. The LLM scorer is trusted
to grade noise correctly downstream.

- Prefer 80 candidates @ 40% relevance + accurate LLM grading over
  19 candidates @ 90% relevance.
- DeepSeek cost of ¥0.5–2/day is explicitly acceptable. Cost-saving is
  **not** a valid justification for cutting recall.
- Do **not** propose tightening `must_pair_with`, adding restrictive
  routing rules, or adding broad `negative_keywords` to "reduce noise."
- "Adjacent-field inspiration" counts as value (e.g. clinical hip
  papers offering methodological hints, generic ML papers transferable
  to surrogate modelling).
- When tuning, the question is "are we recalling enough?", not
  "are we showing too much?".

See: `TODO.md` § "2026-05-13 优化方向校准".

---

## 2. Scope boundary — the SCOPE.md contract

Radar is the **discovery layer**. lit-system is the **deep-parsing /
RAG layer**. The handoff is a file: `data/exports/candidates.jsonl`
(planned W2.3). Radar guarantees DOI-keyed, relevance-filtered
candidates; lit-system owns everything past that.

**Never propose adding** any of these to Radar:

- PDF download / parsing (Docling, GROBID, pypdf, MinerU, etc.)
- OCR, equation/figure/table extraction
- Chunking, embeddings, vector stores (Chroma, Qdrant, FAISS)
- RAG, knowledge graphs, citation-graph analysis
- Cross-paper synthesis outside the review-loop layered chain (per-paper → weekly → monthly → quarterly → annual; ADR-0026)
- Personalization, feedback loops, active learning, re-ranking
- Chat-with-papers, conversational UI
- Curation/annotation web UI on deep-parsed PDFs (lit-system territory)
  (NOTE 2026-05-19: client-side marks+notes on the Radar browse surface
  are permitted per ADR-0016. They are a human-curation aid distinct from
  lit-system's automatic machine annotation of PDFs.)

If a feature touches any of the above, it belongs in lit-system — reject
or redirect.

See: `SCOPE.md`.

---

## 3. Rejected suggestions — do not re-propose

These were already considered and rejected (see `TODO.md` § "明确不做"
and the 2026-05-12 audit). Do not surface them again unless the user
explicitly reopens the question:

- A 5th "Very High" priority tier (4 tiers is enough).
- Auto-downloading OA PDFs (conflicts with Zotero quota; manual
  "Find Available PDF" in Zotero is preferred).
- Run modes beyond `--force`, `--skip-zotero`, and a date arg.
- One-shot 100-paper ground-truth set; the plan is the incremental
  10-paper `tests/eval_set.yaml`, growing weekly.
- Hiding abstracts on the public page (the site already only shows
  LLM-rewritten Chinese summaries, not original abstracts).
- Finer Zotero-sync tiers before real usage data justifies them.
- Productization: subscribers, mobile app, UI polish, login,
  themes, "open source it." Not until thesis is done.

**Single criterion for any new feature:** does it shorten
"see paper → decide whether to read" for the user? If not, reject.

---

## 4. Data-integrity guardrails come before features

The 2026-05-12 incident — an Actions empty-run overwrote 298KB of valid
daily JSON with 2 bytes — shapes priorities. When choosing between
shipping a feature and hardening the pipeline, harden.

Respect and preserve these guardrails:

- Empty-run gate in `_save_daily`: reject `fetched_total == 0`,
  reject overwriting N papers with 0, flag suspicious payloads <1KB.
- Zotero sync audit log at `data/zotero_sync_log/YYYY-MM-DD.jsonl`
  (one line per item, with `target_collection` + `status` + `error`).
- `run_status` and `quality_flags` fields in the daily manifest.
- DOI-only strict dedup. No fuzzy dedup — too many edge cases.
  The dedup key format is `doi:10.xxxx/...` with the `doi:` prefix —
  not the bare DOI. This tripped W1.4 testing.
- Scorer prompts are versioned (`prompts/scorer_vN.txt`) and
  **never overwritten**. A change means a new `vN+1` file.
  Current active prompt: `prompts/scorer_v3.txt` (4 fields added on
  2026-05-13: `relevance_level`, `read_action`, `why_not_core`,
  `validation_kind`). The workflow `.github/workflows/daily.yml` pins
  `SCORER_PROMPT_FILE: scorer_v3.txt`. When the user asks to "iterate
  on the scorer," create `scorer_v4.txt` — do not edit v3.
- Every run writes `data/manifests/YYYY-MM-DD.json`; config/prompt
  changes update `CHANGELOG.md`.

---

## 5. How to evaluate proposals and changes

Before suggesting a change:

1. Check `SCOPE.md` § "What Research Radar is NOT" — if it touches that
   list, reject.
2. Check `TODO.md` § "明确不做" — if already rejected, do not re-propose.
3. Prefer **data-driven** tuning ("let it run 2 weeks, then decide")
   over speculative design. Most Tier 2 items in `TODO.md` are
   explicitly gated on real usage data.
4. For substantive architectural changes, add a row to the Decision Log
   table in `TODO.md` with date, decision, and reason.
5. Avoid "full project review" framing. The 2026-05-12 audit lesson:
   LLM-generated broad reviews tend to invent facts ("Docling
   module", "Very High tier"), over-plan, and substitute generic best
   practices for project-specific reasoning. Respond to specific code
   with specific problems.

---

## 6. What Claude Code should and shouldn't do in this repo

### Should

- **Bug hunting** in the pipeline: heredoc/quoting issues, `nonlocal`
  scoping bugs, dedup-key correctness, manifest-write races,
  silent-failure paths, off-by-one in date handling.
- **Helper scripts** that support scope discipline or auditing —
  e.g. `scope_audit.py`-style tools that check the codebase against
  `SCOPE.md` boundaries, or one-off backfill/inspection scripts.
- **Draft ADRs / Decision Log entries** for substantive changes, then
  let the user paste them into `TODO.md`.
- **Local dry-runs**: `python -m pipeline.run_daily 1 --skip-zotero` is safe and encouraged when validating a change.
- **Read** any file freely; **edit** code, prompts, and configs when
  asked, following the versioning rules in §4.

### Shouldn't

- **Don't edit `.github/workflows/*.yml`** without an explicit ask.
  CI changes can silently break the daily run; the user must own them.
- **Don't edit `TODO.md` § "2026-05-13 优化方向校准"** (the recall-vs-
  precision declaration). That section is a user-authored calibration
  statement; propose changes in chat instead.
- **Don't run the production pipeline** (`python -m pipeline.run_daily`
  without `--skip-zotero`, manual Actions triggers, Zotero writes,
  monthly-archive runs). Those touch shared state — Zotero, GitHub
  Pages, Releases — and must be user-initiated.
- **Don't overwrite a versioned scorer prompt.** Create
  `prompts/scorer_vN+1.txt`; never edit `scorer_vN.txt` in place.
- **Don't `git push`, force-push, amend pushed commits, or open/close
  PRs/issues** without explicit instruction.
- **Don't add dependencies** that imply scope drift (PDF parsers,
  vector DBs, queue/broker libs, web frameworks).

---

Last reviewed: 2026-05-14.
