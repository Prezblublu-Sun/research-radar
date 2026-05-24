# Session log — 2026-05-24 (research-radar)

三方协作 (用户 prezblublu / Web Claude / Claude Code TUI)。
接续 2026-05-23 (见 session-log-2026-05-23.md)。本日三段: (1) 收尾昨日
+ rescore 改造收尾, (2) daily cron 失败救火 → search-index era-split,
(3) recall 调查 → 定位 OpenAlex backfill 静默归零 (今日最重要发现)。

HEAD at session end: 1fec6b8a (origin/main 同步 0 0)。

================================================================
本日 commit (按序, 全部已 push)
================================================================
昨日尾: f4f07ebe (session log) → 另一并行会话加了 analytics:
  ae8f6b6f/3d928854/15b27152 (build_analytics A1 distribution, ADR-0018)
本日:
  - c268a0b8 perf(rescore): batch candidates per bucket (ADR-0019)
  - f6c4399d data: rescore all silent → 0
  - 14434b98 feat(scripts): corpus quality audit tool + report
  - effa3ca8 docs(adr): ADR-0021 rl_world_model direction + RL×FEA boost (Proposed)
  - b5028fad docs(adr): ADR-0022 search-index era-split (Accepted)
  - c28a9474 feat(search): era-split + drop summary_en (ADR-0022 code)
  - dd6e6b7a docs: regenerate site + era-split (ADR-0022 data, 4296 files)
  - cfcc4f01 data: manual daily run 2026-05-24 (补全 + OpenAlex 恢复)
  - 1fec6b8a docs(adr): ADR-0023 OpenAlex backfill silent-zero (root cause)

================================================================
段 1 — 收尾 (silent rescore + 质量审计)
================================================================
- rescore_silent 之前逐篇 score_batch([p]) → 无并发。改 per-bucket 批量
  (c268a0b8)。跑完: 5383 silent → 0, succeeded=5383, scorer_failed=0, 88 min
  (f6c4399d, 560 files)。注: silent 分布不均 (110 bucket×1篇, 262×6-20篇),
  稀疏 bucket 拖慢, 实际 88min 而非理想 50min。
- 质量审计工具 scripts/audit_corpus_quality.py (14434b98): 跨年分层抽 50,
  客观指标 (完整率 92%, scorer_failed 0, silent 4=旧格式) + 启发式判断。
  发现 fea_surrogate 被 "active learning" (教育同名词) 污染收教学论文。
- ADR-0021 (effa3ca8): 新方向 rl_world_model (RL+世界模型, PINN 留 fea) +
  RL×FEA/surrogate 交叉提升一档 (确定性后处理, 仅此一个交叉)。设计完成,
  实现 deferred (用户先要查 recall)。

================================================================
段 2 — daily cron 失败救火 (search-index era-split, ADR-0022)
================================================================
- 收到 GitHub 失败邮件。run 26354088757: fetch/score/render 成功但 git PUSH
  被拒 — docs/search-index.json 244MB > GitHub 100MB 限。
- 根因: 10年 refetch (103k paper) + rescore (填满双语 summary) 撑大 index。
  blob 占 85%。单文件无解 (精简后仍 146MB)。按年拆每年 <32MB。
- ADR-0022 (b5028fad, Accepted): (1) era-split 按年 → search-index-YYYY.json
  ×13 + manifest, git rm 旧单文件; (2) blob 去 summary_en (abstract[:500] 已
  英文; why_not_core 保留); (3) 前端 manifest + Promise.all 各年文件合并,
  搜索逻辑不变。blob 仅搜索用, 不影响任何页面显示。
- 实现 (c28a9474 代码 + dd6e6b7a 数据): build_pages._build_search_index 按年写
  + manifest; 内联 JS 多文件 load。5 新测试, 206 pass。全站重渲染 (4296 files,
  corpus 34k→103k 所有 HTML 更新)。最大年文件 28MB (2022)。
- 手动 run_daily 补全 (cfcc4f01): OpenAlex 恢复 (429→200)! 126 unique →
  29 routed → scored, 写 9 bucket (5/22 +13, 5/23 +5 = cron 失败丢的)。
  era-split 在真实 run_daily 路径验证通过 (年文件, 无超限单文件)。

================================================================
段 3 — RECALL 根因 (ADR-0023, 今日最重要发现)
================================================================
起点: femoral-stem ground-truth must_read recall 低, refetch 后只 21%→26%。
三次假设, 前两次被数据证伪:
  1. "router 太严" ❌ — live route() 测 4 篇 must_read, router 放行 3/4
  2. "fetcher 分页截断 >2000/query" ❌ — 目标月 concept 量 1765/219/2321,
     且今天重跑 fetcher (OpenAlex 恢复) 3 篇全在结果里。fetcher 逻辑没问题。
  3. "OpenAlex backfill 静默失败" ✓ 实锤:
ROOT CAUSE: data/historical/_progress.json by_source 显示 — 137 月中 47 月
  openalex=0, 几乎全是近期 (2022-12..2026-05 连续 42 月 + 早期散月 2017-06/
  2018-09,10/2019-02,03)。这些月 status 仍标 "complete"。
