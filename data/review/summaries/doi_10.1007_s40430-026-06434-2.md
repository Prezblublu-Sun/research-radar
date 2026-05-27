# Physics-informed neural network framework for accurate pressure drop prediction in laminar and turbulent pipe flows

- **id**: `doi:10.1007/s40430-026-06434-2` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link (Springer J Braz Soc Mech Sci Eng)
- **来源**: 2026-05-16（**W20**）

## 复核 — 边缘 fea_surrogate

- **方向**：技术上 fea_surrogate（PINN + 流体方程 + 代理建模），但**应用是
  管道流压降**，与 user 生物力学完全无关。
- **方法学**：Navier-Stokes 残差 + 数据损失的标准 PINN——无新意。
- **优先级 Medium**：合理偏高。按 ADR-0024 草案应是 novelty=low,
  pathway=none → 降到 Low。
- **跟进**：不必。

## ADR-0024 验证样本

加入"electronics/engineering domain + low novelty"长尾计数。
本周已累计：本文 + Haversian-gyroid（不算，那是 am_biomedical）+ ... 等待累计 4 周
数据后再正式提议。
