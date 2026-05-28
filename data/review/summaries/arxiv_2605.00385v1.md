# PILIR: Physics-Informed Local Implicit Representation

- arXiv: 2605.00385v1（2026-05-01, cs.LG）
- 作者：Jianfeng Li, Feng Wang（Wuhan U.）, Ke Tang（SUSTech）
- 方向归类：fea_surrogate（priority=High）

## 研究问题
PINN 的 **spectral bias** 让 MLP 偏向学低频，复杂物理高频细节收敛极慢。原因有二：
1. **架构**：MLP 全局 receptive field → 全局参数耦合 → 偏好全局低频趋势，抑制局部高频
2. **映射**：从低维坐标直接映到高维物理场难学，没有有效 feature embedding

已有 grid-based 方法（[Kang 2023/2025]、[Shishehbor 2024]）用确定性插值核（如双线性）混合 grid 值，但 **convex hull 约束 + 引入数值粘性，反而 smear 高频结构**。

## 方法
**PILIR** = 离散 grid encoding + 连续 neural operator generative decoding（受 LIIF / Local Implicit Image Function 启发）：

1. **可学习 grid feature vectors**：每个 grid vertex 关联一个 learnable feature vector（类似 image processing 的 feature channel），替代"原始坐标直接查询"
2. **轻量 neural operator 作为 generative decoder**：把 grid 上的 discrete features synthesize 成连续物理场；**不是机械插值，而是 generative reconstruction**，保留 sub-grid details + 高频
3. 物理损失：标准 PINN residual + BC/IC（在 generative decoder 输出上算 autodiff）

**关键 design shift**：把"从 grid 重构物理场"从 deterministic interpolation 换成 **generative synthesis** —— 解耦 reconstruction quality 与 grid resolution。

## 关键结果
- 多个 challenging PDE benchmark 上超过 SOTA
- 有效缓解 spectral bias，加速高频细节收敛

## 与我研究方向的关联
**fea_surrogate（高度相关）**：
- spectral bias 是工程 FEM surrogate（电子封装焊点尖角应力、生物组织界面）的核心痛点。本文 generative decoding 思路与本周 W19 [[arxiv_2605.12544v1]] DCP-INN（双网络频率解耦）异曲同工 —— 都把"频率难学"转化为架构 inductive bias 而非 loss penalty。
- 与 [[arxiv_2605.09016v1]] CATO（学 chart）、[[arxiv_2605.06203v1]] ACT block（layer-wise coordinate transform）形成"几何/局部性 inductive bias"系列。

## 局限
1. **Grid resolution 仍是超参**：太粗丢细节，太细 grid feature 爆炸
2. **Generative decoder 训练稳定性**：generative 比插值难训
3. **未对照 CATO/ACT** 等 SOTA
4. **代码 / 数据**：未给链接

## 评分体系反馈
Direction 正确，priority High 合理。existing_summary 准确。
