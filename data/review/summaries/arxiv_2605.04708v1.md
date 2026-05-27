# Differentiable Chemistry in PINNs for Solving Parameterized and Stiff Reaction Systems

- arXiv: 2605.04708v1（2026-05-06）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
标准 PINN 在 **刚性反应动力学**（如氢燃烧）上失败 —— 时间尺度跨越数量级，autodiff 梯度信号不稳。

## 方法
**Differentiable chemistry solver 嵌入 PINN**：
- 把 stiff ODE 反应求解器（隐式 / Rosenbrock 类）作为可微 module 嵌入网络
- 参数化网络架构 + residual 加权
- 联合训练 NN + chemistry solver

## 关键结果
- 求解氢燃烧 stiff ODE/PDE，正问题 + 参数辨识两个任务
- 跨越多个时间 / 浓度量级的可靠收敛

## 与我研究方向的关联
**fea_surrogate (弱相关)**：燃烧化学不是我研究方向；但 **"differentiable solver 嵌入 NN" 范式** 对其他 stiff 问题（如电子封装 thermal cycling, 生物组织 reaction-diffusion）有 transferable value。

## 局限
- 应用单一（氢燃烧）
- Stiff solver 的可微化是已成熟方向（torch.diffeq, DifferentialEquations.jl）

## 评分体系反馈
Direction 较 weak fit。existing_summary 准确。Reference 级。
