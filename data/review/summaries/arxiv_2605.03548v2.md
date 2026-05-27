# PerFlow: Physics-Embedded Rectified Flow for Efficient Reconstruction and UQ of Spatiotemporal Dynamics

- arXiv: 2605.03548v2（2026-05-05）
- 方向归类：fea_surrogate（priority=High）

## 研究问题
从稀疏 / 不规则测量重建 PDE 场 + 提供 UQ；现有 diffusion-based 方法慢（多步），引导（guidance）方法易违反物理约束。

## 方法
**PerFlow** = Rectified Flow + 解耦"观测条件"与"物理约束"：
- 观测条件作为 conditioning（数据 fit）
- 物理约束通过 **constraint-preserving projection** 在每个 flow step 后投影（hard physics）
- Rectified flow 训练，**1-step / few-step 推理**

## 关键结果
- 多 PDE benchmark 高精度重建 + 物理一致
- 推理速度 **比 guided diffusion baseline 快 320×**

## 与我研究方向的关联
**fea_surrogate（高度相关）**：与本周 [[arxiv_2605.06916v1]] Tyche 类似（1-step rectified flow），但应用于**通用 PDE field reconstruction + UQ**，对工程逆问题（应力场重建、温度场重建）直接可用。和 [[arxiv_2605.07060v2]] functional-prior B-PINN 互补。

## 局限
- 物理约束 projection 实现细节关键
- v2 update，可能仍在调整
- 代码未给链接

## 评分体系反馈
Direction 正确，priority High 合理（速度 + 物理 + UQ 三轴齐全）。existing_summary 准确。
