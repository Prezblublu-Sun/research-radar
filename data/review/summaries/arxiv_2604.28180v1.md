# Adaptive Wavelet-Based PINN for Localized High-Magnitude Source Problems

- arXiv: 2604.28180v1（2026-04-30）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
PINN 在 **局部高强度源项** 问题（点 / 线热源、奇异性）上失败：spectral bias + 损失项尺度差 10^10:1，autodiff 在源附近数值不稳。

## 方法
**Adaptive wavelet-based PINN**：
- 用 wavelet basis 替代纯 NN 表达
- **动态调整 wavelet 基函数**（adaptive scale + location）
- **避免 autodiff**（用 wavelet 解析导数）
- 这是 PINN + classical 自适应方法的 hybrid

## 关键结果
- 瞬态热传导、Poisson 问题（含点源、线源）
- 损失比 10^10:1 仍能收敛

## 与我研究方向的关联
**fea_surrogate (中相关)**：电子封装焊点是天然的局部高源（热源、应力集中）。Wavelet PINN 对这类奇异性问题是直接 transferable 工具。与本周 [[arxiv_2605.12544v1]] DCP-INN（双网络频率解耦）、[[arxiv_2605.00385v1]] PILIR（局部 implicit representation）同"局部高频"主题。Reference+ 价值。

## 评分体系反馈
Direction 正确。existing_summary 准确（包含损失比 10^10:1 关键数字）。
