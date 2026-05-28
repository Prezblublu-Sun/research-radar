# Knowing when to trust machine-learned interatomic potentials (PROBE)

- arXiv: 2605.00640v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**MLIP (machine-learned interatomic potential)** 在分子动力学 / 材料模拟中 UQ 困难：ensemble 法成本高、误差信号弱。

## 方法
**PROBE**：用预训练 MLIP 的**冻结表示**训练判别分类器做 selective classification → 高效 UQ + monotone 误差信号。

## 关键结果
- 2 个 MLIP 架构上的大规模测试
- 可靠性概率 + 误差单调性优于 ensemble

## 与我研究方向的关联
**fea_surrogate (中相关)**：MLIP 主要用于第一性原理材料 / 分子模拟，与 FEM 直接关联弱，但**"用冻结特征 + 判别分类器替代 ensemble UQ"思路对任何 NN surrogate UQ 通用**。对电子封装 / 生物医学的 FEM surrogate 是 reference 级方法。

## 评分体系反馈
Direction 正确（弱）。existing_summary 准确。
