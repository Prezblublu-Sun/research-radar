# Online Safety Filter for Deformable Object Manipulation with Horizon-Agnostic Neural Operators

- arXiv: 2605.01069v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
RL-based 可变形物体操控（流体、软体）通常用 reward shaping 间接编码安全性，**无约束满足保证**。

## 方法
- **Horizon-agnostic NO**：学一个 NN 算子能预测任意时间窗的演化
- **Boundary control barrier function (CBF)** 作 safety filter
- 在线：NO 预测未来状态 → CBF 判断是否进入不安全区 → 修正控制

## 关键结果
- FluidLab 仿真：安全轨迹率 +22%，到达安全集步数减少

## 与我研究方向的关联
**fea_surrogate (中相关)**：可变形物体操控 + NO + safety 与生物打印的 robotic deposition（FrameTwin 类）、ink 流变控制有概念交集。与 [[ADR-0021]] rl_world_model 方向直接相关（NO 作为 world model + safety constraint）。Reference 级。

## 评分体系反馈
Direction 偏弱 fit，应为 `rl_safety` 或 `robotics_manipulation`。existing_summary 准确。
