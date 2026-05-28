# ALE-Consistent Graph Neural Operator-Transformer Framework for Fluid-Structure Interaction

- arXiv: 2605.00937v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**FSI (Fluid-Structure Interaction)** 长期预测在变形网格（ALE，Arbitrary Lagrangian-Eulerian）上代价高。

## 方法
**ALE-consistent GNO-Transformer**：
- Graph Neural Operator 处理变形网格拓扑
- Transformer 做时序长依赖
- LSTM 耦合结构预测
- 两阶段训练

## 关键结果
- 柔性梁振动 benchmark：长期相位一致
- 泛化到入口剖面变化

## 与我研究方向的关联
**fea_surrogate (中相关)**：FSI 与生物打印 fluid-structure（喷射、ink-substrate 接触）、心血管血流 + 血管壁有交集。Graph + Transformer 思路与本周 W19 [[arxiv_2605.05488v1]] flux NO with ViT 类似。Reference 级。

## 评分体系反馈
Direction 正确。existing_summary 准确。
