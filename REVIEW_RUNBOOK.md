# Research Radar — 文献精读循环 Runbook（给 Claude Code）

你是精读 agent。所有状态都在 `data/review/state.json` 里，**你自己不记忆进度**。
任何新 session 启动后，照本文件从断点继续即可。

## 一次性准备
1. `uv pip install pymupdf`（PDF 正文抽取；可选回退 `pdfplumber`）。装到项目 `.venv`，
   不要污染系统 Python。
2. 确认环境变量 `UNPAYWALL_EMAIL`（用 DOI 找开放获取 PDF 必需，免费）。
3. 首次或每周抓取后：`UNPAYWALL_EMAIL=<your-email> .venv/bin/python review_harness.py discover`
   —— 把窗口内（默认近 6 周；可用 `REVIEW_SINCE=YYYY-MM-DD` 覆盖）的
   High/Medium 论文收进状态库。

> **重要：所有命令都用 `.venv/bin/python`，不要用裸 `python`。** 系统 Python 没有
> 装 pymupdf；走裸 `python` 会让 `extract_text` 静默回退到空字符串，导致 `pdf_found`
> 全部为 false，浪费抓取并把本可精读的论文降级成 checked。同理，凡是会触发 PDF
> 下载（即调用 `next`）的命令，都把 `UNPAYWALL_EMAIL=...` 前置上，否则只有 arxiv
> 能拿到正文，所有 DOI 论文都掉到 checked。

## 主循环（每个 session 反复做，直到撞墙或暂停）
重复以下步骤，**一次只处理一篇**：

1. 运行 `UNPAYWALL_EMAIL=<your-email> .venv/bin/python review_harness.py next`，读它返回的 JSON。
2. 看 `status` 字段：
   - `PAUSED` → 立刻停止循环，告诉用户已暂停。
   - `DONE`   → 本批次全部完成，进入「周报」环节。
   - `READY`  → 继续第 3 步。
3. 按 `pdf_found` 分流：
   - **有正文**（`pdf_found=true`）：读 `text_path` 全文，写一份详细中文总结到
     `summary_target`（建议含：研究问题 / 方法 / 关键结果与数据 / 与我研究方向的关联 /
     局限 / 是否值得跟进）。完成后：
     `.venv/bin/python review_harness.py done <id> --kind read --summary <summary_target>`
   - **无正文**（`pdf_found=false`）：不要硬找。复核 `existing_summary` 与 `priority`：
     摘要是否准确、方向归类是否对、优先级是否合理；把复核结论写到 `summary_target`。完成后：
     `.venv/bin/python review_harness.py done <id> --kind checked --summary <summary_target>`
   - 处理中若彻底无法进行（如正文乱码）：
     `.venv/bin/python review_harness.py fail <id> --reason "..."`
4. 回到第 1 步。

> 每完成一篇，状态已落盘。**被中断最多损失正在读的那一篇**，下次 `next` 会自动重新拾起它（attempts 已计数，超过 3 次自动跳过）。

## 单 session 论文上限（≈25 篇）

**主动 cap：单 session 处理论文数不要超过约 25 篇。** 达到上限后，
把当前这一篇收尾（`done`），告诉用户已到 cap，然后停。用户会开新 session
继续 —— 状态都在 `state.json` 里，断点干净。

**为什么要 cap：** 长时间单 session 会出现**总结深度衰减**。早期论文
（前 ~15 篇）能写出完整结构（研究问题 / 方法 / 结果 / 与研究方向关联 /
局限 / 跟进），到 25+ 篇后会逐步坍缩到 15-20 行的骨架式总结 —— 标的是
`read` 但深度更接近 `checked`。这是上下文疲劳，**与论文质量无关**，但
会让 weekly 报告的"重点论文"覆盖度不均匀，且这种不均匀完全由处理顺序
决定，不反映实际重要性。W19 单 session 跑完 65 篇是这种衰减的典型样本。

**实操：**
- 周容量 42-46 篇的 W16/W17/W18 各需要约 2 个 session。
- 周容量 ≤27 的 W21+ 可以单 session 跑完。
- 周容量 ≥35 强烈建议**至少**两个 session（每 session ≤25）。
- 撞到上限时不需要先写周报；周报留到该周 0 pending 时再写。
- 如果一周跨多个 session，**所有 session 都完成后**再写周报，
  报告里不需要标记哪些论文在哪个 session 处理。

> 这个 cap 是经验值，不是硬限制。如果发现自己仍能写出完整结构总结，
> 可以多跑几篇；如果发现已经在写骨架式总结，应立刻停止并告诉用户。
> 衡量标准是**总结质量**，不是论文计数。

## 撞到 token / 用量墙
若上限 cap 不够保护或上下文意外填满：把当前这一篇收尾（`done`），
然后结束。状态都在磁盘上，新 session 直接从「主循环」第 1 步继续。

## 手动暂停 / 恢复
- 暂停：`.venv/bin/python review_harness.py pause`（或直接 `touch data/review/PAUSE`）。下一次 `next` 即返回 PAUSED。
- 恢复：`.venv/bin/python review_harness.py resume`。

## 周报（`next` 返回 DONE，或用户要某周周报时）
1. 确定 ISO 周号（如 `2026-W21`），运行
   `.venv/bin/python review_harness.py weekly 2026-W21`，拿到清单 manifest 和规范报告路径
   `reports/weekly/2026-W21_周报.md`。
2. 逐个读 manifest 里每篇的 `summary_path`，综合成**不少于 1000 字的中文周报**，写到 `report_path`。
   建议结构：
   - 本周概览（覆盖周期、High/Medium 篇数、按方向分布）
   - 重点论文逐篇要点（精读的展开讲，复核的简述结论）
   - 跨论文的趋势 / 共同主题 / 与我各研究方向的呼应
   - 值得跟进的线索 + 对现有评分体系的反馈（哪些 priority 判错了）
3. 写完后告诉用户报告路径，并 `git add` 让用户决定是否 commit。

## 命名规范
- 单篇总结：`data/review/summaries/<safe-id>.md`（harness 已给出 `summary_target`）
- 周报：`reports/weekly/<YYYY-Www>_周报.md`（可排序）
