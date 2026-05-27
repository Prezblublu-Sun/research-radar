# BACO: Bayesian Algorithm for Collaborative Optimization (Aircraft Design)

- arXiv: 2605.05474v1（2026-05-06）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**多学科设计优化 (MDO)** 中 collaborative optimization (CO) 框架的双层黑箱评估成本高。

## 方法
**BACO**: GP surrogate + acquisition function 替代昂贵的双层黑箱调用，转化为 Bayesian 优化范式。

## 关键结果
- 50 次随机 MDO 基准 + CRM 机翼气动结构优化
- 比 baseline 评估次数少 + 目标值更低 + 约束违反接近零

## 与我研究方向的关联
**fea_surrogate (弱相关)**：航空 MDO 与我电子封装 / 生物医学方向不同；但**BO + GP 替代 CO 双层黑箱**思路在 FEM + AI 优化 loop 中可借鉴。reference 级。

## 评分体系反馈
Direction `aerospace_mdo` 更准。existing_summary 准确。
