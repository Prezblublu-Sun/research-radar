# Optimization behavior in Physics-Informed Neural Networks: Diagnostic analysis of PDE formulations

- **id**: `doi:10.1016/j.cma.2026.119070` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: extract_failed_or_scanned（CMA Elsevier）
- **来源日期**: 2026-05-19（**W21**）

## 复核

- **方向**：正确。PINN + PDE 公式分析 + 固体力学/多孔介质，fea_surrogate 核心。
- **优先级 Medium**：合理偏低。诊断/分析类论文不是直接可用工具，但对设计 PINN
  的工程实践极有价值。如果 user 自己用 PINN 做骨/植入物力学，该论文是必读。
- **摘要质量**：好。具体技术（NTK、CKA、原始/混合/能量公式）+ 应用域（流体、
  多孔、固体）+ 关键发现（异构约束削弱全局物理学习）。
- **跟进**：值得。机构权限取 PDF 后看：(a) NTK 分析中能量公式 vs 残差公式的具体
  差异；(b) 固体力学案例选哪些（线弹性？大变形？接触？）；(c) 对 hyperelastic
  植入物应力分析的 PINN 设计建议。
- 与本周 IKNO（算子学习）和 Neural Compiler（hybrid SciML）形成"PINN/算子学习/
  hybrid"三论文方法论矩阵——本文是 PINN 阵营的健康度诊断。
