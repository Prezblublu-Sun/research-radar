# Conformalized Percentile Interval: Finite Sample Validity and Improved Conditional Performance

- arXiv: 2605.03233v1（2026-05-04）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 误，应为 generic_ml / conformal_prediction**

## 研究问题
现有 conformal prediction 区间条件 validity 和 width 效率不足。

## 方法
在 **probability integral transform (PIT) 空间**做 quantile interval calibration + NN 估计条件 CDF。

## 关键结果
- 合成 + 真实 benchmark：更好条件 calibration + 更短 interval
- Finite-sample validity guarantee

## 与我研究方向的关联
**fea_surrogate (弱相关)**：与 [[arxiv_2605.08561v1]] CONTRA 同 conformal UQ 主题。对工程 surrogate 输出 calibrated PI 有用。Reference 级。

## 评分体系反馈
Direction `ml_uq / conformal` 更准。existing_summary 准确。
