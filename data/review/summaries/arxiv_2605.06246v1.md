# Structure-Preserving Gaussian Processes Via Discrete Euler-Lagrange Equations (LGPs)

- arXiv: 2605.06246v1（2026-05-07, cs.LG）
- 作者：Jan-Hendrik Ewering（Leibniz Hannover）, Kathrin Flaßkamp（Saarland）, Niklas Wahlström, Thomas Schön（Uppsala）, Thomas Seel（Hannover）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
学动力学模型时，**energy drift**（长时积分能量漂移）是普遍问题。Lagrangian/Hamiltonian Neural Networks (LNN/HNN) 用 Lagrange-d'Alembert 原理作 hard inductive bias 缓解这个问题，但 prior work 三大局限：(i) 不严格保 energy conservation 的结构；(ii) 无 UQ；(iii) 需要 velocity/momentum 数据（实际中常只有 position 数据，如 motion capture, visual servoing）。

## 方法
**Lagrangian Gaussian Processes (LGPs)**：

1. **核心**：把 GP 后验通过**离散 forced Euler-Lagrange 方程**条件化 —— GP prior 不直接放在动力学场上，而是放在**Lagrangian L** 和 **外力 F** 上：L ~ GP(0, κ_L), F ~ GP(0, κ_F)
2. **离散变分原理 → 线性算子条件**：discrete forced E-L: L_D[L_∆] + F_D[F_∆^±] = 0 → 这是 GP 上的**线性算子条件**，闭式求解
3. **由 d'Alembert 原理保证 energy-consistency by construction**（在无外力时严格保 Lagrange 结构）
4. **只需 position 数据**：不像 LNN/HNN 要 velocity；变分离散化的"discrete momentum"是自动恢复的
5. 同时给出 discrete LGP 和 continuous LGP 两个版本（continuous 用 implicit integration 算子）

## 关键结果
- **合成 + 真实案例**包括 real-world soft robot with hysteresis
- Data-efficient，stable long-term prediction
- 提供物理一致 + UQ

## 与我研究方向的关联
- **fea_surrogate（相关，但偏 dynamics）**：本文是 dynamics + control 方向，非典型 FEM；但 Lagrangian-structured surrogate 思路对**电子封装中的振动 / 力学动力学**、**生物打印中的 robotic arm 控制**有迁移价值。
- **soft robot + hysteresis 应用**：与 [[arxiv_2605.09362v1]] FrameTwin（线框 3D 打印 robot control）的 dynamics-aware control 理念相通。
- **方法学**：用线性算子在 GP 上施加 PDE/ODE 约束是 [[arxiv_2605.09775v1]] vvBO 的"linear measurement operator" 的姊妹思路。

## 局限
1. **应用 dynamics，非 FEM static**：direction `fea_surrogate` 略宽泛，更准确应是 dynamics_surrogate
2. **GP scalability**：discrete E-L 条件化的 GP 计算仍受 O(N³) 限制；对长 time series 不可扩展（vs CUTS-GPR [[arxiv_2605.08036v1]] 的高维 scalability）
3. **Lagrangian 必须 well-defined**：含有阻尼 / 非保守内力的复杂系统需要小心建模 F^±
4. **代码 / 数据**：未给链接

## 是否值得跟进
**Priority Medium 合理**。

- 方法学严谨，与 dynamics 控制 + UQ 主题相关。对我研究主线只是 reference value。
- 跟进动作：reference 收录。

## 评分体系反馈
- Direction `fea_surrogate` 略宽，**更准确应为 dynamics_surrogate / structured_ml**。本周已多次出现 direction 混淆。
- existing_summary 准确（Lagrangian GP、E-L 方程、位置数据、soft robot 案例）。无错。
