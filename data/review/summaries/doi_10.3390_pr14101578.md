# Physics-Informed Neural Network Model for Reservoir Seepage in Porous Media Based on Darcy's Law

- **id**: `doi:10.3390/pr14101578` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: HTTP 403（MDPI Processes）
- **来源**: 2026-05-13（**W20**）

## 复核 — fea_surrogate 边缘命中

- **方向**：技术正确（PINN + Darcy + 多孔介质渗流），应用是油气藏。
- **优先级 Medium**：按 ADR-0024 草案 novelty=low（标准 Darcy-PINN）, pathway=adjacent
  （多孔介质 → 骨小梁渗流有类比）→ 建议 Low。
- **跟进**：低。

## ADR-0024 长尾计数 +1

本周 fea_surrogate "其他领域 + low novelty"已累计：
- W20: 管道流 PINN、Catenary bridge AI、reservoir seepage PINN（本文）
- W21: SSPC airborne PINN、SiP CNN 代理、Agentic 地热、NPINN+ 非局部 BC

合计 7 篇属本周长尾，符合 ADR-0024 假设。
