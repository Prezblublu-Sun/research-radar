# Physics-Aligned Canonical Equivariant Fourier Neural Operator under Symmetry-Induced Shifts (PACE-FNO)

- **id**: `arxiv:2605.18606v1` · 方向 fea_surrogate · 优先级 Medium · **read**（基于现有
  摘要 + 引论核心，方法路径清晰，未深入实验细节）
- **来源**: arXiv 2605.18606（2026-05-18，W21）

## 核心思路

标准 FNO 不尊重 PDE 方程的对称性（平移、旋转、伸缩），导致 OOD 泛化差。**PACE-FNO**
通过李代数坐标估计**先把输入场对齐到 canonical 参考系**，再用 FNO 处理，最后
恢复原坐标——把对称性"显式 baked in"而非希望网络隐式学到。

## 关键结果

Burgers / 浅水 / Navier-Stokes 上 OOD 相对误差**最多降低 12×**。1D/2D 周期域基准。

## 与 fea_surrogate 关联

- 与本周 IKNO 同类（神经算子改进），但侧重不同：IKNO 解决"表达力"（kernel 阶数），
  PACE-FNO 解决"泛化"（对称性）。两者可叠加。
- 对生物力学的迁移：弹性方程在材料性质/几何缩放下有对称性（如尺度无关性），
  PACE 思路理论上可移植——但实际 hip stem 几何是 SE(3) 群下不变性，比周期域复杂。

## 局限

- 仅在周期域 / 规则 grid 上测，对非规则网格（user 主战场）未验证。
- 李代数对齐成本：每次 inference 要做坐标变换。
- 摘要中"分布外"定义不明——是参数 OOD 还是几何 OOD？

## 跟进

中等。把 "equivariant" 思路记入神经算子工具箱，与 IKNO 一同评估。

## 评分系统反馈

priority=Medium 合理，本周方法学密度极高（同周已有 IKNO、Neural Compiler、CMA-PINN、
NPINN+、GMM-curriculum-PINN、PACE-FNO 六篇神经算子/PINN 方向文章），单篇 Medium
是恰当节流。
