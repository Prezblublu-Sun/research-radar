# 复核：W7161090206 — Bayesian Optimization with Structured Measurements (Vector-Valued RKHS)

- 优先级：High（保留）
- 方向归类：fea_surrogate（正确）
- 来源：OpenAlex W7161090206，pdf_found=false（no_open_access_link）

## 关键判断：与 arxiv:2605.09362v1 的关系
**这是同一篇论文的不同入口。** 标题逐字相同；OpenAlex 抓到的元数据应是 Wenbin Wang & Colin N. Jones (EPFL Automatic Control Lab) 的 arXiv 2605.09775v1（cs.LG, 2026-05-10）。本批次同一 session 中已对 arXiv 版本做了完整精读，详细总结见 [[arxiv_2605.09775v1]]。

**潜在去重缺口**：理论上 `doi:` 严格去重应能合并两条记录，但本条 OpenAlex 入口没有 DOI（arXiv preprint 通常无 DOI 直到正式收录），所以 dedup 自然漏掉。这一行为符合预期，**不是 bug**；按 CLAUDE.md §4，DOI-only 严格去重的边界 case，无需调整。

## 摘要准确性复核
existing_summary 与 arXiv 全文一致：
- ✅ "标准 BO 丢弃结构化输出信息" —— 准确，论文第 1 段直接给出建筑供热成本的动机例。
- ✅ "vector-valued RKHS + 结构化测量" —— 准确，对应论文 Eq. (1) 与 Section 2-3。
- ✅ "测量空间置信界 + UCB + 亚线性遗憾" —— 准确，对应 Theorem 1-3 与 Algorithm 1。
- ✅ "数值基准验证 sample efficiency + 时变适应" —— 准确，Section 5 三个合成基准 + MPC 建筑控制实验。
- 摘要里"未涉及生物医学或 FEA 应用"这一句是 scorer 主动加的负面信息 —— 严格说论文确实没有这两类直接实验，但**方法本身天然适配 FEA**（输出场 + 多 KPI 线性泛函），scorer 这条 disclaimer 反而低估了价值。

## 优先级复核
**保留 High 正确，且如果重新打分应更靠前**：
1. 方法直接对应 fea_surrogate 方向的核心痛点（FEA call 昂贵 + 同几何多 KPI），见 arxiv_2605.09775v1 总结 §"与我研究方向的关联"。
2. 理论 + 实验完备，作者团队（EPFL Colin Jones 组）在 control 圈有 track record。
3. 唯一减分项：未在 FEA 上验证，需我自己迁移；这是 idea 空间，不是缺陷。

## 处置
合并到 arXiv 版本的总结即可；本条 checked，**不再单独跟读**。

## 评分体系反馈（积累中）
- 同一 session 内出现 arXiv ↔ OpenAlex 双入口的情形，建议未来 weekly 流程做一次 title 相似度 audit（Levenshtein / token-overlap）将两边手动合并，避免精读重复消耗。这是 [[ADR-0025]]（figshare/zenodo version DOI normalization）的相邻问题，可以一并考虑。
