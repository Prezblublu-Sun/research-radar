# Geometry-aware energy-based physics-informed neural network for geometric parametric modeling in computational mechanics

- **id**: `doi:10.1016/j.compstruc.2026.108285` · 方向 fea_surrogate · 优先级 High · checked
- **失败原因**: no_open_access_link（Computers & Structures，Elsevier 收费）

## 复核

- **方向**：正确。能量基 PINN + 几何参数化 + 计算力学，是 fea_surrogate 的核心
  方法学路径之一（与 Therm-FM 的算子学习路线互补：PINN 是无监督残差/能量最小化，
  算子学习是有监督函数空间映射）。
- **优先级 High**：合理。理由：(a) energy-based 比 residual-based PINN 在数值稳定性
  上有理论优势；(b) "几何感知" + "参数化建模"直接对应 fea_surrogate 在患者特异
  解剖/植入物几何变化上的痛点；(c) Computers & Structures 是计算力学一线期刊。
- **摘要质量**：**偏弱**。motivation、result 都很泛（"提高效率"、"高精度"），
  缺关键定性信息：几何感知是怎么实现的（参数化方式？SDF？图神经网络？）、
  能量基损失的具体形式（势能 vs 互补能）、对比 baseline 是谁、加速比是多少。
  这种摘要在 routing 决策上够用，但作为后续判断"是否花精力找 PDF"的输入不足。
- **跟进**：值得。机构权限取 PDF 后重点看：(1) 几何如何离散输入（mesh-based vs
  point cloud vs SDF）；(2) 能量泛函形式；(3) 在多少不同几何上做了泛化测试。

## 评分系统反馈

priority=High 正确，但 **summary_zh 质量明显低于本周其他 High 论文**。
观察：可能是原文摘要本身就抽象（学术写作风格），LLM 没有"放大有效信息"的能力。
未来可以在 scorer prompt 中增加："对方法部分，必须复述具体技术名词（PINN、CNN、
能量泛函形式等），不可用通用词替代"。
