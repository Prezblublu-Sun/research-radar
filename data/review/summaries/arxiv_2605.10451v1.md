# Don't Fix the Basis — Learn It: Spectral Representation with Adaptive Basis Learning for PDEs

- **id**: `arxiv:2605.10451v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.10451, 2026-05-11（**W20**）

## 核心思路

固定全局基（如 Fourier 在 FNO 中）难以表示多尺度 + 空间异质 PDE 动力学。
**自适应谱表示**：学数据依赖的 Parseval frame（保持正交性的可学习基）。

## 关键结果

PDE benchmark 提升精度，对**尖锐梯度 + 多尺度**问题尤其显著。

## 与 fea_surrogate 关联

- 又一篇神经算子方向方法学创新——本周第 N 篇。
- 适应基对生物力学**应力集中**（尖锐梯度）问题有特别价值——髋柄/植入物界面
  是典型场景。

## 评分

priority=Medium 合理。novelty=high（adaptive basis learning 是有数学新意），
pathway=adjacent。

## 跟进

低-中。神经算子工具箱 +1。
