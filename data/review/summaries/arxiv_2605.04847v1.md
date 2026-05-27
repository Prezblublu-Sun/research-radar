# Quantile-Free Uncertainty Quantification in Graph Neural Networks (QpiGNN)

- arXiv: 2605.04847v1（2026-05-06）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 偏，应为 generic_ml/GNN**

## 研究问题
GNN 在节点回归 / 链接预测任务中需要 prediction interval（PI）做高风险决策；现有方法依赖 quantile loss 或 conformal post-hoc，UQ 质量参差。

## 方法
**QpiGNN**：
- 双头架构（mean + width）
- **Quantile-free** 联合损失直接优化 coverage probability + interval width
- 端到端 differentiable

## 关键结果
- 19 个 benchmark 平均 coverage +22%，width -50%

## 与我研究方向的关联
**fea_surrogate (弱相关)**：GNN UQ 对 mesh-based PDE surrogate 有潜在 transfer value（FEM mesh 自然是图），但本文应用是 social / citation graph 等，未涉及 PDE。Reference 级。

## 评分体系反馈
Direction 应为 `ml_uq` 或 `gnn`，不是 `fea_surrogate`。本周累计 direction misclassification 信号充分。existing_summary 准确。
