# Bayesian Optimization in Linear Time

- arXiv: 2605.00237v1（2026-04-30）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
标准 GP-BO O(N³) cost；全局 GP 对局部优化也低效。

## 方法
**递归二分划分** 搜索空间 + 局部建模 + acquisition function → **线性复杂度 BO**。

## 关键结果
- 6-124 维测试函数：超过常用 BO 库
- 线性 wall-clock 复杂度

## 与我研究方向的关联
**fea_surrogate (中相关)**：高维 BO 对工程 design optimization 直接有用。与本周 W19 [[arxiv_2605.06618v1]] MTRBO、[[arxiv_2605.05474v1]] BACO 同 BO scalability 主题；与 [[arxiv_2605.08036v1]] CUTS-GPR (高维 incomplete grid GP) 互补（前者解 acquisition 复杂度，后者解 surrogate 复杂度）。Reference 级。

## 评分体系反馈
Direction 偏弱（ml_bo 更准）。existing_summary 准确。
