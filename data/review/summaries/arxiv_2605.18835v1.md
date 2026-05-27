# StampFormer: A Physics-Guided Material-Geometry-Coupled Multimodal Model for Rapid Prediction of Physical Fields in Sheet Metal Stamping

- **id**: `arxiv:2605.18835v1` · 方向 fea_surrogate · 优先级 High · **read**（摘要 + 引论）
- **来源**: arXiv 2605.18835, 2026-05-13（**W20**）

## 核心思路

冲压 FEA 耗时；现有代理或忽略材料属性、或只出标量。**StampFormer** 用 Swin-UNet
backbone，**多模态融合几何与材料应力-应变数据**，预测物理场（位移、应力）。

## 关键结果

- 钢和铝面板数据集上平均相对误差 < 8.5%
- 位移场 MSE < 1.2 mm²

## 与 fea_surrogate 关联

- 多模态（几何 + 材料）融合思路对**患者特异 FEA**有借鉴——不同骨密度 +
  不同几何同时输入是核心需求场景。
- Swin-UNet backbone 在视觉领域成熟，应用到 FEA 代理是合理选择。
- 应用是冲压（large deformation 弹塑性）—— 与生物力学差异大，但方法学迁移路径
  明确。

## 评分

priority=High 合理（多模态架构 + 物理场预测组合是有方法学价值的 application）。
按 ADR-0024：novelty=medium-high（multimodal 融合 + Swin-UNet 应用），
pathway=adjacent。

## 跟进

中。把 multimodal geometry+material 思路记入 fea_surrogate 架构清单。
