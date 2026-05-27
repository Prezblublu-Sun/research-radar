# 复核：Constrained-weight PINN for forward and inverse mechanics analyses

- DOI: 10.1016/j.cpc.2026.110206（**Computer Physics Communications**, 2026）
- 方向归类：fea_surrogate（priority=High）
- pdf_found=false

## 摘要复核
- ✅ "带约束权重的 PINN" + "自适应权重 + UQ"：是 PINN 训练稳定性 + 不确定性方向的标准组合
- ✅ "正反问题 + 弹性梁/热传导":典型力学 benchmark
- CPC 是 Elsevier 数值方法专期，质量信号好

## 优先级复核
**保留 High 合理**：与本周已读的多篇 PINN 改进工作（[[arxiv_2605.08408v1]] AdamFLIP, [[arxiv_2605.12544v1]] DCP-INN, [[arxiv_2605.11001v1]] FVM-PINN）属同一 thread；都在 PINN 训练 robustness 上做改进。本文加 UQ 是相对独特卖点。

## 处置
checked。**建议获取 PDF**：UCL 应能下载 CPC；与本周已读 PINN 工作合并对照即可全面了解 PINN 2026 状态。

## 评分体系反馈
- Direction 正确（fea_surrogate）。priority High 合理（mechanics + UQ + 知名期刊）。
- existing_summary 简短但准确。无错。
