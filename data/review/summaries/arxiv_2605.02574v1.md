# Fast and Accurate Conditioning for Large-Scale and Online GP Prediction

- arXiv: 2605.02574v1（2026-05-04）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
大规模 / 在线 GP 预测成本高，需要高效精确近似。

## 方法
**精心选择数据对比 (contrasts)** 做 GP 条件化 —— 少量 contrasts 即可机器精度近似；**online prediction O(1)**。

## 关键结果
- 少量 contrasts 达到机器精度
- 在线复杂度 O(1)

## 与我研究方向的关联
**fea_surrogate (弱相关)**：高效 GP 算法可用于工程 BO / surrogate；与 [[arxiv_2605.08036v1]] CUTS-GPR 同 GP scalability 主题。Reference 级。

## 评分体系反馈
Direction 偏弱 fit。existing_summary 准确。
