# Uncertainty Quantification Methods for Optimal Excitation Design in Parameter Identification

- arXiv: 2605.04691v1（2026-05-06）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**最优激励设计**（optimal excitation design）：给定动力学系统参数 identification 问题，设计能最大化信息量（最小化参数不确定性）的输入信号。传统方法（Fisher information based）需要重复仿真，**计算成本高**。

## 方法
两种 UQ 方法：
1. **Polynomial Chaos Expansion (PCE)**：传播参数不确定性到模型输出，闭式 / 半闭式获取 sensitivity，避免重复仿真
2. **Optimal Transport (OT)**：基于 Wasserstein distance 衡量后验信息增益

## 关键结果
- 与传统重复仿真方法相比显著降低 cost
- **实车实验验证**（车辆动力学参数识别）

## 与我研究方向的关联
**fea_surrogate（弱-中相关）**：
- 严格说是 system identification + control 方向，但**最优激励设计思路在 FEM 反问题中也通用**（例如选取最优实验荷载组合识别材料参数）
- 与本周 [[arxiv_2605.09775v1]] vvBO 互补：vvBO 是模型探索，本文是实验设计
- PCE 思路与 [[arxiv_2605.12540v1]] S-SPH 共享 PCE Galerkin 工具箱

## 局限
- 应用是车辆动力学，非 FEM
- PCE 维度诅咒（高维参数空间难扩展）
- 代码未给链接

## 评分体系反馈
Direction 偏弱 fit。existing_summary 准确。Reference 级收录。
