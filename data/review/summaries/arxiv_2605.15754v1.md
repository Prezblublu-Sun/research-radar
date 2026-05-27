# PI-SWNO: Spatiotemporal decoupled physics-informed Stone-Weierstrass neural operator for long-time prediction of time-dependent parametric PDEs

- **id**: `arxiv:2605.15754v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读摘要 + 方法概要）
- **来源**: arXiv 2605.15754 (physics.comp-ph), 2026-05-15（**W20**），Tsinghua 安全科学

## 核心思路

现有 neural operator 在长时间 PDE 预测下精度退化、稳定性差、训练成本高、显存
大。**PI-SWNO** 用时空解耦（时不变空间基函数 + 时变演化系数）+ Stone-Weierstrass
逼近定理 + time-marching batch-wise sampling 策略。两子网分别编码 spatial / temporal
信息。

## 与 fea_surrogate 关联

- 长时间 PDE 预测在生物力学非主流场景（user 主要是 quasi-static 弹性问题），
  对长期骨重建模拟（年-十年时间尺度）才有意义。
- "时空解耦"思路本身经典——Stone-Weierstrass 加持是数学上的新颖。

## 评分

priority=Medium 合理；novelty=medium（理论加持但 spatiotemporal decoupling 是
已知技术），pathway=adjacent（长时间 PDE → 骨重建有类比）。

## 跟进

低。除非 user 做长时间生物组织演化建模。
