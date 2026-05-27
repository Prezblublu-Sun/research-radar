# AOT-POT: Adaptive Operator Transformation for Large-Scale PDE Pre-training

- **id**: `arxiv:2605.15793v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读摘要）
- **来源**: arXiv 2605.15793, 2026-05-15（**W20**）

## 核心思路

多 PDE 预训练（PDE foundation model 路线）的核心难题是**算子结构多样性**——
不同 PDE 的算子形式不一致，难以共享 backbone。**AOT-POT** 通过多流表示 +
Sinkhorn 投影把不同 PDE 算子统一到一个 normalized form。

## 关键结果

- 12 PDE benchmark 上平均相对 L2 误差降低 **40.9%**。
- Fine-tuning 后 **OOD 误差降低 89%**。

## 与 fea_surrogate 关联

**核心方法学相关**：是 W21 Therm-FM "PDE foundation model + 跨问题迁移"路线的
扩展工作。Therm-FM 借用了 DPOT/Poseidon 这类 PDE foundation model；AOT-POT
是直接解决"foundation model 的算子异构性"问题。

可能 priority 偏低——若把它视为 Therm-FM 路线的补充技术，**应该接近 High**。
按 ADR-0024 草案：novelty=high（algorithmic foundation work）, pathway=adjacent。

## 跟进

**中-高优先**。Therm-FM 的关注者应一起跟踪此文。如有代码开源，可考虑在生物
力学 PDE 上做 transfer 实验。

## 与 W20+W21 trend

W20 已出现 SON + MNO（算子 + UQ）+ AOT-POT（foundation model）+ PI-SWNO（解耦）
4 篇 fea_surrogate Medium。**本周神经算子方法学密度比 W21 更高**。
