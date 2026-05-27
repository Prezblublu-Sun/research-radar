# HS-FNO: History-Space Fourier Neural Operator for Non-Markovian Partial Differential Equations

- arXiv: 2605.09523v2（2026-05-12, cs.LG）
- 作者：Lennon J. Shikhman（Georgia Tech, College of Computing）
- 方向归类：fea_surrogate（priority=Medium）
- 代码：https://github.com/lennonshikhman/hs-fno（明确给出）

## 研究问题
神经算子（FNO / DeepONet）做时间相关 PDE 代理时，**标准的自回归形式 G_θ : u(t,·) ↦ u(t+Δt,·) 隐含假设瞬时场就是完整状态**。这对延迟 PDE（DPDE）、记忆驱动系统、Mori-Zwanzig 粗粒化闭包不成立 —— 两个轨迹在 t 时刻完全相同、但因历史不同就有不同的未来。`u(t,·)` 本身不再是单值映射的输入，逼神经算子学习一个并非单值的映射。该问题在分布内一步预测时可能被掩盖，但**在 autoregressive rollout、延迟扰动、参数迁移和反馈场景下会显著放大**。

## 方法
**核心思想**：把状态从瞬时场提升到"历史场" u_t(θ,x) = u(t+θ,x), θ ∈ [-τ, 0]；evolution 是 S_Δt : u_t ↦ u_{t+Δt}（C([-τ,0]; X) 上的算子）。

1. **算子分解**（关键创新）：
   - **PΘ**：FNO predictor，只预测**新暴露的未来切片** û(t+Δt, ·) = PΘ(u_t, μ, τ, Δt)
   - **ShiftAppend**：对已知的历史窗口部分 [-τ, -Δt] 直接做**精确平移**：u_{t+Δt}(θ,·) = u_t(θ+Δt, ·)
   - 拼接：GΘ(u_t) = ShiftAppend(u_t, û(t+Δt,·))
   - 数学上：网格 θ_j = -τ + jδθ，Δt = mδθ；前 M-m+1 个切片由 input 复制，后 m 个由 PΘ 预测。
2. **FNO backbone**：对 (θ, x) 二维（1D 空间问题）或 (θ, x₁, x₂) 三维（2D 空间问题）做 spectral convolution，把 history-time 与 physical space 同时建模；μ, τ, Δt 作为 constant channels / coordinate embedding / FiLM modulation 注入。
3. **训练目标**：
   - L_data：history-space L² 误差（因 shift 段精确，主惩罚落在新切片）
   - L_rollout（可选）：K 步自回归累积误差
   - L_semi（可选）：半群一致性 G_Θ(G_Θ(u_t; s); r) ≈ G_Θ(u_t; s+r)
4. **理论分析（Section 4）**：
   - Prop 1：若历史表征 Π 把不同的真历史映到同一表示但下一切片 Φ(h)≠Φ(h')，则任何确定性预测器都有不可消除误差 p(1-p)‖Φ(h)-Φ(h')‖² —— 解释为什么 current-state / 稀疏 lag-stack 会有结构性误差。
   - Prop 2：在监督损失下，shift-append 把要学的输出坐标从 Mn 维（n 为空间自由度，M 为历史切片数）压到 n 维。
   - Lemma 1（rollout 误差递推）：a_{k+1} ≤ ε + L · max_{r=k-M..k} a_r —— 新误差只通过新预测切片进入；老切片误差最多通过 Φ 的 Lipschitz 衰减传播 M 步。
5. **基线对比**：current-state FNO、lag-stack（输入若干离散过去时刻）、unconstrained history-to-history FNO（也用全历史但直接输出全历史）、ConvLSTM、temporal U-Net、transformer-over-history。

## 关键结果与数据
五个 DPDE benchmark family：延迟反应扩散、空间流行病学、非局部神经场、延迟波动、分布式记忆（Mori-Zwanzig 类闭包）；10 个 seed；4 regime（in-distribution / held-out delay / held-out parameter / resolution transfer）。

**Aggregate rollout error（最关键指标）**：
| 模型 | Rollout | 参数量 | 内存 (MB) |
|---|---|---|---|
| HS-FNO (default) | **0.094** | 2.19×10⁵ | 22.0 |
| HS-FNO no-delay | **0.090** | 1.23×10⁵ | 20.4 |
| History2History | 0.185 | 6.09×10⁶ | 78.5 |
| Lag-stack | 0.188 | 1.05×10⁶ | 27.6 |
| Current-state | 0.241 | 6.72×10⁵ | 24.1 |
| Temporal U-Net | 0.352 | 1.61×10⁶ | 33.0 |
| ConvLSTM | 0.383 | 1.54×10⁶ | 32.5 |
| Transformer | 0.459 | 7.69×10⁴ | 19.4 |

- **HS-FNO vs H2H 的对比是关键**：两者都看到全部历史窗口；HS-FNO 仅用 H2H 1/28 的参数把 rollout 误差从 0.185 砍到 0.094 —— 证明**结构约束（shift-append）本身贡献巨大，而不是单纯"喂更多历史数据"**。
- **One-step / history-space error**：HS-FNO 0.066 / 0.098，远低于 0.143 / 0.123 (current) 和 0.113 / 0.126 (H2H)。
- **rollout 越长，HS-FNO 优势越大**：第 3 步累积误差差距比第 1 步大很多（Fig. 3）。
- **Ablation**：
  - 去掉 shift-append：rollout 从 0.094 → 0.150（架构核心组件）
  - history-space U-Net / Transformer backbone：0.162 / 0.228（FNO backbone 适配最好）
  - rollout + semiflow loss：恶化到 0.475（作者不建议）
