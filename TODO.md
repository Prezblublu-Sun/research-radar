# Research Radar — TODO & 备忘录

Operational guide for the project. Structural concerns (sustainability,
extensibility, traceability) are addressed in README's version governance
section. This file is about operations: configuration, monitoring,
long-term maintenance, and discipline.

Organized in three tiers by urgency:

- **Tier 1**: Must-do before launch (small effort, prevents disasters)
- **Tier 2**: Within 2-4 weeks of launch (based on real usage data)
- **Tier 3**: Long-term vigilance, mostly discipline rather than action

---

## Tier 1 — Pre-launch (about 1 hour total)

### T1.1 Secret leak prevention  ~15 min

- [ ] `.gitignore` includes `.env`, `*.key`, `.venv/`, `__pycache__/`
- [ ] GitHub Settings -> Code security: Secret scanning ON, Push protection ON, Dependabot ON
- [ ] If a key ever leaks: rotate immediately at DeepSeek/Zotero console (do NOT `git rm`, history is permanent)

### T1.2 GitHub Actions quota monitoring  ~5 min

- [ ] Settings -> Billing -> Spending limit set to $0 (alert only, no charge)
- [ ] Email alerts at 75% usage enabled
- [ ] Repo stays PUBLIC (public repo Actions are unlimited and free)
- [ ] Never store PDFs in the repo, only DOIs + metadata

### T1.3 Zotero data redundancy  ~10 min

- [ ] Enable Zotero Storage sync (300MB free is plenty for metadata)
- [ ] Optionally periodic BibTeX export to repo as cold backup

### T1.4 Lock dependencies  ~10 min

- [ ] Commit `uv.lock` to repo
- [ ] On new machine: `uv sync` restores exact versions

### T1.5 First manual run  ~20 min

- [ ] Trigger Actions -> daily-research-radar -> Run workflow
- [ ] Check Actions log: fetcher counts should not all be zero
- [ ] Check `data/manifests/YYYY-MM-DD.json` is created
- [ ] Check GitHub Pages opens
- [ ] Check Zotero has new entries
- [ ] Any failure: debug before letting cron run for a week

---

## Tier 2 — Within 2-4 weeks after launch

### T2.1 Heartbeat monitoring  ~30 min

Trigger: 3 consecutive days where `fetched + scored + zotero_synced` are all zero.

- [ ] Write `pipeline/heartbeat.py` (~30 lines)
- [ ] Read last 3 manifests, if all-zero, open a GitHub Issue via API
- [ ] Call from end of `run_daily.py`
- [ ] Enable mobile push for `@me` mentions

### T2.2 Tune must_pair_with rules  ongoing

After two weeks, observe noise levels per direction:

- [ ] If daily High count < 1, rules too strict, loosen `must_pair_with`
- [ ] If daily High count > 10, rules too loose, tighten
- [ ] Each change is auto-logged in CHANGELOG

### T2.3 Real OpenAlex concept IDs  ~30 min

Current `openalex_concepts` are empty placeholders. Find real IDs at:

- https://api.openalex.org/concepts?search=bioprinting&per-page=10
- https://api.openalex.org/concepts?search=femoral%20stem
- https://api.openalex.org/concepts?search=finite%20element
- https://api.openalex.org/concepts?search=additive%20manufacturing

Paste IDs (format `C2779343474`) into `directions.yaml`.

### T2.4 Validate monthly archive  ~5 min

