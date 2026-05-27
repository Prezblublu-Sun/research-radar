# ADR-0024: fea_surrogate scorer — method-novelty × transfer-pathway 二维判定

**Status**: Draft（提案；尚未实施；不要在确认前修改 scorer_v3.txt 或新建 scorer_v4.txt）
**Date**: 2026-05-26
**Related**: CLAUDE.md §1（recall not precision）, prompts/scorer_v3.txt,
W21 pilot 周报 §5.1, ADR-0014（LLM scoring baseline）

## Context — pilot 信号

2026-W21 精读 pilot（27 篇）发现 fea_surrogate 方向出现"应用域偏远但 routing
正确"的命中 cluster。具体样本（按方向"对 user 边际价值"维度）：

| Paper | 应用域 | 方法学创新度 | 实际价值 | scorer priority |
|---|---|---|---|---|
| Therm-FM（arxiv:2605.22663） | 3D-IC 热（电子） | **极高**（PDE foundation model + 多保真） | **高**（范式可平移到生物力学 FEA） | High ✓ |
| SiP 跨尺度 CNN 代理（10.1108/ssmt-03-2026-0017） | 半导体封装 | 中（CNN + 像素灰度均质化） | 中（骨小梁多尺度有借鉴） | Medium ✓ |
| Agentic AI 地热油藏（10.2118/232332-ms） | 地热油气 | 低（DNN 代理 + LLM orchestration） | 低 | Medium ✗ |
| SSPC 航空 PINN（10.1016/j.icheatmasstransfer.2026.111588） | 航空电子 | 低（calibrated residual PINN） | 低 | Medium ✗ |
| NPINN+ 波方程非局部 BC（10.1038/s41598-026-50374-9） | 数学物理 | 低（窄技术增强） | 低 | Medium ✗ |

直观对比：Therm-FM 与 SSPC 都是"电子领域的 PDE 代理"，但 Therm-FM 的方法学
新意（foundation model 跨设计迁移）值得 High，SSPC 的 incremental PINN 改进
不值得占用精读循环时间。**当前 scorer 把两者放在同一档区分不开**。

## 问题陈述

scorer_v3.txt 的 priority 判定主要看"主题与方向的重合度 + 摘要里的关键词命中"，
对"方法学创新度"和"对 user 主方向的迁移路径明确度"没有显式权重。结果：

- **不算 routing noise**（论文确实是 PDE/ML/PINN/算子学习），但
- **对 user 的实际精读价值参差**：方法学新颖且范式可迁移的 → 真值；
  方法 incremental + 应用域距离远的 → 形式合规但实际无用。

W21 一周内这类长尾约 3–4 篇，占 fea_surrogate 14 篇的 ~25%。**累积一年约 150–200
篇**，足以让精读循环成本失真。

## 提案（方法-应用二维加权）

为 fea_surrogate 方向（以及其他可能受影响的方向）增加一个 **两维子判定**，
**仅在 LLM scorer 内部使用，不改变 priority 枚举**：

1. **method_novelty**：{high, medium, low}
   - high = 新架构 / foundation model / 跨问题迁移 / 新的理论框架
   - medium = 现有方法的有意义改进 / 跨领域应用首次
   - low = 已知技术组合 / incremental 改进 / 单点工程优化

2. **transfer_pathway**：{direct, adjacent, none}
   - direct = 方法可直接用于 user 核心方向问题（如生物力学 FEA / 髋柄 / 骨建模）
   - adjacent = 需要类比迁移（如电子热扩散 → 生物力学弹性，需找算子等价）
   - none = 应用域差异 + 方法无可迁移性

**最终 priority 后处理规则**（在 scorer 给出 priority 后再调整）：

```
if direction in {"fea_surrogate"} and topic_matched:
    if method_novelty == "low" and transfer_pathway == "none":
        priority = "Low"      # 强降级：应用边缘 + 方法 incremental
    elif method_novelty == "high":
        priority = max(priority, "High")  # 方法学创新优先保留
    # 其他情况维持 scorer 原判
```

举例对照（上表）：
- Therm-FM: novelty=high, pathway=adjacent → 维持 High ✓
- SiP CNN 代理: novelty=medium, pathway=adjacent → 维持 Medium ✓
- SSPC PINN: novelty=low, pathway=none → 降到 **Low**（当前 Medium）
- Agentic 地热: novelty=low, pathway=none → 降到 **Low**（当前 Medium）
- NPINN+ 波方程: novelty=low, pathway=none → 降到 **Low**（当前 Medium）

预估 fea_surrogate Medium 池每周减少 3–4 篇（约 25%），精读循环吞吐相应提升。

## 与 CLAUDE.md §1 "recall not precision" 的关系

CLAUDE.md 明确"宁可多收 80 篇 40% 相关，也不收 19 篇 90% 相关"。本提案
**不违反此原则**——前提条件是 `direction in {fea_surrogate}` AND `topic_matched`
都已成立。已经通过 router 入 corpus 的论文，priority 判定本来就是 LLM 的精细化
工作；把"应用 + 方法"二维信息加入是让 priority 更准，**不是收紧 router 召回**。

降级到 Low 仍然保留在 corpus 里，仍然出现在 daily JSON 中，仍然写入 Zotero
低优先级 collection。只是不再进入 review_harness 精读循环（PRIORITIES =
{"high", "medium"}）。

## 不在本 ADR 范围

- **不**新建 scorer_v4.txt（按 CLAUDE.md §4，scorer prompt 改动必须新建版本，
  但本 ADR 仅是提案，不实施）。
- **不**修改 prompts/scorer_v3.txt（不可变）。
- **不**改 review_harness.PRIORITIES 集合。
- 对其他方向（am_biomedical / hip_implant / ai_bioprinting）的等价规则需要
  独立数据支持，本 ADR 暂不覆盖。

## 实施前置条件

W21 单周 27 篇数据量不足以做严肃决策。建议**累计 4 周（W21..W24 共约 100 篇）
fea_surrogate 数据后再决定**：

- 验证"electronics-domain + low-novelty"模式是否稳定存在（不是 W21 偶然）。
- 量化降级到 Low 会丢失多少 false-negative（误降的真有用论文）。
- 检查是否有"应用域电子但方法学高新"的稳定信号（避免一刀切丢 Therm-FM 类
  论文）。

只有数据稳定支持提案后才正式落地为 scorer_v4。

## 验收标准（数据达标后）

- 4 周累计中"应用域电子 + novelty=low + pathway=none"样本 ≥ 12 篇。
- 这些样本中 ≥ 80% 在精读复核结论里被标为"低跟进价值 / 不必精读"。
- 误降率（被降为 Low 但实际有价值的）≤ 5%。

## 决策日志条目（拟入 TODO.md Decision Log）

```
| 2026-05-26 | ADR-0024 草案 | fea_surrogate 二维加权方法-应用 priority；4 周数据后决策 | Claude pilot W21 | Draft |
```
