# Don't Get Your Kroneckers in a Twist: Gaussian Processes on High-Dimensional Incomplete Grids (CUTS-GPR)

- arXiv: 2605.08036v1（2026-05-08, cs.LG）
- 作者：Mads Greisen Højlund, August Smart Lykke-Møller, Ove Christiansen（Aarhus U. 化学系）, Henry Moss（Lancaster U.）
- 方向归类：fea_surrogate（priority=Medium）
- 应用：计算化学（高维势能面 PES）

## 研究问题
**精确 GPR 在高维 (D > 10) 上不可行**：标准 O(N³) cost；用 separable kernel + complete Cartesian grid 能降到 O(nDN) 但 N 随 D 指数爆炸；inducing-point 方法 (FITC/SVGP) 是近似的。**高维 + exact + scalable 同时具备**仍是开放问题。

## 方法
**CUTS-GPR**（Cuts-based GPR）：
1. **Incomplete cut-based grid**：参考点 + 1D 切片（每维独立）+ 2D 切片（每对维度）+ ... 直到 α 阶 cut；训练数据量 N = O(D^α)，**不是指数级**。
2. **Additive kernel**（最大交互阶 ω）：k = σ_0² + σ_1² Σ k^(m) + σ_2² Σ k^(m)k^(m') + ...
3. **核 MVP（matrix-vector product）的精确 O(n·α·N) 实现**：通过 careful 利用 Kronecker structure + 增量 cut subgrid 的结构性；**无近似**。
4. 用 iterative CG + 预条件子做 linear solve + log-det + trace —— 所有 GPR 必备运算都基于 MVP。

## 关键结果
- **Billions of data points, thousands of dimensions** MVP benchmark 可跑
- **N = 447,265 + D = 24 的全 GPR（含超参优化）数小时完成**
- 应用到**计算化学势能面建模**——传统 GPR 卡死的问题。

## 与我研究方向的关联
- **fea_surrogate（间接相关）**：本文核心应用是 PES，但**方法本身对工程 surrogate 中"高维设计空间 GPR" 普遍适用**：
  - FEM 设计优化中 design variable 数 10-50+ 是常态；CUTS-GPR 可作为 BO 的代理模型
  - 与 [[arxiv_2605.09775v1]] vvBO（vector-valued BO）互补：vvBO 处理 output structure，CUTS-GPR 处理 input dimension scalability
- **方法可借鉴点**：
  - "Sample design = cuts not random LHS" 思想：先沿 1D 切片采样，再 2D 切片，再 3D... 是非常有效的高维 sparse 采样模式。可加入 ADR-0024 评分体系作为采样策略评分维度。
  - "Additive kernel + structure-aware MVP" 是高维 GP 的通用配方。

## 局限
1. **要求 incomplete grid 结构**：实验数据是随机 / Latin Hypercube 不适用；只有"主动设计实验"场景才能享受此结构。
2. **Cut order α 与 max interaction order ω 是必须匹配的超参**；选错就退化为普通 GP。
3. **PES 应用偏窄**：化学势能面是 separable + smooth 的天然样本；其他工程函数（含 shock / discontinuity）未验证。
4. **没有与 SKIP / KISS-GP / variational SVGP 在 N=10⁵+ 上的直接对照表**；scaling 数字漂亮但缺横向 benchmark。
5. **代码 / 数据**：未给链接。

## 是否值得跟进
**Priority Medium 略偏高**。

- 方法学扎实但应用领域离我研究主线远。
- **跟进动作**：仅 reference 收录。如未来做高维 FEM design BO（design vars > 20），CUTS-GPR 是 surrogate 候选。
- 横向追读：SKIP [10]、KISS-GP [9]（structured kernel interpolation 经典工作）。

## 评分体系反馈
- Direction `fea_surrogate` 不准确，**应归到 generic_ml_surrogate 或 high_dim_BO**。当前 scorer 倾向把所有"含 surrogate 关键词"的工作归入 fea_surrogate，是 false positive。
- existing_summary 准确（incomplete grid、additive kernel、kernel MVP、billions of points、势能面），无错。
