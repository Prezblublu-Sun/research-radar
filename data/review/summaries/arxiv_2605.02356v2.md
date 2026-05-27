# ZNO: Stable Rational Neural Operators in the Z-Domain for Discrete-Time Dynamics

- arXiv: 2605.02356v2（2026-05-04）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
现有 neural operator 多为连续时间；**离散时间动力学**（控制系统、数字信号）需专门建模。

## 方法
**Z-domain Neural Operator (ZNO)**：在 z 域用 **stable rational filter** 参数化算子（自动 causal + stable by design）。

## 关键结果
- 近单位圆 + long memory 任务上最低平均误差
- 5 个非线性系统辨识 benchmark；非通用替代

## 与我研究方向的关联
**fea_surrogate (弱相关)**：离散时间控制系统 surrogate；对工程 FEM 时间步进 surrogate 有 transferable value，但应用偏 system identification。Reference 级。

## 评分体系反馈
Direction `system_id / control` 更准。existing_summary 准确。
