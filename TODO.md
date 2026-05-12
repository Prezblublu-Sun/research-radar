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
---

# 2026-05-12 Phase 1 上线后审议

本节记录 Phase 1 上线当晚一份外部 LLM 建议的审议结论。
原始建议涉及 14 条改动 + Tier 0/1/2/3 重排,经审议后保留
真实痛点、剔除过度设计、明确不做项。

## 本周做 (Week 1, ~4 小时)

### W1.1 空跑闸门 (~30 min)  ⚠️ 最紧急
**问题**: 2026-05-12 当晚出现 Actions 空跑后用 2 字节空 JSON 覆盖
本地 298 KB 有效数据。Zotero 数据完好,但 main 分支日报记录丢失。

**修复**: 在 `pipeline/run_daily.py` 的 `_save_daily` 之前加守卫:
- `fetched_total == 0` → 拒绝写入,sys.exit(1)
- 已有 N 篇但要覆盖成 0 → 拒绝写入
- JSON 大小 < 1KB → 标记 suspicious_empty

### W1.2 Zotero sync audit log (~30 min)
**问题**: 当晚 15 篇 Medium 进了 root 而不是 collection,因为本地
未 export ZOT_COL_* 环境变量,collection_key 为空字符串静默失败。
事后通过 backfill 脚本修复,但当时没有日志快速定位。

**实现**: 每次同步后写 `data/zotero_sync_log/YYYY-MM-DD.jsonl`,
每篇一行: `{doi, priority, target_collection, item_key, status, error}`

### W1.3 manifest 加 run_status (~10 min)
**目的**: 让 manifest 同时承担质量审计,不只是版本治理。

**实现**: manifest.py 输出加字段:
- `run_status`: success / partial_success / suspicious_empty / failed
- `quality_flags`: [low_fetch_count, zotero_sync_failed, ...]

### W1.4 --force flag 给 run_daily (~20 min)
**问题**: dedup 拦截导致本地跑过后 Actions 再跑变空跑。需要一个
明确的"强制重跑当天"开关,不依赖手动删 seen_dois.json。

**实现**: `python -m pipeline.run_daily --force` 跳过 seen_dois 检查。
注意:不要做"4 种运行模式"那种过度设计,只加 --force 就够。

### W1.5 Zotero 升级 2GB ($20/年, ~5 min)
**问题**: Zotero 云端 99.9% 满,新条目元数据虽小但有撞墙风险。

### W1.6 SCOPE.md (~30 min)
**目的**: 明确 Research Radar 做什么、不做什么,避免后续功能扩张
混淆 Radar 和 lit-system 的边界。

**内容**:
- In-scope: 论文发现、规则路由、LLM 评分、Zotero 同步、HTML 渲染
- Out-of-scope (lit-system 范畴): PDF 全文解析、chunking、embedding、
  RAG、知识图谱、引用分析

### W1.7 跑 2-3 天观察真实数据分布
**目的**: Phase 1 数据基线只有 1 天(且被空跑覆盖)。等 W1 完成
+ 自动跑 3 天后,才有真实数据决定后续调参方向。

---

## 下周做 (Week 2, ~4 小时)

### W2.1 调整 must_pair_with 规则
基于一周真实数据(估计 500-1000 篇路由结果)。
不要预先设计 4 个方向的细则——根据观察到的噪音再调。
判断标准: 每方向每天 High 1-3 篇 / Medium 5-15 篇为合理区间。

### W2.2 写 10 篇 mini eval set
注意:不做"100 篇 ground truth"——那是 8-16 小时工作,不切实际。
改为渐进式:本周读到的论文里挑出明确 High/Medium/Low/Exclude 各 2-3 篇,
存成 `tests/eval_set.yaml`。每周补充几篇。

### W2.3 candidate export to lit-system (~30 min)
**目的**: 给 lit-system 一个稳定接口读取 High/Medium 候选。

**实现**: `pipeline/export_for_lit_system.py` 扫所有 daily JSON,
筛 Medium+,输出 `data/exports/candidates.jsonl`。
不需要新格式——daily JSON 已经含所有字段。

---

## 月内做 (Month 1, 视精力)

### M1.1 OpenAlex 真实 concept IDs
浏览器查 `https://api.openalex.org/concepts?search=...` 拿到
4 个方向的真实 concept ID,填进 directions.yaml 的 openalex_concepts。

### M1.2 周报 Phase B: 趋势分析
关键词词频本周 vs 上周对比,简单 SVG 柱状图。
不依赖 LLM,~1 小时。

### M1.3 周报 Phase C: LLM 元
综述
DeepSeek 读一周 High+Medium 写
