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
---

## 明确不做 (Rejected)

### Rejected 1: "Very High" 优先级 + 自动下载 OA PDF
**理由**:
1. 当前 prompt 只有 4 级 (High/Medium/Low/Exclude),不需要 5 级
2. 自动 PDF 跟 Zotero quota 直接冲突 (2GB 也撑不久)
3. 让用户在 Zotero 客户端手动用 "Find Available PDF" 更可控

### Rejected 2: 4 种运行模式 (normal/manual/backfill/debug)
**理由**: 过度设计。`--force` + `--skip-zotero` + 日期参数已覆盖
所有真实场景。多种模式会增加代码复杂度但不增加价值。

### Rejected 3: 100 篇人工 ground truth (一次性建)
**理由**: 8-16 小时工作,不是"尽快"能完成的。改为 10 篇 mini set
+ 每周渐进补充 (见 W2.2)。

### Rejected 4: "重新定位为 lit-system 文献发现层"
**理由**: 当前架构本来就是文献发现层。LLM 建议担心"Radar 扩张成
RAG"——但没有任何代码或计划朝这个方向走。担忧不存在的问题不是
合理的优先级。改为写 SCOPE.md 明确边界即可 (见 W1.6)。

### Rejected 5: "公开页面不展示完整 abstract"
**理由**: 当前 HTML 已经只显示 LLM 重写的中文总结,不复制原文
abstract。LLM 建议这条是没仔细看代码就提的。

### Rejected 6: 立即收紧 Zotero 同步策略 (分级 PDF)
**理由**: 当前所有 Medium+ 同步 metadata 不带 PDF,已经是
"分级"——只是分了 2 档 (同步/不同步) 而不是 4 档。
档位继续细分需要先看实际数据决定,不要预先优化。
---

## 审议方法说明

这次审议的输入是一份 LLM 生成的建议文档,审议中识别出几类问题:

1. **虚构事实**: "Very High" 5 级优先级、Docling/RAG 模块——不存在
2. **过度规划**: 14 条改动 + 全面架构重排,对刚上线项目过激
3. **没看代码就提建议**: 担心 abstract 全文复制等问题,但当前代码已避免
4. **"标准做法"填充**: 用通用最佳实践代替项目特异性分析

教训: LLM 用于"全面审项目"时容易脑补缺失上下文。后续若再用 LLM
辅助审议,应给具体代码 + 具体问题,不要让它"全面审视"。
---

## W1.8 期刊 RSS 兜底 fetcher (~1-2 小时, 待 Phase 1 稳定后做)

**目的**: 关键词搜索可能漏掉顶刊论文(标题/abstract 没出现关键词)。
用 RSS 订阅作为召回兜底,不影响 LLM 评分逻辑。

**设计原则**:
- 期刊订阅只做召回(捞到论文),不参与 priority 评分
- 论文走完整路由 + LLM 评分,跟其他来源平等
- 失败重试: 期刊 RSS 不通时记 warning 不报错

**实施步骤**:
1. 确认期刊 RSS URL (大部分用 IOP/Elsevier/Wiley/Nature 标准 RSS)
2. 新建 fetchers/journal_rss_fetcher.py 用 feedparser
3. RSS 只给标题时,用 DOI 去 OpenAlex 补 abstract
4. directions.yaml 加 journal_subscriptions 列表
5. aggregator.py 把 RSS 来源合进去

**候选期刊清单** (LLM 推荐, 待真实数据验证):
- Biofabrication
- Biomaterials
- Acta Biomaterialia
- Bioactive Materials
- Journal of Biomechanics
- Journal of the Mechanical Behavior of Biomedical Materials
- Additive Manufacturing
- Acta Materialia
- Materials & Design
- Journal of Arthroplasty

注意: 这是 LLM 推荐的清单,不是用户自己确认的。
在真正订阅前,应该让自动跑 2 周,看哪些期刊在现有 fetcher 下漏报,
再有针对性地添加(基于真实漏报数据)。

**预期增量**: 每天多 30-100 篇候选论文进流水线。
LLM 评分成本增加 ~¥0.2/天,可接受。
---

# 2026-05-13 优化方向校准

经用户明确,Research Radar 的优化函数是:

**最大化召回**(不漏掉有价值的论文),不是最小化精确度或 LLM 成本。

具体含义:
- DeepSeek ¥0.5-2/天 的调用成本不是问题,完全可接受
- LLM 评分能正确筛选噪音,所以路由层应该宽松而非收紧
- "相关领域启发"也算有价值——hip 临床论文的方法启示、纯 ML 论文
  在 surrogate 方向的可迁移性等,都不应被路由排除
- 比起"路由通过 19 篇 90% 相关",更想要"路由通过 80 篇 40% 相关
  + LLM 准确分级"

## 这改变了之前几条 TODO 的判断

### Revised: W2.1 调整 must_pair_with 规则
原计划:基于一周数据"降噪"。
修订:不再优先"降噪",改为"召回评估"——一周后看是否有方向命中过低,
有针对性地加关键词/concept,而非减。

### Revised: 关于 hip_implant 临床论文
原本担心:hip arthroplasty concept 拉到的临床论文是噪音。
修订:不处理。LLM 会打 Low/Exclude,但偶尔的方法启示有价值。

### Revised: 关于 fea_surrogate 通用 ML 关键词
原本担心:conformal prediction / Bayesian optimization 等过宽,
拉来纯 ML 论文。
修订:不处理。这些论文里可能有可迁移到 surrogate modelling 的方法。

## 这没改变的事

- 数据质量闸门(W1.1 空跑闸门)仍然必要
- 版本治理(manifest, CHANGELOG)仍然必要
- SCOPE.md 边界(不做 RAG)仍然不变
- Zotero 同步只 Medium+ 仍然合理(避免低优先级污染阅读队列)

## 新增的潜在 TODO (待数据驱动决策)

- W2.x 加 fea_surrogate 的 OpenAlex concept IDs (即使会拉来更多
  泛 ML 论文,因为可能有方法启示)
- W2.x 加 negative_keywords 字段时,要严格——只排除明确无关的
  (土木桥梁、纯药物、纯影像诊断),不排除"看起来不直接相关"的

## 日报视觉策略的影响

默认 "High+Medium" 过滤的设计仍然合适:
- 你不会被 80 篇 Low 淹没
- 但 80 篇 Low 仍然存在于 JSON,LLM 评过分,如果某天 High/Medium
  很少,你可以点 "Show all" 看 Low 里有没有遗珠
