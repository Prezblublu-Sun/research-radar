# Frequency Bias and OOD Generalization in Neural Operators under a Variable-Coefficient Wave Equation

- **id**: `arxiv:2605.12997v1` · 方向 fea_surrogate · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.12997, 2026-05-13（**W20**）

## 核心思路

诊断性研究：FNO vs DeepONet 在变系数波动方程上的 OOD 表现。结构化分布偏移
实验（频率 + 系数平滑度）。

## 关键发现

- FNO 在频率偏移下**误差剧增**——暴露 FNO 的 frequency bias 问题。
- DeepONet 退化较缓但**整体误差更高**——两条路线各有 trade-off。

## 与 fea_surrogate 关联

- 诊断类工作，对工程选型有价值。生物力学常面对"训练分布外的患者数据"，OOD
  泛化是临床部署关键。
- 与 W21 PACE-FNO（用对称性改善 OOD）形成对照——本文是诊断，PACE 是解药。

## 评分

priority=Medium 合理。novelty=medium（系统化诊断有价值但非新方法），pathway=adjacent。

## 跟进

低-中。若 user 用 FNO/DeepONet 做生物力学，本文是 OOD 风险参考。
