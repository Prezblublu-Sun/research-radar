# LABO: LLM-Accelerated Bayesian Optimization through Broad Exploration and Selective Experimentation

- **id**: `arxiv:2605.22054v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读 + 略读后半）
- **来源**: arXiv 2605.22054（ICML 2026），SJTU / 哈工大 / 上海 AI Lab / 中石大

## 研究问题

科学优化（药物发现、催化剂、分子工程、材料）单次真实实验昂贵 + 数据稀缺。
传统 Bayesian Optimization 在 cold-start 和高维 search space 下效率受限。前人把
LLM 接进 BO 多是局部（initialization / acquisition refinement），没充分利用
"LLM 评估比真实实验便宜几个数量级"这一性质。

## 方法

**LABO** = LLM-Accelerated BO，dual-fidelity BO 框架：
- **建模端**：KOH（Kennedy–O'Hagan）多保真高斯过程 → fR(x) = ρ·fL(x) + δ(x)，
  其中 fL 是 LLM-fidelity 预测，δ 是真实-LLM 差异项。kL 和 kδ 是独立 GP 核。
- **决策端**：discrepancy-dominance gating criterion τ（论文最佳 τ=0.75）——
  根据"预测不确定性中 δ 项占比"判断该候选是用 LLM 评估还是触发昂贵真实实验。
  LLM 预测覆盖广域 + 真实实验只用在高不确定区域。
- **理论**：给出 cumulative regret bound，证明 LLM 信号信息量足时 sample efficient，
  LLM 误导时仍 robust（受 KOH 假设保护）。

## 关键结果

- 在化学/材料任务（Fullerene、COF 共价有机框架等）上同 budget 下优于
  baselines（LLAMBO、BOPRO、ReasoningBO 等）。
- 消融：LLM 初始化贡献部分 gain 但非全部；用随机 fidelity 替代 LLM-fidelity
  显著变差 → LABO 收益来自 LLM 知识先验本身。
- LLM 模型 size 影响：Intern-S1（mini→7B 到 Qwen3-235B 到 DeepSeek V3.1 685B）
  随能力提升优化结果变好，但差异不大；Qwen3-Thinking > Qwen3-Instruct，说明
  推理能力比纯参数量更关键。
- 任务越简单（Fullerene），LLM:real 查询比例越高；越难（COF 高维），越依赖真实
  实验——LABO 自适应分配。

## 与我研究方向的关联

**对 fea_surrogate：方法学有借鉴，但应用域不直接对接。**

1. **KOH 多保真框架**直接可移植：fea_surrogate 中常见的"粗 FEA 网格（低保真）
   vs 细 FEA（高保真）"完全可以套这套 GP+discrepancy+gating，无需 LLM 参与。
   论文做了精彩的"知识源是 LLM"这一具体案例，框架本身是 fidelity-agnostic。
2. **LLM-as-fidelity 对生物力学 FEA 价值有限**：LLM 不知道你的患者 CT 几何，
   也不真知道接触界面力学的数值——比化学优化任务弱。但 LLM 可能在 **"设计空间
   先验"** 上有价值（例如：哪个植入物参数组合"看起来"合理）。
3. **Gating criterion 的"discrepancy-dominance"思路**有方法学价值：fea_surrogate
   里"何时用代理 vs 何时跑 ground-truth FEA"是一个反复出现的工程问题，
   uncertainty-based gating 是 principled 思路。

**对 am_biomedical / ai_bioprinting**：bioprinting 工艺优化本身是 BO 高匹配
场景（每次打印实验成本高），LABO 可直接试。

## 局限

- 评估全是化学/材料 BO benchmark（Fullerene、COF、Hamidieh 超导等），没在
  传统 BBOB 或工程设计任务（FEA-in-the-loop）上测。
- "LLM 评估" 的成本统计偏理想化——大模型 API 不真便宜，且 latency 与并行度
  限制未深入讨论。
- KOH 标量 ρ 由 OLS 拟合，假设全域线性缩放可能在多模态目标上失效。
- 利益冲突：作者们属于上海 AI Lab，LLM 中包含他们自家的 Intern-S1，结果偏倚
  风险存在（虽然他们也跑了 Qwen、DeepSeek 对照）。

## 是否值得跟进

**值得跟进（中等优先）**。建议：
1. 把 KOH+gating 框架记入 fea_surrogate "多保真训练" 工具箱（与 Therm-FM 的
   两阶段策略并列）。
2. 暂不在自己工作里实装 LLM-fidelity；等"工程问题 + LLM 先验"的可靠 case study
   出现再说。
3. 关注后续：如有人把 LABO 框架用到 FEA 优化（如 hip stem 设计空间），是高
   信号事件。
