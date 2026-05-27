# Meta-Inverse Physics-Informed Neural Networks for High-Dimensional ODEs

- arXiv: 2605.03511v1（2026-05-05）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
高维耦合 ODE 反问题（如 PBPK 药代动力学，33 维）的 PINN 优化困难、跨任务泛化差。

## 方法
**Meta-Inverse PINN**：两阶段元学习
1. 先学**物理感知 representation**（meta-learning across tasks）
2. 固定 representation 优化任务特定参数

## 关键结果
- 33 维 PBPK（**扑热息痛 + 茶碱** 静脉/口服）验证
- 准确恢复动力学参数 + 缺失机制项

## 与我研究方向的关联
**fea_surrogate (中相关)**：高维 ODE 反问题方法对**药物输送、生物力学多尺度模型**有 transferable value。Reference 级。

## 评分体系反馈
Direction 正确。existing_summary 准确。