机制 (run_historical.py ~line 229-240): backfill 跑到后期 OpenAlex 免费配额
  耗尽 → 持续 429 → openalex_fetcher._fetch_one raise_for_status 抛 →
  run_historical catch, log 一行, by_source[openalex]=0, 月份照常 complete。
  无重试/无 incomplete 标记/无报警。
为什么毁了 recall: OpenAlex 是唯一覆盖期刊论文的源 (MDPI/Nature/Elsevier);
  arxiv 是 preprint, pubmed 窄。用户 ground-truth must_read 多是近年 (2024-25)
  期刊论文 = 恰好那 47 个 0 月。corpus 虽 103k 但近 3.5 年几乎全 arxiv preprint,
  期刊正式论文缺失。refetch 没救回因为那几天 OpenAlex 又 429。
教训: progress.json 第一天就记着 openalex:0 — 早看 by_source counts 直接定位,
  不用绕三天假设。"先看已有数据再假设"。一个吞异常+log+报告成功的 pipeline
  比直接失败更危险 (103k 健康假象掩盖 3.5 年数据洞)。

================================================================
待办 (下次, 优先级排序)
================================================================
## 1. ADR-0023 修复 (最高优先 — recall 灾难)
   Part 1 代码加固 (必须先做, 否则重跑又 429):
     a) openalex_fetcher._fetch_one: 429/5xx 重试+指数退避 (尊重 Retry-After),
        而非 raise_for_status 直接中断整月; 最终失败抛 typed error
     b) run_historical: 区分"源 0 结果"vs"源抛错"; 抛错标 month incomplete
        (可 resume 只重跑这些月); 不静默标 complete
     c) 速率控制 (sleep / 检测日限暂停), 守住 OpenAlex 免费配额
   Part 2 数据修复 (加固后): 重跑 47 个 openalex=0 月 (列表见 ADR-0023)。
     OpenAlex 现已恢复 (200)。first-seen-wins 只补缺的期刊 paper, 不动已有
     arxiv/pubmed; ADR-0020 pre-dedup 跳过已有。分批跑避免再触发 429。
     预期: recall 大涨 (ground-truth must_read 期刊论文就在这些月)。
   47 月: 2017-06, 2018-09, 2018-10, 2019-02, 2019-03, 2022-12,
     2023-01..12 (全), 2024-01..12 (全), 2025-01..12 (全), 2026-01..05 (全)

## 2. rl_world_model 实现 (ADR-0021, 已设计)
   config 加方向 + boost helper (run_daily, RL×FEA 交叉提升一档) + UI 5方向
   + 测试。范围: 用户最后定"先不管 backfill, 回来查 recall" → backfill 范围
   待定 (查完 recall 后再议; 注意 backfill 只新增改不了已有, re-route 需另写)。

## 3. DeepSeek key 轮换 (安全)
   sk-10630...daa8 多次会话明文暴露。platform.deepseek.com 撤销 → 新 key →
   GitHub Secrets OPENAI_API_KEY + /tmp/secrets.sh。

## 4. ADR 状态升级
   - ADR-0020 Proposed→Accepted: 下次 backfill 实测 pre-dedup 省 ~22-24%
     (看 skipped_existing) 后
   - ADR-0021 Proposed→Accepted: rl_world_model 实现 + 验证后

## 5. 其他遗留
   - fea_surrogate "active learning" 路由噪音 (教育同名词收教学论文), 需 ADR
   - 8 个 scorer_failed=True paper (3 retry 都失败)
   - cron 验证: 明早 daily cron 应 ✓ (era-split 已修); gh run list 查

================================================================
关键运维 (承 2026-05-23 log, 仅记新增/变化)
================================================================
- OpenAlex 已从 429 恢复到 200 (2026-05-24)。但免费配额有日限, 大量 backfill
  会再耗尽 — 这正是 ADR-0023 根因, 重跑前必须先做 Part 1 加固。
- fetcher 在 fetchers/openalex_fetcher.py (顶层 fetchers/ 包, 非 pipeline/)。
  fetch() 双模式: daily max_pages=4, historical max_pages=40 (×50=2000/query)。
  fan-out: concepts AND keywords → 双 query (concept-only + search-only) union。
- run_daily 的 --help 不显示帮助而是直接执行整个 pipeline (argparse 未配 --help,
  且 import 时即读 OPENAI_API_KEY — 跑前必须 source /tmp/secrets.sh)。
- search-index 现为 docs/search-index-YYYY.json ×13 + manifest (非单文件)。
  build_pages._build_search_index 生成; 任何重渲染都走这个 (已验证 run_daily)。
- 承前: source /tmp/secrets.sh; LLM_CONCURRENCY=8; backfill date_range 必须与
  CLI 完全一致; tmux 跑长任务; 不 resize 终端; Claude Code prompt 走
  /tmp/cc_prompt.txt; git commit 走普通 bash 非 Claude Code TUI。

================================================================
lit-system (另一仓库, 顺带记录)
================================================================
本日用户在 ~/lit-system 提交 5ceb2c9 (DOI recovery 实验脚本, ADR-0018 调查) +
跑 ingest_619 tmux (docling PDF 解析)。与 research-radar 无关, 不同 repo/上下文。
