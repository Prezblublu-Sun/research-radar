# Neural Operators as Efficient Function Interpolators

- arXiv: 2605.07792v1（2026-05-08, cs.LG）+ CERN-TH-2026-096 + CCTP-2026-8
- 作者：Vasilis Niarchos, Angelos Sirbu（U. Crete CCTP/ITCP）, Sokratis Trifinopoulos（CERN + UZH）
- 方向归类：fea_surrogate（priority=Medium）
- 投：AI4Physics @ ICML 2026 Workshop

## 研究问题
Neural Operators（FNO/DeepONet）原本设计学**无穷维 → 无穷维**的函数空间映射，但能否反过来用作**有限维函数 f: R^d_in → R^d_out 的高效插值器**（替代 MLP / KAN）？此前 (Huang et al. 2025a) 改架构搞这个；本文不改架构，**只 reinterpret 训练/推理流程**：
- 引入辅助 base space B（dim d_B），构造 operator F[x](s) = f(x(s))
- 学 F 等价于学 f；输入函数 x(s) 通过随机 partition 训练数据构造
- d_B=0 时退化为 tensorized MLP

## 方法
- d_B = 0/1/2 三种实现（0D-NO 退化成 tensorized MLP；2D-NO 用于 (Z,N) 核电荷-质子图）
- 用 **TFNO（Tensorized FNO with Tucker/CP decomposition）**，参数高效
- Training: 随机 shuffle 数据点形成"input function on base space"

## 关键结果
- **解析函数 benchmark**（partial-wave expansions、Heaviside、分段 Gaussian、高维函数）：(T)FNO 在参数效率和训练时间上 match 或超越 MLP / KAN
- **核质量预测**（real-world application）：2D TFNO with ~150k params 学 WS4 nuclear mass model 的残差场；**OOF（out-of-fold）pooled 5-fold ensemble: RMSE = 198.2 keV** —— 与目前 leakage-free single-task 方法持平，但参数少、训练快。

## 与我研究方向的关联
- **fea_surrogate（弱相关）**：
  - 论文的 framing 是"NO 作为通用函数插值器"，与我研究主线"FEM 代理"基本不直接对应。
  - **方法 takeaway 偏 niche**：拿 TFNO 当 tensorized MLP 用是 incremental observation；nuclear physics 应用对我无直接价值。
  - **轻度可借鉴**：base-space reframing 的"用随机 partition 把 vector 提升为 function" trick 在 surrogate 数据增强中可能有用；但需要案例支撑才能判断。
- 与本周其他强 surrogate 工作（CATO/SpectraNet/EquiNO）相比，本文偏理论性/方法学，与工程应用 gap 较大。

## 局限
1. **应用单一**：除了 nuclear physics 都是 toy analytic functions；没工程 PDE 案例。
2. **vs 改架构方法（Huang et al. 2025a）的对照**：作者明示 differ from 该工作，但没直接 head-to-head 数字。
3. **Workshop preprint**：preliminary work，未经 main venue 同行评审；理论严谨度有限。
4. **核物理应用对评分体系无 transferability**：是 niche 领域 benchmark，不能 generalize 到工程 surrogate 评估。
5. **Base-space 选择是经验性的**：noisy input 似乎"helps global structure"，但缺乏机制解释。

## 是否值得跟进
**Priority Medium 略偏高，Low-Medium 更合理**。

- existing_summary 准确（"NO 重定向为有限维插值"、TFNO、参数少、解析函数 + 核质量），无错误。
- 对我研究方向**无直接复现价值**。Reference 级收录即可。

## 评分体系反馈
- Direction `fea_surrogate` **borderline**：本文严格说更接近 ML 方法学 / 核物理应用，不是经典工程 FEM 代理。建议下次 scorer prompt 区分"工程 PDE surrogate" vs "通用函数插值"两个子方向。
- existing_summary 准确简洁，无修正项。
