# Real-Time Catenary AI: Surrogate vs. PINN Models for Stress Ribbon Bridges

- **id**: `doi:10.5281/zenodo.20230081` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link（Zenodo 404，是 ADR-0025 提案中的 Zenodo namespace）
- **来源**: 2026-05-16（**W20**）

## 复核 — 边缘 fea_surrogate

- **方向**：技术上 fea_surrogate（surrogate vs PINN 对比 + 非线性悬链方程），
  但**应用是 stress ribbon 桥梁** —— 与 user 生物力学完全无关。
- **优先级 Medium**：合理偏高。按 ADR-0024 草案：novelty=low（surrogate vs PINN
  对比是熟悉技术）, pathway=none。
- **摘要质量**：差。**"NMAE<55%"是严重红旗** —— 这是接近"完全错"的误差水平
  （随机猜测都不会更差），不是"AI 模型比 exact solver 快 33×"的好结果。
  存在两种可能：(a) LLM scorer 误读了原文（可能是 <5.5% 或 <0.55%）；(b) 原
  论文本身报告了大误差作为 negative result。
- **跟进**：不必。但是**摘要 NMAE 数字异常**值得本周报作为"scorer 数字幻觉
  风险"案例提一下。

## ADR-0025 验证

本条命中 `10.5281/zenodo.*` namespace，验证 ADR-0025 提案的覆盖范围正确——
当前没看到 `.vN` 版本，但 Zenodo 也支持版本化 DOI，需要在实施时一并处理。
