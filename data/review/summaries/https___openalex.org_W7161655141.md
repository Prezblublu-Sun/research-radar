# Curriculum Learning of Physics-Informed Neural Networks based on Spatial Correlation

- **id**: `https://openalex.org/W7161655141` · 方向 fea_surrogate · 优先级 High · checked
- **失败原因**: no_open_access_link + no DOI/arxiv (OpenAlex fallback)
- **来源**: 2026-05-14（**W20**）

## 复核

- **方向**：正确。PINN + 课程学习 + 空间相关性传播 + 区域一致性，fea_surrogate
  方法学。
- **优先级 High**：合理偏低。"课程学习 + 空间因果权重 + 低频信息桥 + 区域自适应
  重加权"是 PINN 工程优化方向有意义的组合，但单看不算 ADR-0024 novelty=high。
  与 W21 GMM-curriculum-PINN + CMA-PINN 诊断同 cluster——PINN 训练改进是连续
  两周热点。
- **摘要质量**：好。具体技术（空间因果权重、低频信息桥、区域自适应）+ 验证形式
  （多 benchmark）。
- **跟进**：值得（若用 PINN）。机构权限拿 PDF 后看与 GMM-curriculum 的方法学
  差异。

## 趋势 — PINN 训练诊断与改进 cluster

W21 + W20 共出现：
- W21 CMA-PINN 诊断（NTK/CKA 分析 PDE 公式）
- W21 GMM-curriculum-PINN（残差分布拟合 + 动态课程）
- W21 NPINN+（非局部 BC 等价变换 + RAR + 自适应权重）
- W20 **本文** Spatial Correlation Curriculum-PINN
- W20 PI-SWNO（时空解耦）

**两周累计 5 篇 PINN 训练改进**，说明 PINN 落地工程优化仍是活跃研究痛点。
