# Session log — 2026-05-23 (research-radar)

三方协作 (用户 prezblublu / Web Claude / Claude Code TUI)。
起点: DOI verify 发现 femoral-stem ground-truth recall 偏低, 顺藤摸出多个问题。

================================================================
已完成 (全部已 push 到 origin/main, HEAD=f6c4399d)
================================================================

## Bug 修复
1. fetcher gap (17bd08a) — OpenAlex 召回过窄。两个根因:
   _build_filter 把窄 concept 与 search keyword AND 在一起; 硬编码
   type:article 漏掉 review。修法: OR fan-out 双 query (concept-only +
   search-only, 按 OpenAlex id 去重) + type:article|review + 拓宽
   config/directions.yaml 的 concepts。
2. silent scorer (ADR-0017, f433939) — 5479 篇 priority 有值但 reasoning
   空 (旧版异常吞进 priority_reason)。修法: score_batch 3 次 retry, 全失败
   记 scorer_failed=True + priority=None (不再默认 Low)。rescore_silent.py
   工具回填历史。
3. scorer hang (d1f3742) — OpenAI SDK client 无 timeout, DeepSeek 连接卡死
   38 分钟。修法: client 加 timeout=60 + max_retries=3 (env 可调
   LLM_TIMEOUT / LLM_MAX_RETRIES)。

## 性能优化
4. 并发 scorer (ADR-0019, bd557e58) — score_batch 串行 5.1s/篇。改
   ThreadPoolExecutor (LLM_CONCURRENCY 默认 8), 保序, 保留 ADR-0017 retry。
   实测 8-9x。DeepSeek 实测 10 并发 0 错误。
5. score-before-dedup (ADR-0020, d217e212) — run_historical 先 score 后
   first-seen-wins 丢弃, 浪费 22-24% LLM call。改: score 前按 v2.identity_key
   过滤 corpus 已有。语义契约: run_historical 不再重 score 已有 paper, 重评分
   走 rescore_silent。(Status 仍 Proposed, 待下次 backfill 实测确认)

## 数据
6. 10 年 refetch (c33678ae) — 用新 fetcher 重抓 2015-01..2026-05 (137 月)。
   并发 backfill ~14h (串行需 ~69h)。scored 90064, wrote 68434 new。merge 时
   解了 18 个 daily file conflict (取并集, first-seen-wins)。
7. silent 清零 (f6c4399d, 本次) — rescore 5383 silent → 0, succeeded=5383,
   scorer_failed=0, 88 分钟 (并发 + per-bucket 批量, c268a0b8)。剩 8 个
   scorer_failed=True 保留 (--resume 跳过)。

## 工具 / 基础设施
8. manual-backfill / manual-rescore GitHub Actions workflows (a6efec0)
9. corpus 质量审计工具 (14434b98) — scripts/audit_corpus_quality.py, 跨年分层
   抽样, 客观指标 (完整率/silent/failed) + 启发式判断 (一致性/中文摘要/路由)。
   首跑 n=50: 完整率 92%, failed=0, silent 4 (旧格式, 本次已清), routing 发现
   fea_surrogate 被 "active learning" (教育术语) 污染。

## ADR
- ADR-0017 scorer resilience (retry + null-flag)
- ADR-0019 scorer throughput (并发, 含 retrospective)
- ADR-0020 score-before-dedup (Proposed)
- ADR-0021 rl_world_model 新方向 + RL×FEA 交叉提升 (Proposed)

================================================================
待办 (下次)
================================================================

