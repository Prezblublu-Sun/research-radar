# Tyche: One Step Flow for Efficient Probabilistic Weather Forecasting

- arXiv: 2605.06916v1（2026-05-07）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 误：实际是 weather_forecasting + diffusion-distillation**

## 研究问题
扩散模型在概率天气预报取得 SOTA 但推理多步（10-50 step）昂贵；本文目标：1 步生成即可达到多步质量。

## 方法
**Tyche** = 单步条件 flow 模型 + **JVP-regularized rectified flow** 目标 + 大气数据训练 (ERA5)。

## 关键结果
- 单步评估 ≥ multi-step diffusion baseline
- 与 ECMWF IFS ensemble forecast 精度持平或更好
- ERA5 全球 reanalysis 数据验证

## 与我研究方向的关联
**fea_surrogate（弱相关）**：本文是**气象 + diffusion-distillation**，与 FEM/PDE surrogate 完全不同 domain。**唯一可借鉴 takeaway**：rectified flow + JVP 正则做 distillation 的方法，对未来训练 fast 1-step PDE surrogate 有 transferable value。

## 局限
- Weather forecasting domain，对工程 surrogate 直接价值零
- 1-step rectified flow 训练稳定性是常见痛点；JVP 正则细节是关键

## 评分体系反馈
- **Direction `fea_surrogate` 严重错位**：应归 `weather_forecasting` 或 `generative_distillation`。本周 direction misclassification 累积，建议 v4 scorer 加 "atmospheric_science" 子方向。
- existing_summary 准确简洁。无错。
