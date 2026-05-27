# A calibrated residual physics-informed neural network surrogate for junction temperature prediction and heat-sink optimization of airborne SSPCs

- **id**: `doi:10.1016/j.icheatmasstransfer.2026.111588` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link
- **来源日期**: 2026-05-22（**W21**）

## 复核 — fea_surrogate routing noise 候选 ★

- **方向归类**：技术上正确（PINN + FEA 替代 + 热场预测），但**应用域是航空固态功率
  控制器（SSPC）** —— 与 user 的生物力学 / 骨 / 植入物核心研究无任何重叠。
- **方法相似度**：与上面 Therm-FM 的"PDE surrogate for thermal"算同类（神经算子 vs PINN，
  两种范式），但 Therm-FM 还有"foundation model"和"跨设计迁移"等可借鉴的方法学创新；
  这篇是"应用 + 局部校准"的 incremental 工作，**方法学新意有限**。
- **优先级 Medium**：合理偏高。理由：方法学借鉴价值低（residual PINN + calibration
  是熟悉技术组合），应用域无对接。如果纯按"对 user 的边际价值"判，应该是 Low。
- **摘要质量**：偏弱。motivation 没说为何 PINN 优于普通神经网络（如果只是更准更
  快，那是行业常识）；method 没说"calibrated residual"具体是什么校准；result 是
  纯定性。

## 评分系统反馈 — 这是 fea_surrogate routing-noise 的典型样本 ★

**routing 命中机制可能是**：标题里有 "physics-informed neural network surrogate"
+ "FEA-like behavior" 这类关键词，但完全没考虑应用域是 EE/power-electronics 而非
biomechanics/biomedical。

**建议**：fea_surrogate routing 增加"应用域负关键词"（如 airborne / SSPC /
power electronics / aerospace electronics 等），或在 LLM scorer prompt 中加一条
"若 fea_surrogate 命中但应用域为电子/电气 PINN 工作，重新评估为 Low"。

这种条目积累多了，会真实抬高 fea_surrogate 的 noise floor，使精读循环的有效命中
率下降——值得在 W21 周报中正式记录。

## 跟进

不必。如做方法学综述时可以再回看其 calibration 技巧的具体实现。
