# Martingale Neural Operators: Learning Stochastic Marginals via Doob-Meyer Factorization (MNO)

- **id**: `arxiv:2605.15806v1` · 方向 fea_surrogate · 优先级 High · **read**（精读引论 + Setup）
- **来源**: arXiv 2605.15806 (cs.LG), 2026-05-15（**W20**），UW Applied Math（**单作者**）

## 与 W20 姐妹论文的关系

本周 W20 出现两篇 **SPDE + neural operator + UQ** 论文：
- **SON**（arxiv:2605.17107，FSU+ORNL，High）：DeepONet + Stochastic NN +
  Hamiltonian-SMP 训练。Brownian diffusion 嵌入。
- **MNO（本篇）**（arxiv:2605.15806，UW，High）：FNO 双头 + Doob-Meyer 分解 +
  low-rank covariance factor。Wasserstein 距离降 **120×**。

两条独立路线，但目标几乎完全相同——给 deterministic neural operator 加 UQ。
MNO 的方法**更优雅**（理论驱动 + 单次 forward 给 closed-form mean+variance），
SON 的方法**更通用**（Brownian diffusion 不挑分布族）。一周两篇说明
"operator learning + UQ"是当前真正热点。

## 研究问题

Neural operator (FNO, DeepONet) 是 deterministic surrogate，在 SPDE 上 L2 训练
必然收敛到 conditional mean E[u_T|u_0]，**抹掉 aleatoric residual**——空间方差、
相关性、采样变异性。这些是 UQ 的核心。
现有 UQ 方法（Monte Carlo rollout、Wiener-chaos 展开、conditional diffusion）
都付出代价（慢 / 高维难 / 迭代采样）。**核心需求**：terminal marginal moments 或
risk envelope，**operator-speed 同时给出**。

## 方法

**MNO** 把 Doob-Meyer 定理（任何半鞅 = predictable drift + zero-mean martingale）
turned 成 architectural prior：
- **Drift head**（FNO）：输出 conditional mean。
- **Covariance head**（FNO）：输出 rank-r、channel-aware residual factor B_φ。
- **PSD 保证**：Γ = B^T B by construction 半正定，对角即 per-channel variance。
- Gaussian residual instantiation：本论文具体实现是高斯尾部，但框架兼容更广。

在非半鞅情形（如 rough volatility），同一 split 是 mean/covariance principled
factorization。

## 关键结果

- **1D SPDE**（φ⁴ field theory）：W2 距离降低 **120×**
- **Stochastic Burgers**：W2 降低 **68×**
- **Rough volatility**（H=0.1）：terminal marginal accuracy 提升 2.6×
- **推理速度**：~3× faster than conditional diffusion baseline 在 matched wall-clock
  training budget 下
- **2D**：turbulent flow 和 zero-shot resolution transfer 与 FNO comparable；
  quasi-deterministic 系统（Gray-Scott）是失败模式（噪声太小，drift 主导）

## 与我研究方向的关联

**对 fea_surrogate：核心相关，是 ADR-0024 中 novelty=high 的典型样本。**

1. **临床部署级 UQ 价值**：患者特异 FEA 中，材料属性（CT 灰度反演）+ 几何边界
   （分割）+ 载荷估计都有不确定性。MNO 这种"单次 forward 给 mean+variance"
   特性，比 Monte Carlo rollout 在临床实时反馈中可行得多。
2. **Doob-Meyer 分解作为 architectural prior**：这种"用数学定理指导网络结构"
   思路，对生物力学 inverse problem（如骨密度反演）也可借鉴——任何 noisy 数据
   驱动的 PDE 求解都可考虑显式分解 drift + residual。
3. **与本周 SON 形成方法学对照**：MNO 优雅 + 假设强（高斯残差）；SON 通用 +
   工程复杂。值得对比这两条路线在生物力学问题上的实际表现。
4. **与 W21 IKNO/Therm-FM/PACE-FNO 拼图**：神经算子的 4 个方向——表达力
   (IKNO)、对称性 (PACE)、跨问题迁移 (Therm-FM)、UQ (MNO/SON)。**完整工具箱
   越来越成形**。

**对 hip_implant**：间接。患者特异 FEA UQ 的临床部署是核心使用场景。

## 局限

- 高斯残差假设强（生物力学常见多模态、重尾噪声不适用）。
- Gray-Scott 失败模式表明在 deterministic-dominated 系统上不优于 FNO。
- 2D 任务中 CNN baseline 偶尔更强 —— FNO + low-rank covariance 在某些场景下
  不是必胜组合。
- 单作者（UW）preprint，未同行评审。
- 实验主要是数学物理 benchmark，工程 PDE（弹性）未测。

## 是否值得跟进

**强烈建议跟进（High）**。建议：
1. **优先级与 SON 并列**作为"算子学习 + UQ"方向 W20 双标杆。
2. 关注作者 Kai Hidajat 后续工作（UW 应用数学），可能有 v2 扩展更广分布族。
3. 在 fea_surrogate 知识地图加新 axis："UQ for operator learning"，归 MNO + SON
   + 早期 UQDeepONet / Bayesian DeepONet 一起。
4. 长期 idea：把 MNO 的 drift+covariance split 嵌入 Therm-FM 的 foundation
   model 框架——能否得到"跨问题 UQ-aware foundation model"？是个明显的下一篇
   论文。

## 评分系统反馈

priority=High 正确。novelty=high（Doob-Meyer 作为 architectural prior 是真新
颖），pathway=adjacent（数学物理 SPDE → 生物力学 SPDE 需类比迁移）。
**完美符合 ADR-0024 草案中"应保留 High"的判定**——证明 routing + scorer
对方法学创新度的识别在这一类是 OK 的，问题集中在 incremental 工作上。
