# A Mutual Information Lower Bound for Multimodal Regression Active Learning

- **id**: `arxiv:2605.14917v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.14917, 2026-05-14（**W20**）

## 核心思路

现有 AL 方法假设 unimodal posterior，不能处理多模态回归的 epistemic uncertainty。
提出双索引框架 + 互信息下界 acquisition function + 混合密度网络集成。

## 与 fea_surrogate 关联

- 方法学边缘。AL 在 FEA-in-loop 工程优化中常用，但本文专门解决"多模态目标"
  问题——生物力学 FEA 输出通常 unimodal（应力场是确定的 PDE 解），多模态场景
  少见。
- 与 W21 LABO / LGBO / LLM-AL 同属"BO/AL 方法改进"cluster。

## 评分

priority=Medium 合理；novelty=medium（multimodal AL 是 niche 但有数学贡献），
pathway=none（应用域与 user 不重合）。

## 跟进

低。除非 user 有多模态回归需求。
