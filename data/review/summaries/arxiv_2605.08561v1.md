# CONTRA: Conformal Prediction Region via Normalizing Flow Transformation

- arXiv: 2605.08561v1（2026-05-08, stat.ML）—— 实际是 **ICLR 2025** 已发表论文的重新发布
- 作者：Zhenhan Fang, Aixin Tan（U. Iowa Statistics）, Jian Huang（HK PolyU 应数）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 不准确，应为 generic_ML / UQ**

## 研究问题
**Conformal Prediction（CP）在多维输出上失效**：经典 CP 用 1D nonconformity score + quantile 给出 box / ellipsoid 形预测区域；对多模态 / 重尾 / 各向不对称的条件分布，box / ellipsoid 会**膨胀到包含低密度区**。已有 multi-dim CP 方法（PCP, ST-DQR）用多个球并集，得到**不连通、不规则边界**，可读性差。

## 方法
**CONTRA**：用 conditional normalizing flow（CNF）把 output Y 映射到 latent space（标准多元高斯），定义 **nonconformity score = 距离 latent space 中心的距离**；用 split-conformal 在 latent 上调整 high-density region，再 push back 回 output space。**输出区域是单一连通 high-density region 的 bijection 像**，自然贴合条件分布，无需多球并集。

**ResCONTRA**（CONTRA 变体）：先用任意 predictive model 学 E[Y|X]，对**残差**训练简单 NF；适合 E[Y|X] 复杂（XGBoost 更合适）但残差结构简单的场景。引入 symmetric base distribution + three-step calibration procedure 保 exchangeability + coverage guarantee。

## 关键结果
- **NYC Taxi drop-off prediction** 示意图：给定 pickup 点的多模态 drop-off 分布，CONTRA 给出贴合 KDE 形状的连通区域；vs Ellipses / Rectangles / NF+PCP / DM+PCP 等 baselines
- 在多个标准 dataset 上保证目标 coverage probability（如 90%）+ 区域 area 显著小于 shape-restricted 方法
- 边界更光滑、可解释性 vs PCP/ST-DQR 的多球区域

## 与我研究方向的关联
- **fea_surrogate（弱相关；direction misclassified）**：本文不针对 PDE / FEM，**是 generic ML UQ 方法**。
- **可借鉴价值**：
  - 如果我未来 FEM surrogate 要给出**多维输出**（如同时预测应力、温度、变形）的 conformal prediction region，CONTRA 可直接用。
  - **conformal + normalizing flow** 是 calibrated UQ 的好组合，与本周其他 UQ 工作（functional-prior B-PINN, B-PINN theory, flow-based VI）共享 NF 工具箱但是不同 paradigm（exchangeability-based 而非 Bayesian）。

## 局限
1. **不是为 PDE/FEM 设计**：scorer 把它放进 fea_surrogate 是错误的。
2. **训练 CNF 本身有要求**：output dim 不能太高（>10 维 NF 难训）；FEM 全场输出（>10⁵ 维）直接用不行。
3. **ICLR 2025 paper**：相对成熟，已发表 1 年；属于"补漏"扫到的论文，不是新出 SOTA。

## 是否值得跟进
**Priority Medium 偏高，Low 更合理**。

- 对我研究主线**无直接价值**。Reference 级，如未来做"多维 surrogate 输出的 conformal UQ" 才用得上。
- **跟进动作**：reference 收录。

## 评分体系反馈
- **Direction `fea_surrogate` 错**：本文是 generic ML UQ，与 PDE/FEM 无关；建议 scorer prompt v4 加 "general_ml / generic_uq" 子方向。
- existing_summary 准确（NF + conformal + 多维输出 + 比 box/ellipsoid 精确）。
- 本周已多次出现 direction 误分类（[[arxiv_2605.07792v1]] 核物理插值、[[arxiv_2605.07987v1]] cardiac imaging、本文 generic UQ）。建议下次 scorer prompt v4 强化 direction discrimination。
