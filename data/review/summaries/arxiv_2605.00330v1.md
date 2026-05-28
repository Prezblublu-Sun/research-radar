# Conformalized Quantum DeepONet Ensembles for Scalable Operator Learning with Distribution-Free UQ

- arXiv: 2605.00330v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
DeepONet 推理复杂度高 + 无 distribution-free UQ。

## 方法
- **量子正交网络**降低 DeepONet 推理复杂度（quantum-inspired，不一定真量子硬件）
- Conformal prediction 套在 ensemble 上 → distribution-free coverage guarantee

## 关键结果
- 合成 PDE + 电力系统动力学
- 校准 UQ + 准确预测

## 与我研究方向的关联
**fea_surrogate (弱-中相关)**：与本周 [[arxiv_2605.08561v1]] CONTRA、[[arxiv_2605.03233v1]] conformal、[[arxiv_2605.01868v1]] BNF 同 conformal UQ 主题；与 DeepONet 思路结合后对工程 surrogate UQ 有应用价值。"Quantum" 措辞需谨慎 —— W19 已观察过 [[arxiv_2605.12544v1]] DCP-INN 同样 quantum-inspired 表述其实是 gradient-statistics weighting，不是真量子。本文需读全文确认是哪一类。

## 评分体系反馈
Direction 正确（弱）。existing_summary 准确。