## 1. 新方向 rl_world_model 实现 (ADR-0021 已设计完整)
   - config/directions.yaml 加第 5 方向 "RL & World Models"
     strong_keywords: world model / model-based RL / latent dynamics /
       Dreamer / MuZero / learned simulator / MPC / RSSM ... (不放裸
       "reinforcement learning", 防泛 RL 噪音)
     must_pair_with: [RL, world model] / [RL, dynamics model] /
       [RL, model-based] / [RL, simulation] / [RL, surrogate] /
       [RL, finite element] / [RL, design optimization] / [world model, physics]
     PINN 不放 (留 fea_surrogate)
   - boost helper (单一定义, run_daily 在 score_batch 后调用):
     若 paper.directions 同时含 rl_world_model + fea_surrogate →
     priority 升一档 (Low→Medium, Medium→High, High 封顶, Exclude 不救),
     记 priority_boosted / boost_reason / priority_pre_boost。
     仅此一个交叉, 不泛化。幂等 (重跑不重复升)。
   - UI 支持 5 方向 (颜色 / nav / filter, build_pages + radar-ui.css)
   - 测试: 路由 (RL+world model 进; 纯 Atari RL 不进; PINN-only 不进 rl);
     boost (双方向 Low→Medium 等; 单方向不升; 其他方向对不升; Exclude 不动)
   - 范围: 只 daily cron 向前生效; 历史 corpus 不 re-route
   - 走 Claude Code, 但要在干净 working tree 下做 (rescore 已完, 现可)

## 2. recall 分页截断验证 (等 OpenAlex 429 恢复)
   femoral-stem ground-truth 4 个 missing must_read 重抓后只补回 1
   (recall 21%→26%)。已定位: router 不是主因 (实测 4 篇里放行 3 篇),
   嫌疑是 fetcher 分页 cap (每 query 40 页 x 50 = 2000, 高产 concept 月份
   如 FEM 每月可能 >2000, 目标 paper 排后被截)。
   待验证: 查 C135628077(FEM)/C170700871(biomech) 在目标月份的 paper 总数
   是否 >> 2000。若是 → 改 fetcher 分页策略 (按 concept 拆 / 按月细分 / 提 cap)。
   目标 DOI: 10.1002/jor.70079 (2025-10, concept 无 FE/biomech, router 真丢),
   10.1038/s41598-024-61305-x (2024-05, router 丢-abstract 关键词不足),
   10.3390/app15073522 (2025-03), 10.3390/app14083200 (2024-04 review)。
   后 3 篇 concept 对、router 放行, 嫌 fetcher 没抓到。

## 3. DeepSeek key 轮换 (安全)
   sk-10630...daa8 在本次对话明文暴露。该: platform.deepseek.com 撤销 →
   建新 key → 更新 GitHub Secrets OPENAI_API_KEY → 更新 /tmp/secrets.sh。
   /tmp/secrets.sh 是 tmpfs (reboot 丢)。

## 4. ADR-0020 Proposed → Accepted
   下次 backfill 实测 pre-dedup 真省 ~22-24% (看 skipped_existing 计数) 后升级。

## 5. 其他遗留 (更早会话)
   - fea_surrogate routing 噪音: "active learning" 在教育界同名, 大量教学论文
     被收为 Exclude。可给该词加 must_pair_with 收紧。需 ADR (改 routing)。
   - 8 个 scorer_failed=True paper (3 retry 都失败, 多为 JSON parse)。
   - search-index.json 接近 GitHub 100MB 限 (未来 era-split / lazy-load)。

================================================================
关键运维笔记
================================================================
- key: source /tmp/secrets.sh (OPENAI_API_KEY=DeepSeek, base api.deepseek.com,
  MODEL deepseek-chat)。SSH 本地默认无 key。
- 并发: export LLM_CONCURRENCY=8 (backfill 和 rescore 都吃这个)
- backfill: .venv/bin/python -m pipeline.run_historical --from-date .. --to-date ..
  progress: data/historical/_progress.json (date_range 必须与 CLI 完全一致,
  否则 run_historical.py:422 SystemExit)。resume-safe。
- rescore: .venv/bin/python -m scripts.rescore_silent --resume (--dry-run 只读计数)
- tmux 跑长任务; 别 Ctrl+Z (用 Ctrl+C); 别 resize 终端 (crash Claude Code TUI)
- 长 Claude Code prompt 写 /tmp/cc_prompt.txt, 粘一行 "Read /tmp/cc_prompt.txt
  for the task description." (该文件会复用, 触发前确认内容)
- git fetch 在 backfill/rescore 跑时安全 (只更新 remote ref); git pull/push 不安全
- daily cron: 0 3 * * * UTC, 实际 ~06:30-07:00 UTC commit (GitHub 调度延迟, 正常)

HEAD at session end: f6c4399d (origin/main 同步, 0 0)
