# 复核：NURBS-based parameterization PINN with adaptive architecture

- DOI: 10.1016/j.jcp.2026.114980（**Journal of Computational Physics**, 2026）
- 方向归类：fea_surrogate（priority=Medium）
- pdf_found=false

## 摘要复核
- ✅ NURBS 几何参数化 + PINN + 自适应架构：把 IGA (isogeometric analysis) 的几何表示与 PINN 结合，是合理的工程方向
- JCP 是计算物理顶刊，质量信号好

## 优先级复核
**保留 Medium 合理，可上调 Medium-High**：
- JCP 文章通常质量高
- NURBS + PINN 对复杂几何（CAD-imported 工程零件）是 enabling combination —— 直接关联电子封装、生物医学植入物的 surrogate 工作
- 与本周 CATO ([[arxiv_2605.09016v1]]) 的 chart-aware 思路理念相通（都试图把"几何复杂"内化到架构）

## 处置
checked。**强烈建议获取 PDF**：UCL 应能下载 JCP；对我研究主线（复杂几何 FEM surrogate）直接相关。

## 评分体系反馈
- Direction 正确。Priority Medium 可考虑上调（JCP + NURBS-PINN 组合是高价值）。
- existing_summary 简短但准确。无错。
