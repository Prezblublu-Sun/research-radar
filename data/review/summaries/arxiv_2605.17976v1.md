# Unleashing LLMs in Bayesian Optimization: Preference-Guided Framework for Scientific Discovery (LGBO)

- **id**: `arxiv:2605.17976v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读引论 + 核心）
- **来源**: arXiv 2605.17976（**ICLR 2026**），上海 AI Lab + HIT + SJTU（与 LABO 同 Lab 重合作者）

## 与本周姐妹论文的关系（重要）

本周已经处理两篇 LLM+BO 论文，本篇是第三篇：
- **LABO**（arxiv:2605.22054, ICML 2026）：dual-fidelity GP（KOH），LLM 作为 LLM-fidelity 信号源，
  uncertainty gating 决定何时用真实实验。
- **LLM-AL**（doi:10.1038/s41524-026-02136-4, npj CompMat）：**training-free**，LLM 直接做
  AL 选择器，无 surrogate。
- **LGBO（本篇）**：region-lifted **preference** mechanism，每轮把 LLM 偏好嵌入到 acquisition
  里，shift surrogate mean。**第一个把 LLM 当 expert prior 全程参与**的框架。

三篇构成"本周 LLM-augmented BO" topical cluster，覆盖三种范式（保真融合 / 训练
自由 / 偏好引导）。一周三篇说明这是当前 SciML 热点方向。

## 研究问题

BO 在科学发现中两痛点：(a) cold-start 慢，(b) 高维 curse-of-dimensionality。前人
把 LLM 接进 BO 多是 warm-up initialization 或 candidate proposal——LLM 信号只用一次
就被 acquisition function 盖过。如何让 LLM 偏好**全程指导**优化？

## 方法

**LGBO** = LLM-Guided BO，核心机制：
- **Region-lifted preference**：每轮把 LLM 对候选区域的偏好（"这块更好"）嵌入到
  surrogate mean shift——不是改 acquisition function，而是改先验。
- 这种偏好嵌入是**stable 和 controllable** 的——理论上证明：
  - 偏好对齐时：显著加速。
  - 偏好误导时：worst-case 不比 standard BO 差太多。

## 关键结果

- 物理 / 化学 / 生物 / 材料 multi-domain 干 benchmark 上一致优于 baselines（包括
  LABO 这类同期工作）。
- **湿实验**：Fe-Cr 电池电解质优化，**6 次迭代达到最佳值的 90%**，standard BO 和
  其他 LLM-augmented baselines 需要 10+。湿实验是这三篇中**最有说服力的实证**。

## 与我研究方向的关联

**对 fea_surrogate：方法学价值，应用域偏远。**
- 与 LABO 的差异：LABO 把 LLM 当 fidelity，LGBO 把 LLM 当先验。两者都不直接适合
  user 的"FEA-in-loop"工程优化场景（LLM 不懂髋柄 CAD）。
- **可借鉴**：把"工程领域专家知识"以偏好形式嵌入 acquisition 的思路——FEA 优化
  中工程师对设计空间有强 prior（如"应力集中区不能开洞"），这种偏好用 mean shift
  方式嵌入是优雅的工程实践。

**对 ai_bioprinting**：高度相关。湿实验的电解质配方优化与生物墨水配方优化同构。

## 局限

- 与 LABO/LLM-AL 一样：API 成本未深入分析。
- preference mechanism 的具体形式 paper 没在前几页写出来——可能在 Section 3 详细
  推导，未深入读。
- "expert prior alignment" 在工程领域可能比化学领域更弱——化学专家知 fluence
  比工程师对未知 hip stem 设计强多了。

## 是否值得跟进

**中等优先**。把 LGBO + LABO + LLM-AL 三个一起记入"LLM-augmented BO/AL"知识地图。
**LGBO 的湿实验结果（6 vs 10+ 迭代）是该方向目前最强的实证**，最值得记住。

未来若做生物墨水配方 BO 优化，按以下优先级试：LGBO（湿实验已验证）> LLM-AL（无
训练快速原型）> LABO（要 regret bound 时）。

## 评分系统反馈

本周三篇 LLM+BO 都判 Medium 是合理的——单看每篇都是 incremental，但作为 cluster
显示 SciML 的真实 frontier，**周报应在 trend 章节专门提**。priority 没漏掉重要
方向但也没虚高单篇。
