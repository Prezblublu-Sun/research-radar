# Quantitative Sobolev Approximation Bounds for Neural Operators with Empirical Validation on Burgers

- arXiv: 2605.08170v1（2026-05-04）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
神经算子（FNO）在 Sobolev H^t 范数下的定量逼近性质缺乏分析；标准 training 用 L² loss，可能不足以保 H^1 收敛。

## 方法
- 算子学习的 functional-analytic 框架
- 证明 FNO 在 H^t 范数下的逼近界（定量）
- **用 H¹ loss 训练 FNO**（替代标准 L² loss）

## 关键结果
- 1D viscous Burgers benchmark
- H¹ 误差低至 **10⁻⁷**
- 经验 scaling exponent **~1.4**

## 与我研究方向的关联
**fea_surrogate (相关)**：理论 + 训练损失改进。**H¹ loss 训练 FNO** 是简单有效的改进，可作为我未来 FNO 工作的默认选择。与本周 [[arxiv_2605.08672v1]] B-PINN 理论形成 "theory of neural PDE solvers" 主题。

## 评分体系反馈
Direction 正确。existing_summary 准确。
