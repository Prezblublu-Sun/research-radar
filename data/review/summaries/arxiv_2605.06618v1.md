# MTRBO: Multiple Trust-Region Based Bayesian Optimization

- arXiv: 2605.06618v1（2026-05-07）
- 方向归类：fea_surrogate（priority=Medium）
- 应用：高维 BO + 投资组合优化

## 研究问题
高维 BO 中单一 trust region (TuRBO 类) 受限于探索能力；本文用**多个 trust region 并行**，分别用后验均值（exploitation）+ 方差（exploration）驱动。

## 方法
**MTRBO**：维护多个 trust region，每个 region 独立 GP surrogate，按贡献 dynamic 分配 budget；用 acquisition function 同时考虑 local 开发 + global 探索。

## 关键结果
- 在多个高维非凸 benchmark 上超过单 TR baseline
- 投资组合优化真实案例验证

## 与我研究方向的关联
**fea_surrogate（弱相关）**：本文是通用 BO 方法学，对 FEM-in-the-loop 工程优化（高维参数空间）可用，但与本周更强的 vvBO [[arxiv_2605.09775v1]] 相比是 incremental 工作。**对 PDE/FEM 无 surrogate 内核**，仅是 BO 外层的策略改进。Reference 级。

## 局限
- 投资组合应用与 FEM 评分体系无 transferability
- 没有 PDE benchmark
- 本周已读高质量 BO 工作 [[arxiv_2605.09775v1]] vvBO 更直接相关

## 评分体系反馈
- Direction `fea_surrogate` 偏，应为 `ml_bo`。本周 direction misclassification 多次出现。
