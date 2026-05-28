# Human-in-the-Loop Meta Bayesian Optimization for Fusion Energy and Scientific Applications

- arXiv: 2605.00068v1（2026-04-30）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
高成本科学实验（ICF 聚变能、分子优化）数据稀缺，标准 BO 慢；专家有领域知识但难融入。

## 方法
**Human-in-the-loop meta BO**：
- Meta-learning 在 related task family 上预训练 surrogate
- 专家通过 query / feedback 接口注入先验
- 联合优化

## 关键结果
- ICF energy yield + 分子优化基准
- 超过现有 BO baselines

## 与我研究方向的关联
**fea_surrogate (中相关)**：与本周 W19 [[arxiv_2605.09775v1]] vvBO、[[arxiv_2605.05474v1]] BACO 同 BO 主题。"Meta + human-in-the-loop" 思路对工程 FEM 设计优化（专家有 design intuition）可借鉴。Reference 级。

## 评分体系反馈
Direction 偏弱（应为 ml_bo），但与 fea_surrogate 工程优化有 transferable value。existing_summary 准确。
