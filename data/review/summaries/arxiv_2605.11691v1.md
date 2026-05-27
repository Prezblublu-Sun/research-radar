# Compositional Neural Operators for Multi-Dimensional Fluid Dynamics

- **id**: `arxiv:2605.11691v1` · 方向 fea_surrogate · 优先级 High · **read**（摘要）
- **来源**: arXiv 2605.11691, 2026-05-12（**W20**）

## 核心思路

把复杂 PDE 分解为**预训练的基础算子模块** + aggregator 学习非线性交互。模块化
方法学。

## 关键结果

在对流扩散、Burgers、不可压 Navier-Stokes 上验证模块化适应性 + 可解释性。

## 与 fea_surrogate 关联

- "Compositional + pretrained modules" 是 PDE foundation model 路线的变体——
  与 W21 Therm-FM、本周 AOT-POT 同 cluster。
- 应用是流体动力学，对生物力学 elastodynamics 有类比迁移路径。
- 模块化可解释性对临床部署是优点。

## 评分

priority=High 合理。novelty=high（compositional 是新颖架构）、pathway=adjacent。

## 跟进

中-高。把"算子组合"思路记入 fea_surrogate foundation model 子方向。
