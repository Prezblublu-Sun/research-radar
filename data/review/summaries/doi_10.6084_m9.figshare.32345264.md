# Generative AI-guided in silico closed-loop optimisation of deposition morphology for 3D bioprinting applications

- **id**: `doi:10.6084/m9.figshare.32345264` · 方向 ai_bioprinting · 优先级 High · checked
- **失败原因**: figshare DOI（数据/补充材料仓库，非期刊文章），Unpaywall 404

## 复核

- **方向**：正确。β-CVAE + CNN-BO 闭环优化打印形态，明确是 ai_bioprinting 核心
  （生成模型 + 主动优化 + 工艺-形态映射）。
- **优先级 High**：合理。β-CVAE 的"可解释潜空间 + 条件生成"对生物墨水工艺
  迭代是高价值方向；CNN-BO 闭环 + 迁移学习架构完整。
- **摘要质量**：尚可。覆盖动机/方法/结果但偏抽象，缺关键数据（潜空间维度、
  打印参数空间大小、BO 迭代次数、迁移学习样本量）——这是 figshare 数据集
  类条目的典型问题。
- **跟进**：值得。但 figshare DOI 通常是补充材料/数据集；建议搜原始论文标题
  找正式期刊版本（可能在 Biofabrication / Additive Manufacturing 上）。

## 评分系统反馈

priority=High 在缺正文的情况下，**应该警惕 figshare 类 DOI 的"主条目 vs 补充
材料"歧义**。当前 routing 把数据集 DOI 也按 High 处理是合理的（标题信息足够），
但 PDF 获取必然失败。值得在 fetch 阶段加一个 `is_figshare` 标记，提示下游"原始
论文可能在别处"。
