# Robust Conditional Conformal Prediction via Branched Normalizing Flow (BNF)

- arXiv: 2605.01868v1（2026-05-03, cs.LG）
- 作者：Rui Xu, Xingyuan Chen, Sihong Xie, Hui Xiong（HKUST Guangzhou）+ 广州医科大学第二附属医院
- 方向归类：fea_surrogate（priority=Medium）—— **direction 误，应为 generic_ml / conformal_prediction**

## 研究问题
Conformal Prediction (CP) 在分布偏移（P_XY ≠ Q_XY）下，现有方法只对齐**边际** conformal score 分布（保证 marginal coverage），不控制单个测试输入的**条件** coverage error。当条件分布失配时 CP 不可靠。

## 方法
1. **理论贡献**：定义 conditional coverage gap (CCG) 和 integrated coverage gap (ICG)，证明 **Wasserstein 距离 W(P_XY, Q_XY) 是 ICG 的上界** —— 揭示分布偏移如何从数据空间传到分数空间，并说明**可逆映射（invertible transport）**能改善条件 coverage。
2. **BNF 架构**：双分支 normalizing flow，f_θ(x,y) = (f_θX(x), f_θY(y))，**x 与 y 的变换不显式耦合**：
   - Step 1：将测试输入 X_{n+1} 用 f_θX 归一化到校准分布 → 得到校准分布上的 C_C(X̄_{n+1})
   - Step 2：用 f_θY^{-1} 把预测集反变换回测试分布 → C_BNF(X_{n+1})，保留条件 coverage
   - 训练目标：min_θ W(P_XY, f_θ#Q_XY)

## 关键结果
- **9 个数据集 + 多种 confidence level**：BNF 一致改善 conditional coverage robustness

## 与我研究方向的关联
**fea_surrogate (弱相关)**：本文是 generic ML 方法（CP under distribution shift），与 PDE/FEM 无直接接口。与本周 [[arxiv_2605.08561v1]] CONTRA、[[arxiv_2605.03233v1]] conformal percentile interval 同 conformal prediction 主题。**如未来 FEA surrogate 在 OOD 场景下需要 calibrated UQ**（不同几何 / 不同载荷），BNF 思路可借鉴。

## 局限
- 应用是 generic regression，无 PDE / FEM benchmark
- NF 在高维 output 下训练困难
- 第二附属医院的 affiliation 暗示可能有医学应用扩展，但本文未展示

## 评分体系反馈
- Direction 应为 `ml_uq / conformal`，本周 direction misclassification 累积信号充分。
- existing_summary 准确。
