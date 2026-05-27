# Amortized VI for Joint Posterior and Predictive Distributions in Bayesian UQ

- arXiv: 2605.03710v1（2026-05-05）
- 方向归类：fea_surrogate（priority=High）

## 研究问题
传统 Bayesian 预测推断分两阶段（先 posterior 后 predictive），高保真模型中计算昂贵。

## 方法
**Joint VI**：直接逼近 **posterior-predictive** 联合分布；用 **KL 散度上界 + 矩正则化** 替代两阶段近似。

## 关键结果
- 解析 benchmark + **有限元固体力学**算例
- 联合预测分布更准 + 在线推断成本大幅降低

## 与我研究方向的关联
**fea_surrogate（直接相关）**：FEM 固体力学 UQ 应用 + amortized VI 框架；与本周 [[arxiv_2605.07060v2]] functional-prior B-PINN, [[arxiv_2605.08672v1]] B-PINN 理论 形成 UQ 工具箱。FEM 应用是直接命中。

## 评分体系反馈
Direction 正确，priority High 合理（FEM 应用 + 实用 amortized VI）。existing_summary 准确。
