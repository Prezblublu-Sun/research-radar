# AI-Driven cross-scale modeling for SiP thermo-mechanical simulation

- **id**: `doi:10.1108/ssmt-03-2026-0017` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link（Emerald 出版商 SSMT 期刊）
- **来源**: 2026-05-18（**W21**）

## 复核 — fea_surrogate routing noise 候选 ★

- **方向**：技术上 fea_surrogate（CNN 代理 + 均质化 + 多材料 FEA），但**应用是
  SiP（System in Package，半导体封装）热翘曲**——与 SSPC 那篇同属电子封装热-力问题，
  与 user 生物力学完全无重叠。
- **优先级 Medium**：合理偏高。如纯按"对 user 边际价值"应是 Low。
- **摘要质量**：好。数据具体（网格单元 1/3136 缩减，单斜均质化、多通道灰度像素
  编码），方法路径清晰。
- **方法学借鉴**：跨尺度均质化 + CNN 预测本构参数的思路在生物力学骨小梁
  (trabecular bone) 跨尺度建模中**有潜在迁移价值**——骨小梁的微观各向异性
  也可以用 CNN 从 CT 灰度直接预测本构。这点比 SSPC 那篇要更可借鉴。

## 评分系统反馈 ★

本周已知三篇**电子/半导体 PINN/代理建模**论文落到 fea_surrogate：
1. Therm-FM（3D-IC thermal）— **High**，方法学创新极强（PDE foundation model + 多保真），
   是有借鉴价值的核心，不是 noise。
2. SSPC 热代理（W21 Medium）— 方法 incremental，应用边缘，**轻度 noise**。
3. **本文 SiP 跨尺度**（W21 Medium）— 方法可借鉴（CNN 像素编码 + 均质化），
   应用边缘但**有一点迁移价值**。

**结论**：fea_surrogate 的"电子封装热-力"长尾**不算彻底 noise**——其中
方法学新颖度高的（如 Therm-FM 的 foundation model）应该保留 High；
方法 incremental 应用边缘的应该降到 Low。**建议 scorer prompt 增加判定规则**：
对"PINN/算子学习 应用于电子热-力"类论文，按"方法学创新度"二分。

## 跟进

不必精读。但 CNN-多通道像素编码做均质化的思路记入"骨小梁多尺度建模"工具箱。
