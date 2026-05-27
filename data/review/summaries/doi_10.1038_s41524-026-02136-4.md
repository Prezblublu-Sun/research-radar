# Training-free active learning framework in materials science with large language models

- **id**: `doi:10.1038/s41524-026-02136-4` · 方向 fea_surrogate · 优先级 Medium · **read**（精读核心）
- **来源**: npj Computational Materials 2026（Article in Press），Toronto + Cohere + Vector Institute

## 研究问题

材料发现的 active learning（AL）传统上依赖 task-specific 特征工程和 GP/RF
等 surrogate，**冷启动差**、跨任务复用难、需要领域 ML 工程能力。能否用 LLM 直接
当 AL 选择器，绕过 surrogate 训练？

## 方法

**LLM-AL** iterative few-shot 框架：
- 每轮把已有 (设计-性能) 对 + 候选集以**文本**喂给 LLM，让它直接给出下一批实验建议。
- 两种 prompting 策略：
  - **简洁数值**：适合组成/结构特征明确的数据集。
  - **扩展描述**：适合实验/工艺特征丰富的数据集（提供更多上下文）。
- 整个流程**无任何模型训练**，只调用 LLM API。

## 关键结果

4 个材料科学数据集对比传统 ML（GP / RF / etc）：
- **达到 top candidate 所需实验数减少 > 70%**。
- 始终优于传统 ML baselines。
- 行为分析：LLM-AL 做**更广泛的探索性搜索**但更快收敛。
- 稳定性：在 LLM 非确定性下，跨多次运行的方差与传统 ML 类似。

## 与我研究方向的关联

**对 fea_surrogate：方法学有借鉴，应用域偏远。**

1. 与上面 **LABO**（arxiv:2605.22054）同一主题——LLM 接入 BO/AL。**LABO 更
   principled**（KOH 多保真 GP + 理论 regret bound），**本文更工程化**（直接 LLM
   做选择，无 GP 后端）。两者互补。
2. 对 fea_surrogate 的迁移：材料设计 → FEA 评估 → 优化的工作流可考虑用 LLM-AL
   替代传统 GP-BO。但 LLM 对"FEA 评估结果（数值场）"的理解能力存疑——比化学
   分子简单的组成-性能映射难得多。
3. **重要前提**：LLM-AL 假设可以把候选设计**写成文本**。FEA 的设计空间（几何
   参数 / 材料参数）容易文本化，但"FEA 输出场"反馈回 LLM 时需要 reduction
   （如最大应力、特征频率），损失信息。

**对 ai_bioprinting**：高度相关。生物墨水成分组合优化与材料数据集同构，可直接试。

## 局限

- 4 个数据集偏小（实验科学常态），泛化结论需谨慎。
- 没讨论 LLM API 成本 vs 节省实验成本的实际权衡。
- LLM 选择"偏探索"的真实机制黑盒——可能源于 LLM 知识先验或纯随机性。
- 与 LABO 相比缺理论保证；与传统 GP-BO 相比丢失了不确定性量化。

## 是否值得跟进

**中等优先**。建议：
1. 与 LABO 配对记入"LLM-augmented BO/AL"工具箱。LABO 用于"要可证明 regret bound"
   的场景，LLM-AL 用于"快速、零训练原型验证"的场景。
2. 关注是否有人在工程设计（FEA-in-loop）任务上做 LLM-AL vs GP-BO 对比。
3. ai_bioprinting 方向可优先试这套方法做生物墨水配方筛选。

## 评分系统反馈

priority=Medium 合理；本周已有 LABO 这类 LLM+BO 主题论文，**评分系统正确地
没把所有 LLM-BO 都判 High**——区分能力良好。
