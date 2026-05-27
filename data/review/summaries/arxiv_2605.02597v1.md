# Isotropic Fourier Neural Operators

- arXiv: 2605.02597v1（2026-05-04）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
标准 FNO 不严格保**空间旋转对称性**，可能导致物理不一致 + 参数浪费。

## 方法
**Isotropic FNO**：修改 spectral convolution 的 weight tensor 使其在旋转下不变（用 radial basis 替代 fully-parameterized Fourier weights）。

## 关键结果
- 同精度下 **参数 2D 减少 16×，3D 减少 96×**
- 标准 PDE benchmark 验证

## 与我研究方向的关联
**fea_surrogate (相关)**：FNO 旋转对称化是好的 inductive bias，对各向同性材料 PDE surrogate 直接可用。Reference 级；如未来用 FNO 类工作可考虑这个变体。

## 评分体系反馈
Direction 正确。existing_summary 准确。
