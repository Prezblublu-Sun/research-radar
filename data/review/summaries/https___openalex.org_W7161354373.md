# 复核：W7161354373 — Dual-Correction PINN for Hemodynamic Reconstruction

- OpenAlex W7161354373，pdf_found=false
- 方向归类：fea_surrogate（priority=**Medium**）
- 注意：与 [[arxiv_2605.12544v1]] **同一篇论文**

## 关键判断：与 arxiv:2605.12544v1 的关系
完全相同论文。详细总结见 [[arxiv_2605.12544v1]]。

## ⚠ 评分不一致（scorer bug 信号）
**本条 OpenAlex 入口 priority=Medium，但 arXiv 入口 [[arxiv_2605.12544v1]] priority=High** —— 同一篇论文被打了不同分。

可能原因：
1. scorer 处理 arXiv vs OpenAlex 元数据时拿到的字段不同（如摘要长度、author affiliation 显式程度、关键词）
2. scorer 运行时间不同（如果有时间戳依赖的 prior knowledge）
3. 同一条论文不同入口的"权重 by direction context" 计算结果有差异

**重要的 evaluation 反馈**：这是 scorer 体系自一致性的明确 bug 证据。建议在 ADR-0024 / scorer prompt v4 中加一条：**"如果同一篇论文（标题相同）出现多条记录，必须给同一 priority"**，或在 weekly 流程中做合并时强制取最高 priority。

## 摘要 / 处置
existing_summary 描述准确（与 arXiv 入口的 summary 在内容上一致，但措辞略有差异 —— 显示是 scorer 重新生成而非直接复用）。priority 取 **High**（与 arXiv 版本一致）应该作为权威值；本条 Medium 是 scorer 的下变体，应忽略。

checked。
