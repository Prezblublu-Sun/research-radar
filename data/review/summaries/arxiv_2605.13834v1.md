# Topology-Preserving Neural Operator Learning via Hodge Decomposition

- **id**: `arxiv:2605.13834v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.13834, 2026-05-13（**W20**）

## 核心思路

几何 mesh 上 PDE 求解的两个老问题：谱干扰 + 拓扑自由度（如非平凡 cohomology）
不可学习。用 Hodge 正交性 + 算子分裂，提出 **混合 Euler-Lagrange 架构 + Hodge
谱对偶归纳偏置**。

## 与 fea_surrogate 关联

- Hodge 分解是微分几何/计算电磁的经典工具，应用到神经算子是数学上正经的扩展。
- 对生物力学：骨/植入物界面可能有非平凡几何拓扑（孔洞、连通性），保拓扑性
  对结构正确性有帮助。
- 与 W21 IKNO、本周 MMGUNet 同类"几何感知神经算子"工具。

## 评分

priority=Medium 合理。novelty=high（Hodge 分解是数学新颖嵌入），pathway=adjacent。

## 跟进

低-中。理论性较强，工程落地路径不直接。
