# Finite Volume-Informed Neural Network Framework for 2D Shallow Water Equations: Rugged Loss Landscapes and the Importance of Data Guidance

- arXiv: 2605.11001v1（2026-05-09, cs.LG，投 GMD/JAMES 类）
- 作者：Xiaofeng Liu（Penn State，单作者）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
PINN 在 2D 浅水方程（SWE）上有四个结构性弱点：(i) strong-form 残差假设光滑，但 SWE 经常出现 hydraulic jump / 不连续；(ii) 不保证局部质量/动量守恒；(iii) 没有熵条件保证物理 shock；(iv) collocation 点与工程实际的非结构网格脱节。**前人 FVM-PINN 工作多限于 1D 或结构化笛卡尔网格**，没有覆盖工业洪水预报的 2D 非结构网格场景。

## 方法
**Data-Guided FVM-PINN**：

1. **扰动形式 SWE**：状态 Q = [ξ, uh, vh]，其中 ξ = h - h_s 是自由表面扰动；lake-at-rest 时 ξ = 0 让 well-balanced 性质成为代数恒等式。
2. **可微 Roe Riemann solver**（Rogers et al. 2003）+ Harten-Hyman entropy fix；非结构网格 + ghost cell BC。
3. **FVM-PINN loss**：cell-wise 残差 R_i(t_k) = ∂Q_i/∂t + (1/A_i)Σ_f F̂^Roe · ℓ_f − S_i；用 autodiff 算 ∂Q/∂t。
4. **Fourier feature embedding** + tanh MLP + softplus 输出 h ≥ 0。
5. **Data-guided 训练**：L_total = λ_fvm L_fvm + λ_BC + λ_IC + λ_data L_data；数据可以是稀疏现场测量、SRH-2D 模拟参考、或 in-loop FVM "teacher"。
6. **Sequential time-window decomposition**（长仿真扩展性）：[t_0, T] 分成 N 个窗，每窗独立训网络，末态作下窗 IC；warm-start。

## 关键结果
**核心发现：physics-only 失败 + data 至关重要**

**Loss landscape 诊断**：FVM-PINN 在 trivial zero-momentum 状态的损失值**仅比训练得到的真解大 7×**——一个浅 basin，优化器轻易陷入；加入哪怕稀疏数据后，差距扩到 **310×**，破坏简并。这是"FVM 残差在零速度处面积通量 vanishing"的结构性问题，与"wave speed 不准"是不同的失败模式。

**Block-in-channel benchmark（2D，明确的真解参考）**：
- 200 个随机速度测量：velocity-field L2 **降低 22×** vs physics-only
- 50 个测量：**降 7×**
- Physics-on/off ablation：FVM loss 在稀疏数据下贡献 -23%，dense data 下近乎中性

**真实案例：Savannah River（1306 cells, 3600 s 仿真, 5 个 Manning roughness zone）**：以 SRH-2D 输出为 anchor data 学 surrogate；time-window decomposition 让误差**随窗数单调下降**。

**1D dam-break 验证**：正确捕捉左 rarefaction fan + contact wave + right shock。

## 与我研究方向的关联
- **fea_surrogate（间接相关）**：与本周其他 PDE surrogate（[[arxiv_2605.09096v1]] SpectraNet, [[arxiv_2605.09016v1]] CATO, [[arxiv_2605.09523v2]] HS-FNO）共享"非结构网格 + 守恒律 + 长 rollout"主题，但聚焦于 **hyperbolic / shock-capturing** 这一更难的子类。对我的电子封装 / 生物打印（椭圆/抛物为主）只是方法论参考。
- **可借鉴的核心 takeaway**：
  1. **"physics-only 失败 + data essential" 是普适教训**：不仅 SWE，凡是物理残差有 trivial null minimum 的问题（无源稳态椭圆、零应力静态弹性、零通量传热等），都可能掉同样的坑。这一观察可加入 ADR-0024 评分体系作为对"纯物理监督 PINN"的警告。
  2. **Loss landscape 实测诊断方法**：在 trivial 解处计算 loss 值与真解处的比值（这里 7× vs 310×），是一个 cheap 的"physics-only 是否足够"先验。

## 局限
1. **单作者 + 单 GPU 实验**：scale 有限（最大 1306 cells, 3600 s）；工业级 100k+ cell mesh 未验证。
2. **核心失败模式 "trivial low-momentum minimum"** 是 SWE specific？作者承认 "structural property of any cell-conservation loss whose face flux contributions vanish at zero velocity"。其推论是椭圆/抛物等非守恒律 PDE 不直接适用。
3. **"数据" 的来源多依赖 SRH-2D**：Savannah River 实验里 anchor data 来自 calibrated FVM solver，不是真实测量。所谓 "data-guided" 在工程意义上仍依赖昂贵 FVM solver。
4. **没有 baseline 比较**：没有跟 FNO / DeepONet / SpectraNet 这些 neural operator 对比，只跟标准 strong-form PINN 对比。读者无法判断"FVM-PINN 是否比 operator-based 方法值得"。
5. **scalability strategies（cell mini-batching, gradient checkpointing）** 在代码里但论文里只 demo time-windowing，文章 incomplete。
6. **代码 / 数据 repo**：作者声明 "released with the companion code repository" 但 v1 preprint 未直接给链接 —— 需要等期刊版本。

## 是否值得跟进
**保留 Medium 优先级合理**：

- existing_summary 描述基本准确，特别是抓住了 "data essential" 的关键发现。
- 对我**直接应用价值有限**（SWE/河流水力学不是我的领域），但**方法论 takeaway 通用**（trivial minimum 诊断、time-window decomposition、Fourier feature for spatial heterogeneity）。
- **跟进动作**：仅作 reference 收录。如未来要写"PINN 的失败模式综述"则必引。横向追读 Krishnapriyan et al. 2021 (NeurIPS, PINN failure modes)、De Ryck et al. 2024 (wPINN)、Jagtap et al. 2020 (cPINN) 作为 PINN 优化失败 anchor。

## 评分体系反馈
- Direction 正确。Priority Medium 合理。
- existing_summary 准确，无需修正。是 scorer 表现良好的样本。
