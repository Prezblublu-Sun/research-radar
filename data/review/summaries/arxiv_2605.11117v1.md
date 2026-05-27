# GRAFT-ATHENA: Self-Improving Agentic Teams for Autonomous Discovery and Evolutionary Numerical Algorithms

- **id**: `arxiv:2605.11117v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读摘要 + 引论）
- **来源**: arXiv 2605.11117, 2026-05-11（**W20**），Brown University Applied Mathematics
- **作者**: Juan Diego Toscano + Zhaojie Chai + **George Em Karniadakis**（PINN 范式
  原始提出者之一，是 SciML 领域核心人物）

## 核心思路

科学发现 = 把物理问题映射到数值解的概率决策序列。现有 agentic AI 框架（LLM
planner + solver + evaluator）独立处理每个问题，没有跨问题积累方法学经验的
共享基础。**GRAFT-ATHENA** 是 self-improving agentic 框架：

- **GRAFT**（Graph Reduction to Adaptive Factored Trees）：把组合决策空间投影到
  factored probabilistic trees，每个方法是一条路径。参数足迹从指数到线性。
- **I-map of policy**（Bayesian network 谱系）：factorization 是政策的 I-map，
  路径在度量空间中作为指纹存在 → 新问题从相似旧问题中学习。

## 关键结果

- **PIML benchmarks**：达到 near-machine-precision，超过人类 + 之前的 agentic baselines。
- **复杂工程问题**：
  - 1968 年报告的 Mach-10 阿波罗指令模块流场重建
  - **血液流变学 shear-thinning recovery**（血液动力学相关，有 user 关联）
- **自主发现新方法**：自主提出 ill-posed 逆问题的正则化约束 + 发现**指数收敛的
  spectral PINN**。

## 与我研究方向的关联

**对 fea_surrogate：方法论级影响，长期相关。**

- "Self-improving agentic discovery of numerical methods" 是真正的 long-term 范式
  转变。Karniadakis 组（PINN 原创团队）的押注信号意义重大。
- **血液流变学验证案例**对 user am_biomedical/生物流体有间接关联，证明能处理
  生物医学问题。
- 与 W21 LABO/LGBO/LLM-AL（LLM-augmented BO）+ W20 NIMO（MCP-based SDL）共同
  构成**"LLM/agent + 科学计算"trend**——但 GRAFT-ATHENA 是其中**层次最高的
  方法学积累框架**。

**对其他方向**：弱直接关联。

## 局限

- 自主发现的新数值方法（spectral PINN with exp convergence）需独立验证。
- "近机器精度"通常 PIML benchmark 上偏 toy。
- agentic 框架 LLM 调用成本未量化。
- 多 agent 系统可重现性常有问题。

## 是否值得跟进

**强烈建议（中-高）**。Karniadakis 组工作很少不重要。建议：
1. 关注 spectral PINN with exponential convergence 的具体技术——如果能在生物
   力学 PDE 上保持指数收敛，是 game changer。
2. 长期跟踪 GRAFT-ATHENA 框架的开源情况。
3. 思考：能否用这套框架自动化 user 自己的"hip 几何 + 本构 + FEA 求解器选择"
   组合决策？

## 评分系统反馈

priority=Medium 偏低。Karniadakis 组 + Brown + 跨问题学习 + 血液流变学验证案例
+ 自主发现新数值方法——单看每项 Medium，**合在一起应是 High**。但 scorer 难以
识别"作者机构权重"，且 agentic AI 是新颖范式 scorer 未必有先验。

## ADR-0024 vs 本文

本文是 ADR-0024 草案的有意思测试样本：novelty=high（方法学新颖度极高）；
pathway=adjacent（PIML + 血液流变学 → 生物力学有迁移路径但需中间桥）。按 ADR-0024
应保留或上调到 High。
