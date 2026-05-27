# Bayesian Optimization with Structured Measurements: A Vector-Valued RKHS Framework

- arXiv: 2605.09775v1（2026-05-10, cs.LG）
- 作者：Wenbin Wang, Colin N. Jones（EPFL Automatic Control Laboratory）
- 方向归类：fea_surrogate（priority=High）

## 研究问题
经典贝叶斯优化（BO）把每次查询的输出当作**标量** F(x)，但很多实际系统的物理输出是一条**轨迹 / 场 / 函数**（trajectory / spatial field / time series），最终标量目标只是这些结构化输出的某个线性泛函（如：建筑控制中"成本=电价×功率轨迹"的时间积分）。直接学 x↦F(x) 等于扔掉了 trajectory 里大量信息。已有方法分两路：
- multi-task / multi-output BO（[11, 38, 41]）—— 还是用一堆标量观测，依赖人工设计相关阵；
- BO with augmented input（FFBO [20]、[30]）—— 把线性泛函当作"扩展输入"，把矢量观测投影回标量，浪费结构。

**核心目标**：建立一个把"未知矢量算子 + 已知线性测量算子"原汁原味放进 BO 的框架，并给出可证明 sublinear regret 的算法。

## 方法
**框架**：optimize F(x) = ⟨m, Mf(x)⟩_M，其中
- f: X → Y 是未知向量算子，落在向量值 RKHS H 中，‖f‖_H ≤ Γ；
- M: Y → M 是**已知**有界线性测量算子；M 是测量空间（也可无限维 Hilbert）；
- m ∈ M 是定义目标的线性泛函；
- 每次查询得到 y_t = Mf(x_t) + δ_t，δ_t sub-Gaussian。

**统一性**：M=I 是"全观测向量"极限；M 为标量线性泛函就回退到经典标量 BO；中间任意 M 是观察 richness 与信息量的可调参数。

**关键技术（章节 3-4）**：
1. **诱导核（induced kernel）**：定义 K^M(x,s) = M K(x,s) M*；Lemma 1（来自 Carmeli et al. 2010）表明 K^M 是测量空间 M 上的再生核，对应 RKHS H_M 连续嵌入 H。
2. **测量空间里的 KRR 估计**：μ_t(x) 由 Eq. (2) 求解；其在测量空间的观测 Mμ_t(x) 等价于直接用 K^M 做 KRR，避免在 Y 上各方向逐一控制误差（"不可观方向"无意义）。
3. **Theorem 1（高概率集中不等式）**：在 sub-Gaussian 噪声 + bounded RKHS norm + trace-class 操作核三条假设下，
   ‖Mf(x) - Mμ_t(x)‖_M ≤ [Γ + (σ/√λ)·√(2log(1/ζ) + log det(I + λ⁻¹K^M_{X_tX_t}))] · ‖K^M_t(x,x)‖_op^{1/2}
   —— 这是标量 BO 的 Srinivas et al. [40] / Chowdhury-Gopalan [10,11] 结果在测量空间的直接推广，关键创新是直接在 M 而不是 Y 上做不确定性量化。
4. **vvBO 算法（Algorithm 1）**：UCB 范式，
   x_t = argmax_x ⟨m, Mμ_{t-1}(x)⟩ + β_{t-1} ‖m‖ ‖K^M_{t-1}(x,x)‖_op^{1/2}
5. **Theorem 2-3（regret 上界）**：对一般情形给出 R_T 上界（Thm 2），并对 **separable kernel** K = G⊗B 给出显式 sublinear 速率（Thm 3）：
   - Linear kernel: O(log T · √T)
   - Gaussian: O((log T)^{d+1} · √T)
   - Matérn (ν > d(d+1)/2 类条件)：O(T^{d(d+1)/(2ν+d(d+1))} log T · √T)
   速率与标量 BO 同阶，**没有为观察更丰富的结构化测量额外付出收敛阶代价**。
6. **扩展**：时变目标（mt 随 t 改变）可直接复用 confidence set；对 trajectory 的非线性 Lipschitz 函数也可处理（Appendix G）；通过算子核谱分解 + 截断给出可计算实现（Appendix H）。

## 关键结果与数据
- **合成基准（Ackley、Eggholder 等三个测试算子）**：分三阶段切换不同的 m_i（同一 trajectory 但不同 functional），vvBO 在 simple regret 和 cumulative regret 上全面优于 BO / rBO / MTBO / rMTBO / FFBO / CTBO；尤其 CTBO 在每个新 context 都要大量探索，cumulative regret 显著高于 vvBO。
- **真实场景：MPC 调参 + 建筑能耗控制（BOPTEST 测试床，8500 m²、~1350 人）**：3 个 MPC 控制参数（散热器阀门）；目标 = 能耗 + CO₂ + 热不适加权和；引入正弦时变电价；200 次迭代。
  - vvBO 在第 150 次以后能"高价时降温省钱、低价时升温补舒适"，显著削峰；
  - 在 **未见过的新目标**（"最小化某时段峰值供热功率"，validation）上 vvBO 依然给出最优参数，CTBO 在未见 context 下表现差 —— 说明 vvBO 通过结构化测量实现了真正的"跨目标信息迁移"。
