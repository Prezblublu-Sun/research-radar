# Bayesian Nonparametric Mixed-Effect ODEs with Gaussian Processes (MEGPODE)

- **id**: `arxiv:2605.13088v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.13088, 2026-05-13（**W20**）

## 核心思路

参数化 mixed-effect ODE 易受 misspecification 影响 + 缺 UQ。**MEGPODE** 用 GP
分别建模群体和个体动力学 + 状态空间 GP + 虚拟观测高效推断。

## 与 user 关联

- 验证 benchmark 包含 "生物医学系统" —— 可能涉及药代/疾病动力学。
- 但实际 user 主线（生物力学 FEA）不直接相关。
- 方法学（GP-based mixed effects + UQ）对临床患者特异建模有借鉴。

## 评分

priority=Medium 合理。novelty=medium。pathway=adjacent。

## 跟进

低。除非 user 做患者群体差异建模。
