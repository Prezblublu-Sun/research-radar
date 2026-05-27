# Comparing EPGP Surrogates and Finite Elements Under Degree-of-Freedom Parity

- DOI: 10.32473/flairs.39.1.141836（FLAIRS 39, 2026）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
NN surrogate vs FEM 精度对比通常**不在等参数条件下**（surrogate 通常用更多参数）。本文做**DOF parity** 公平对比，方法是 boundary-constrained EPGP（Exponential Polynomial GP）。

## 方法
- Boundary-constrained EPGP surrogate: 指数多项式基 + penalized least squares
- 与 Crank-Nicholson FEM 在相同 DOF 下做 head-to-head 比较
- 2D 波动方程

## 关键结果
- 同 DOF 下 B-EPGP 比 CN-FEM 精度高约 **2 个数量级** (L2 error)

## 与我研究方向的关联
**fea_surrogate（相关）**：DOF parity 比较思想值得吸收。但单一 toy benchmark（2D wave），扩展性未知。Reference 级。

## 评分体系反馈
Direction 正确。existing_summary 准确。
