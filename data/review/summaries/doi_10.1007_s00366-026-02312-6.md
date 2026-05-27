# IGANets: Isogeometric analysis networks and their applications to linear structural analysis problems

- **id**: `doi:10.1007/s00366-026-02312-6` · 方向 fea_surrogate · 优先级 High · **read**（摘要）
- **来源**: Engineering with Computers, 2026-05-11（**W20**）

## 核心思路

**IGANets** = 样条基 + 物理信息 ML，从物理模型直接构建配点格式。结合 Isogeometric
Analysis（IGA）思路——CAD 几何模型直接用作 FE 模型，无需 mesh 离散化。

## 关键结果

- 在 Poisson + 线弹性问题上验证。
- 变几何 I 型梁多实例测试——预测精度随训练样本增加而提高。

## 与 user 关联

- **直接相关 fea_surrogate**：IGA 是计算力学的成熟方向，与 user 的 hip 几何
  代理建模高度同构（CAD → FE 一体化）。线弹性 + 变几何 = 关节生物力学的
  典型 setup。
- 与 W20 NEST（Neural-Schwarz Tiling）形成对照——NEST 是 voxelization + Schwarz
  domain decomposition，IGANets 是 spline-based + IGA。两条路线对"几何泛化 +
  FEA 代理"都有方法学贡献。
- 与本周 IKNO / Therm-FM / MMGUNet 同 cluster。

## 评分

priority=High 合理。novelty=high（IGA + NN 是有意义的组合），pathway=adjacent。

## 跟进

中-高。把 IGA-aware NN 思路记入 fea_surrogate "几何感知架构"工具箱。机构权限取 PDF
看变几何 I 型梁的具体方法（是 user 的"不同患者股骨"模式同构）。
