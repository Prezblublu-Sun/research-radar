# Functional-prior-based approaches to Bayesian PDE-constrained inversion using PINNs

- arXiv: 2605.07060v2（2026-05-14 update, physics.geo-ph）
- 作者：Ryoichiro Agata（JAMSTEC）, Tomohisa Okazaki（Kyoto U. DPRI + RIKEN AIP）
- 方向归类：fea_surrogate（priority=High）
- 投 Elsevier（推测 Computers & Geosciences / JCP）

## 研究问题
B-PINN（Bayesian PINN）做 PDE 参数反演时，**先验定义在 NN 权重空间**而非函数空间，导致物理上无法解释；简单 IID Gaussian / Student-t 权重先验可能带来不可控影响。本文目标：**把"我相信参数场 m(x) 是某个 Gaussian process"** 这种物理化先验直接注入 BPINN-based 反演。

## 方法
统一框架 **fpBPINN**，包含两种互补方法 + 一个关键 trick：

1. **FPI-BPINN（Functional-Prior-Informed B-PINN）**：先学一个权重空间高斯先验 p(θ_m) = N(μ, diag(σ²))，使得 NN 推前的样本分布与目标 GP（𝒢𝒫(μ(x), k(x,x'))）匹配；用 **MMD（Maximum Mean Discrepancy）**作为分布距离（vs Tran et al. 2022 用 Wasserstein）。学完先验后再用 **preconditioned SGLD+R**（Langevin + repulsion）做 weight-space Bayesian 推断。优势：训完先验后可复用任何 BNN 推断方法；缺：先验近似有 gap。
2. **fParVI-PINN（Function-Space Particle Variational Inference）**：直接在函数空间做 SVGD —— 用 NN 表达 m(x)，update 在 m 空间上算 ∇_m log P(m|D)，再 push back 到 θ_m 空间通过 Jacobian。优势：精度高，先验直接是 GP；缺：与 ParVI 绑定。
3. **Random Fourier Features（RFF）是关键**：纯 FCNN 难以表示 GP；引入 γ(x) = [cos(2π Bx), sin(2π Bx)], B_{ij} ~ N(0, τ²) 后能匹配 GP。τ = 1/(√(2π) · ℓ)（RBF 核相关长度 ℓ）由 Fourier 变换理论给出闭式。

**PDE 约束的引入**：分离 θ_u（解 NN）与 θ_m（参数场 NN）的训练 —— Bayesian 估计仅对 θ_m 做，θ_u 用 L-BFGS 在每步重新最小化 PDE residual，避免联合训练的维度爆炸 + 尺度差异。Adjoint method 在 PDE 约束下算 ∇_{θ_m} log p(θ_m|D)。

## 关键结果
**两个数值实验**：

1. **1D 地震走时层析**（eikonal equation |∇T|² = 1/v²）：真值 v=1 km/s 常速；两组 receiver，5-50 个 traveltime obs；GP prior μ=1, a=0.1, ℓ ∈ {0.075, 0.15} km。
   - 与 linearized tomography 半解析解（Bayesian linear regression）对比作 ground truth
   - **FPI-BPINN 和 fParVI-PINN 都准确恢复后验**；纯 weight-space IID Gaussian prior 的 B-PINN 表现差。
   - 在无 ray-path 覆盖区域（0-0.2, 0.4-0.8, 1-1.2 km）后验 ≈ 先验，符合物理直觉。
   - 三隐层 NN + ℓ=0.075 setup 需要更多 step（pSGLD+R 3000 + 2000 burn-in，fParVI-PINN 2000）。
2. **2D Darcy flow permeability inversion**：更现实，有 GP 渗透率先验。两种方法都得到 plausible 后验。

**两方法对比**（作者明示）：
- **FPI-BPINN 灵活**：训完先验可接 HMC/SGLD/SVGD/ParVI 等任何方法；但 prior matching 有 MMD-level 的近似 gap
- **fParVI-PINN 精度更高**：直接在函数空间做 SVGD，先验完全保真；但与 ParVI 绑定，无法切换
- RFF 是两种方法**共同**的必备组件。

## 与我研究方向的关联
- **fea_surrogate（直接相关）**：
  - 这是本周第 3 篇贝叶斯 PINN / UQ 主题 paper（[[arxiv_2605.08672v1]] 给收缩理论；[[arxiv_2605.09718v1]] 给 normalizing flow VI for multiscale；本文给 functional prior 实现方法）。三者构成一个完整的"B-PINN UQ 工具箱"。
  - **直接应用价值**：FEA 反问题（材料参数反演、缺陷反演、边界条件估计）的物理先验通常是 spatial smoothness（GP 类），本文方法可以直接用 —— 比传统 grid-based Bayesian inversion + adjoint 灵活很多。
  - **RFF + GP 先验**这一套对我未来做电子封装的"未知材料参数 + 稀疏温度观测"贝叶斯反演问题是个 ready-to-use 模板。
- **跨方向**：
  - 与 vvBO（[[arxiv_2605.09775v1]]）正交但互补：vvBO 是 sample-efficient 设计探索，本文是 UQ 反演 —— 在 FEM-in-the-loop 工程优化里两者可以串联。

## 局限
1. **MMD with RBF kernel** 有 bandwidth 超参（用 median heuristic 选）；vs Wasserstein 距离的 Tran et al. 2022，作者承认 MMD 是 implementation simplicity 的妥协。
2. **每步梯度计算贵**：一次 SGLD+R 迭代需要一次 adjoint + 一次 PINN training；HMC 不可用（每次 leapfrog 需要数百次梯度），因此被迫用 SGLD+R 这类相对粗糙的方法。
3. **仅 GP 先验，不含 non-Gaussian / heavy-tailed**：很多实际场景（如断层、阶跃材料属性）需要更结构化的先验。
4. **2D Darcy 实验规模有限**：grid 大小未明示，但显然不是工业级 10⁵+ DOF。
5. **作者 affiliation 偏向 geoscience**：示例都是 seismic / Darcy；电子工程或生物力学应用未直接证明。
6. **代码未在论文中明示链接**：v2 update 但 GitHub URL 未给。

## 是否值得跟进
**值得跟进，priority High 合理。**

- existing_summary 准确：两个方法、RFF 重要、两个 benchmark、灵活 vs 精度的权衡 —— 全都对。
- **跟进动作**：
  1. **方法实现优先**：当我未来要做"电子封装材料参数贝叶斯反演"时，把 FPI-BPINN（MMD + RFF + GP prior + pSGLD+R）作为首选工具栈。
  2. 横向追读：Tran et al. 2022 (原始 functional prior B-NN)，Wang et al. 2019（fParVI 原始论文），Agata et al. 2023（本作者前作）。
  3. 与本周 [[arxiv_2605.08672v1]] 的理论合并：那篇给出 spike-and-slab 先验的近极小化集中速率；本文给出 GP/functional 先验的工程实现 —— 两者可整合为综述 "B-PINN: 理论与实现"。

## 评分体系反馈
- Direction 与 priority 都对，无修正。
- existing_summary 简洁且准确 —— 是高质量 scorer 输出样本。两个方法的核心区别 "flexibility vs accuracy" 都准确捕捉到了。