- **代码与超参数**：未在正文中给出 GitHub 链接；λ、β 的设置在 Appendix I.1。

## 与我研究方向的关联
**对 fea_surrogate 方向（[[ADR-0024]] surrogate electronics domain scoring）的直接价值很高。**

1. **FEA 的天然结构化输出**：FEA 的每次"昂贵查询"产出的是整张应力 / 位移 / 温度场，而工程目标（最大 von Mises、最大变形、平均温度、动柔顺度…）几乎全是这张场的线性泛函（或可被良好近似的非线性 Lipschitz 泛函）。经典 BO 调几何参数时只取标量目标 ⇒ 浪费 99% 的 FEA 输出。本文给出的 vvBO 框架正好对应这种 setup：x = 几何/材料参数，f(x) = 全场解（Y = L²(Ω) 或 Sobolev 空间），M 可以是采样某点 / 在某子区域积分 / 投影到主成分基。
2. **多目标 / 多 use case 的免费迁移**：同一个 FEA 几何在产品演进中常需要重新评估不同 KPI（强度→刚度→热→振动），传统做法每次都要重新打 surrogate；vvBO 表明只要这些 KPI 都是同一场的线性泛函，**已采集的样本可零成本迁移**。对实验室昂贵 FEA 代次的成本节约可能数量级。
3. **方法论可直接搬用**：separable kernel K = G⊗B 的工程含义是 "x 空间核 G 描述设计变量相似度 × Y 空间核 B 描述场的相关结构"；B 可以由一组已有 FEA 样本通过 KL 展开 / POD 估计 —— 这与已经成熟的 reduced-order modeling / POD 方法天然兼容。
4. **跨方向衔接**：
   - **rl_world_model（[[ADR-0021]]）**：RL × BO 的接口是 dynamics model 的不确定性量化；本文测量空间 KRR 的集中不等式可作为 model-based RL world model 的 calibrated uncertainty 工具。
   - **ai_bioprinting**：与今天另一篇 FrameTwin（[[arxiv_2605.09362v1]]）有意外呼应 —— 那篇用 NN 变形场对齐"目标 vs 观测"轨迹，与本文 vvBO 的"linear functional of trajectory" 视角是同一类信号处理问题在两个领域的不同呈现。

## 局限
1. **理论核心受限于 separable kernel** 才给出显式速率（Theorem 3）；非可分核情形只有 Theorem 2 的隐式 bound，实际收敛率难以预估。
2. **无约束设置**：作者明确说没处理 trajectory / output 上的约束（这恰恰是工业问题最痛的地方 —— 应力上限、最大温升等都是 trajectory-level 约束，需要 safe BO / constrained BO 的扩展，已被列为 future work）。
3. **测量算子 M 必须已知且有界线性**：FEA 场景里大部分目标算子是显式知道的（积分、点估值、特征值），但若目标是某个非线性度量（如疲劳寿命的非线性损伤累积）则需要 Lipschitz 扩展（Appendix G），收敛性会退化。
4. **维度诅咒**：高维 X（>20-30 设计变量）下 Gaussian/Matérn 核的 (log T)^{d+1} / T^{d(d+1)/(2ν+d(d+1))} 项快速恶化，与所有 GP-based BO 共病。
5. **算法计算成本**：测量空间 KRR + det(I+λ⁻¹K^M_{X_tX_t}) 在每步都要算一次大型算子 Gram 矩阵；t 大时 O(t³·dim(M)) 级别，作者依赖谱截断（Appendix H）做工程缓解，但实际可行性尺度（多大 T、多高 dim(M)）未在论文里量化。
6. **真实实验只有 1 个**：建筑 MPC 调参。FEA / 工程设计场景未直接验证（这也是给我留的论文 idea 空间）。

## 是否值得跟进
**强烈值得跟进。** 几个原因：
1. **对我研究主线（FEA surrogate 评分体系）有直接概念性贡献**：在审阅 surrogate paper 时，可以问一个新问题 ——"这个 surrogate 是否能用一次 FEA call 服务多个 downstream objective？"，这是一个被本文显著放大的设计维度，建议把这一项加入 [[ADR-0024]] 的评分 rubric。
2. **作者团队跟进**：Colin Jones 组（EPFL Automatic Control）+ Wenbin Wang 的相邻工作 [44] (personalized building climate control with contextual preferential BO, arXiv 2512.09481), [45,46] (Wenjie Xu primal-dual contextual BO) 形成一个连贯的 contextual / structured BO 线索 —— 值得整个 thread 追读。
3. **代码 / 复现**：论文未直接给链接，需要去 EPFL Automatic Control Lab 主页或 OpenReview 找；若在 NeurIPS/ICML 收录会有代码。建议把"找代码 + 跑一个 FEA toy 例子（如悬臂梁多 KPI）"列入下一阶段实验计划。
4. **评分体系反馈**：scorer 把它判为 fea_surrogate / High 是准确的；但论文同时跨 multi-task learning、operator learning、control，scorer 似乎没记录这种 multi-direction overlap。建议下次 scorer prompt 迭代（v4）增加"cross-direction tags"字段。