- [ ] Manually trigger `monthly-archive` workflow before the 1st (don't wait)
- [ ] Check Releases page for `archive-YYYY-MM.tar.gz`
- [ ] Confirm old JSON pruned from main, HTML preserved

### T2.5 Identify missing venues  ~30 min

After two weeks, recall:

- [ ] Did important conference papers (CVPR/NeurIPS/ICRA) show up but should have?
- [ ] If yes, is the gap in arXiv or OpenAlex concepts?
- [ ] Consider adding `crossref` or `dblp` as a 4th fetcher

---

## Tier 3 — Long-term vigilance

### T3.1 Ground truth eval set  ~2 hours

When: after ~1 month of usage, when you have intuition for what should be High vs Low.

- [ ] Pick 20 papers you've already read (5 High, 10 Medium, 5 Low)
- [ ] Save as `tests/ground_truth.yaml`
- [ ] Monthly: run current prompt+model on these 20, check drift
- [ ] If drift detected, upgrade prompt to `scorer_v2.txt` (keep v1)

### T3.2 "No product-ization" discipline  ongoing

The single judgment criterion for any new feature:

> Does this feature directly produce "I read today's digest -> added N papers to deep-read queue"?

Forbidden:

- [ ] Don't let others subscribe to your GitHub Pages (let them fork)
- [ ] No mobile app
- [ ] No UI polish beyond basic readability
- [ ] No login / personalization / themes
- [ ] No "productize and open source" until thesis done

Allowed:

- [x] Improve LLM scoring accuracy
- [x] Add more precise data sources
- [x] Improve prompts
- [x] Shorten "see paper -> decide whether to read" loop

### T3.3 Privacy review  ongoing

Before cross-device demos:

- [ ] Public page doesn't leak personal notes
- [ ] Zotero internal aliases don't sync to public view
- [ ] Open your GitHub Pages in incognito before sharing with supervisor

### T3.4 Legal compliance (UCL)  ongoing

- [ ] Scopus/WoS data: only through saved search alert emails, NEVER batch scrape and publish
- [ ] LLM-generated summaries: your design uses rewritten Chinese summaries, not 1:1 originals — safer
- [ ] If sharing with group: check UCL Research Data Management policy first
- [ ] OpenAlex/arxiv/PubMed: public publication is OK (CC0 or equivalent)

### T3.5 Six-month retrospective  every 6 months

Set a calendar reminder. Every 6 months:

- [ ] Read CHANGELOG.md — what did you actually change, and why?
- [ ] Browse GitHub Pages archive — how many days did you actually open?
- [ ] Browse Zotero — of High papers, how many did you actually deep-read?
- [ ] If "High -> actually read" rate < 20%, recalibrate scoring

---

## Memo (facts to remember)

### Cost baseline

- DeepSeek-chat: ~¥0.0023 per paper scored
- 4 directions x 200 candidates/day = ~¥0.46/day = ~¥14/month
- OpenAlex/arxiv/PubMed/Zotero: free
- GitHub Actions (public repo): free, unlimited
- GitHub Pages: free
- Budget alert: if monthly LLM bill > ¥30, investigate (likely a fetcher overflowed)

### Time baseline

- Single daily run: 30-60 minutes (varies by paper volume)
- LLM scoring is 80% of total time
- Run > 90 min: check DeepSeek rate limiting

### Data baseline (fill in after week 1)

| Metric | Week 1 observed | Notes |
|---|---|---|
| daily fetched total |   |   |
| daily after_dedup |   |   |
| daily after_routing |   |   |
| daily High count |   | <1 too strict, >10 too loose |
| daily Medium count |   |   |
| LLM daily cost |   |   |
| Zotero weekly adds |   |   |

### Emergency contacts

| Problem | Path |
|---|---|
| DeepSeek key leaked | platform.deepseek.com -> revoke + regenerate |
| Zotero key leaked | zotero.org/settings/keys -> delete + create new |
| Actions consistently fail | check log; usually a fetcher API changed |
| Page won't load | Settings -> Pages: verify source branch and folder |
| Repo getting slow | data/daily/ accumulated; manually trigger monthly-archive |
| Reproduce old day | open data/manifests/YYYY-MM-DD.json; checkout git_commit |

---

## Decision log

Track major architectural decisions to avoid forgetting rationale.

| Date | Decision | Reason |
|---|---|---|
| 2026-05-12 | MVP: 4 directions, not 8 | Validate first, expand later |
| 2026-05-12 | Pure LLM scoring, no rule pre-filter | Accuracy over cost, ¥0.5/day acceptable |
| 2026-05-12 | DOI-only strict dedup | Simple and reliable, fuzzy dedup has too many edge cases |
| 2026-05-12 | Public GitHub Pages | Research topic public is fine, also enables free unlimited Actions |
| 2026-05-12 | Scopus/WoS via email alerts only | Avoid ToS risk |
|   |   |   |

Add a row whenever making a substantive change.
