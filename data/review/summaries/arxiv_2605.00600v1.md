# Possibilistic Predictive Uncertainty for Deep Learning

- arXiv: 2605.00600v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 误，应为 generic_ml / uq**

## 研究问题
深度学习 UQ 在"原理严谨性 vs 计算效率"之间矛盾。传统 evidential deep learning 基于 Dirichlet/概率，本文用 **可能性理论 (possibility theory)** 替代。

## 方法
- Dirichlet 近似后验 + projection-approximation 策略
- 效率上接近 deterministic NN，原理上有可能性理论 backing

## 关键结果
- 标准分类 + 回归 benchmark 上 ≈ 或胜 SOTA evidential DL

## 与我研究方向的关联
**fea_surrogate (弱相关)**：generic UQ 方法，对工程 surrogate 仅 reference 价值。Direction misclassification。

## 评分体系反馈
Direction `ml_uq` 更准。existing_summary 准确。
