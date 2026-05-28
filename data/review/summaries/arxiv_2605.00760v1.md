# Learning the Helmholtz equation operator with DeepONet for non-parametric 2D geometries

- arXiv: 2605.00760v1（2026-05-01）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**Helmholtz 散射场**在每个新几何上要重新 mesh + FE 解，many-query 场景昂贵。

## 方法
- **SDF (Signed Distance Function)** 编码几何，作为 DeepONet branch 输入
- Trunk 输入坐标 (x, y)
- Output: 散射场

## 关键结果
- 对**未见几何**泛化
- 比 FEM 计算轻量

## 与我研究方向的关联
**fea_surrogate (中相关)**：SDF + DeepONet 处理变几何是工程 surrogate 通用模式。与本周 W19 [[arxiv_2605.07987v1]] DeepSDF 类几何表示思路相通；与 [[arxiv_2605.09016v1]] CATO 学 chart 是另一条路径。Reference 级；Helmholtz 不是我研究主线。

## 评分体系反馈
Direction 正确。existing_summary 准确。
