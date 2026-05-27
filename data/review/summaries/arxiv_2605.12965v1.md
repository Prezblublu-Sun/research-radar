# U-HNO: U-shaped Hybrid Neural Operator with Sparse-Point Adaptive Routing for Non-stationary PDE Dynamics

- **id**: `arxiv:2605.12965v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要 + 引论）
- **来源**: arXiv 2605.12965, 2026-05-13（**W20**）

## 核心思路

现有 neural operator 难以同时处理 PDE 解中的**全局平滑**（Fourier 分支擅长）和
**局部尖锐特征**（Gaussian 分支擅长）。**U-HNO** = U-shape Hybrid Neural Operator
+ **Sparse-Point Adaptive Routing (SPAR)**，在两支间动态选择。

## 关键结果

- PDEBench 上 8 个 PDE 问题 SOTA roll-out 预测，**尤其擅长局部尖锐特征**。
- 1D/2D/3D 都验证。

## 与 fea_surrogate 关联

- 神经算子方向的又一架构：**全局-局部 hybrid + 路由**。
- 与本周 IKNO（无穷阶 kernel）、MNO（UQ 算子）、Therm-FM（foundation model）、
  PACE-FNO（对称性）共同构成 fea_surrogate 神经算子方法学密集创新——**两周
  累计 6-7 篇神经算子方法学论文**。
- 对生物力学：骨/植入物界面应力集中是典型"局部尖锐 + 全局平滑"问题，hybrid
  路线有借鉴。

## 评分

priority=Medium 合理。novelty=medium（hybrid 路线已有人做，SPAR 是有意义增量），
pathway=adjacent。

## 跟进

低-中。把 hybrid global-local 思路记入神经算子工具箱。
