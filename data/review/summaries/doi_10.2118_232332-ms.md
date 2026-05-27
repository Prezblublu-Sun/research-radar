# Agentic AI-Driven Geothermal Reservoir Simulation and Optimization Using Surrogate Modelling for Rapid Site Screening

- **id**: `doi:10.2118/232332-ms` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link（SPE/OnePetro，会议论文）
- **来源**: 2026-05-18（**W21**）

## 复核 — fea_surrogate routing noise 候选 ★

- **方向**：技术上 fea_surrogate 命中（深度神经网络代理 + 高保真热模拟集成 + AI
  代理框架），但**应用是地热油藏 / 地热场地筛选**——与 user 生物力学完全无重叠。
  与 SSPC / SiP 一起构成本周 fea_surrogate 长尾噪声 cluster。
- **优先级 Medium**：合理偏高。如纯按用户边际价值应是 Low。
- **摘要质量**：好。具体指标（>99% 精度，毫秒级推理，从高保真热集成数据训练）+
  "agentic AI" 是当前热点术语。
- **方法学借鉴**：极弱。"agentic AI driving surrogate + simulation" 在生物力学
  FEA 工作流中也可以做（"agent 决定何时跑高保真 FEA vs 用代理"），但本质上就是
  LLM-orchestrated workflow，方法学上比本周的 LABO / LGBO / LLM-AL 三篇弱。

## 评分系统反馈

加入到 fea_surrogate routing-noise 候选清单（与 SSPC, SiP, NPINN+ 等并列）。
**本周已累计 4-5 篇这样的 fea_surrogate 边缘命中**，足以验证 user 的"fea_surrogate
routing 噪声"假设——周报中要正式记录并提改进建议。

## 跟进

不必。
