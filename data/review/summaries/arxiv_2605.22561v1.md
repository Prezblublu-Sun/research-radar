# Regret-Based (ε,δ)-optimal Stopping Criteria for Bayesian Optimization

- **id**: `arxiv:2605.22561v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读引论 + 核心定理）
- **来源**: arXiv 2605.22561（preprint May 2026），NUS + LLNL + Manchester（三个 equal contrib）

## 研究问题

Bayesian optimization 在工程设计 / 模拟优化 / ML 超参 / 材料发现等贵评估场景广泛
使用，但**何时停止迭代**几乎全靠"用完预算"这种 ad-hoc 规则——既浪费又不保证
解质量。现有 stopping criteria 要么是启发式（MC simple regret、confidence-gap、
EI 阈值），要么有理论但假设强（KL divergence、Bayesian optimal stopping）或计算
开销大。

## 方法

- 在 GP-UCB 上推导**更紧的瞬时（instantaneous）regret upper bound** at finite time T。
- 基于该 bound 构造 (ε,δ)-optimal stopping criterion：终止时以概率 ≥ 1-δ 保证
  ε-最优解。
- 计算开销：与原 GP-UCB 在同量级，相比 PRB / MSP 等 MC-based 方法显著低。

## 关键结果

合成 benchmark + 真实任务上，相比 PRB（Wilson 2024）、MSP（He 2025）等 SOTA：
- 同等或更好解质量下显著减少迭代数。
- stopping behavior 与理论 bound 对齐，可解释。

## 与我研究方向的关联

**对 fea_surrogate：相关但偏专门。**
- BO 在 FEA-in-the-loop 工程优化中是常用工具（如植入物几何参数 → FEA 评估 →
  目标函数）。停止准则对实际节省 FEA 调用次数有直接意义。
- 但本文只覆盖 GP-UCB acquisition function，不覆盖 EI / KG 等其他常用 acquisition。
  实际工程 BO 用 EI 更多，覆盖度有限。

**对 ai_bioprinting**：高度相关。每次打印实验昂贵，停止准则的实际节省可观。

## 局限

- 假设条件：sublinear cumulative regret，要求核函数 RKHS 范数已知。在工程实践中
  RKHS 范数难估计，可能要 conservative 估计而损失 tightness。
- 仅 GP-UCB，未推广到其他 acquisition function。
- 真实任务规模有限（标准 BO benchmark 维度通常 < 20）。

## 是否值得跟进

**中等优先**。建议：
1. 若自己工作中要做 FEA-driven BO，可直接拿来用——比 fixed budget 更负责任。
2. 不必精读所有定理证明。
3. 关注是否有人后续把这套 stopping 推广到 EI / KG / multi-fidelity。