- **Resolution transfer 是唯一明显短板**：reaction-diffusion 上 rollout ~0.394（默认）/ 0.352（最好变体）—— 在更换网格分辨率时 inductive bias 不能补偿。
- **METR-LA / PEMS-BAY 真实交通流验证**：HS-FNO 在 12-input/12-output 协议下 MAE 最低，作为 spatiotemporal sanity check（作者明确说交通流不是真正的 DPDE，**只是说明 history-as-state 思想在真实时空数据上也有效**）。

## 与我研究方向的关联
- **fea_surrogate（直接相关）**：
  1. **历史依赖材料模型**：粘弹性、塑性硬化、损伤累积、疲劳寿命、混凝土徐变 —— 全部是 history-dependent constitutive law，FEM 的 internal state variable 就是事实上的"历史"。当前主流 surrogate（FNO/DeepONet for elastic FEM）几乎都是 Markovian 的；本文提供了把内部变量"提升为状态"的清晰范式。
  2. **多尺度 / Mori-Zwanzig 闭包**：本文 distributed-memory benchmark 直接对应 LES / 多尺度 FEM 中粗粒化时的 memory term。这是 [[ADR-0024]] surrogate electronics domain scoring 中"surrogate for multiscale closure"这个细分方向的活跃前沿。
  3. **方法可直接搬用**：shift-append + FNO 的代码已开源（GitHub），可以拿到一个 toy 粘弹性梁问题上跑——是一个可执行的论文级 idea（"Memory-Aware Neural Operator Surrogates for Viscoelastic FEA"）。
- **跨方向**：
  - 与 **[[arxiv_2605.09775v1]]**（vvBO with structured measurements）方法论互补 —— 后者把"输出结构"作为可观测，前者把"输入历史"作为状态，对 surrogate 学习的两条维度都给出了原则性框架。
  - 与 **rl_world_model（[[ADR-0021]]）**：partial observability 下的 world model 本质上需要 history-aware state representation；Lemma 1 的 rollout 误差递推与 model-based RL 中 compounding error 分析同构。

## 局限
1. **Resolution transfer 不行**（作者承认）：FNO 名义上是 resolution-invariant，但 history-space 的 inductive bias 在跨分辨率时反而成了束缚。对工程 FEM 跨网格 surrogate 是硬伤。
2. **历史网格 M 选择敏感**：M 太小则记忆窗口失真，shift-append 在错的网格上不再"精确"；M 太大则 input dimension 爆炸。本文未给出自适应历史网格的方案，留作 future work。
3. **延迟显式条件化效果不稳定**：no-delay 变体反而比 default 略好（0.090 vs 0.094）—— 表明把 τ 注入网络的最佳方式还没找到。
4. **状态依赖延迟、空间变化延迟、分布式记忆核**：会破坏 ShiftAppend 的"精确性"，需要插值/quadrature 近似，inductive bias 优势打折扣。
5. **rollout-semiflow 损失反而恶化性能**：理论上半群一致性是合理正则项，但实际训练里 0.475 vs 0.094 是巨大恶化 —— 优化困难，作者明确不建议使用。
6. **DPDE 基准全是合成数据**；唯一"真实"数据是 METR-LA/PEMS-BAY 但它们不是真正的 DPDE。**真实工程 history-dependent FEM 数据缺位**，这是我可以填补的空白。
7. **作者只有一人（grad student）**：工作扎实但缺乏导师署名 —— 引用尚不充分时（preprint v2，刚 2 周前发布）需要观察社区反应；可关注是否进 NeurIPS / ICML / JCP。

## 是否值得跟进
**值得跟进，且 priority 应该上调到 High。**

- existing_summary 把 priority 判为 Medium，我认为偏低。原因：(1) 直接给出可执行的 surrogate-for-history-dependent-FEM 论文 idea；(2) 代码开源、benchmark 详细、实验严谨（10 seed + 4 regime + 8 baseline），方法可信度高；(3) 与本周 paper 2/4（vvBO with structured measurements）形成"input history × output structure"的双轴方法论组合，对 surrogate 模型设计是两个独立的轴向收益。
- **跟进动作**：
  1. clone 仓库，在粘弹性/塑性 toy FEM 例子上跑通 baseline，评估是否值得正式立项。
  2. 把"history-aware surrogate"作为 [[ADR-0024]] 评分体系的一个新维度（"是否考虑 internal state variable"），下次 scorer prompt 演进（v4）时加入。
  3. 横向追读：Feng et al. 2024（[19] FNO for delay chaotic）、Zhu et al. JCP 2023（[20] statistics-informed NN for non-Markovian dynamics）、O'Leary-Roseberry et al. 2024（[37] DINO）作为相邻锚点论文。

## 评分体系反馈
- 本文被 scorer 打成 Medium / fea_surrogate，**direction 正确但 priority 偏低**。可能原因：scorer prompt 对"Markovian assumption 突破"这类**软范式贡献**的权重不够，而对"直接对应 FEA application"的字面匹配更敏感。建议下次 prompt v4 加一条"方法论新颖性（即使应用领域不直接对应）"的加分项。
