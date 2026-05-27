# Per-Loss Adapters for Gradient Conflict in Physics-Informed Neural Networks

- **id**: `arxiv:2605.10136v1` · 方向 fea_surrogate · 优先级 High · **read**（摘要）
- **来源**: arXiv 2605.10136, 2026-05-11（**W20**）

## 核心思路

PINN 多损失梯度冲突 → 优化停滞。**Per-loss adapter**：识别冲突类型后用低秩
适配器为每个 loss 创建独立参数子空间。

## 关键结果

60+ PDE 配置上，"方向冲突主导"问题上显著提升性能。

## 与 fea_surrogate 关联

- 是 PINN 工程化问题（数据损失 vs 物理损失梯度冲突）的有意义工程方案。
- 与本周 NTK criterion + BO 边界函数论文（doi:10.1016/j.neucom.2026.133937）+
  W21 CMA-PINN 诊断 + GMM-curriculum-PINN + NPINN+ 等共同构成 PINN 训练
  改进 cluster。**W20+W21 已 6+ 篇 PINN 训练改进**。
- 60+ PDE 配置评估规模可观。

## 评分

priority=High 合理。novelty=high（per-loss low-rank adapter 是有意义新工具），
pathway=adjacent（PINN 工具改进对生物力学 PINN 实操有借鉴）。

## 跟进

中。若 user 用 PINN，可作为多损失冲突场景的工具书。
