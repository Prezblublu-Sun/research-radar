# Spatial statistics for screening molecular structures

- **id**: `arxiv:2605.17147v1` · 方向 fea_surrogate · 优先级 Medium · **read**（精读引论与方法概要）
- **来源**: arXiv 2605.17147, 2026-05-16（**W20**）

## 核心思路

数据稀缺下的分子筛选代理建模——用**空间统计 two-point correlation function +
PCA 降维**构造凸表示。10 个训练样本即达 < 2% 预测误差。在周期晶体、高熵合金
（HEA）、有机分子上验证。

## 与 fea_surrogate 关联

- 方法学：two-point correlation + PCA 是经典材料信息学工具（PyMKS 系列）。
  对**骨小梁微观结构 → 宏观力学**这类多尺度问题有潜在借鉴（骨小梁形态学
  描述与晶体周期性有形式相似）。
- 应用域偏远：分子/晶体/HEA 不是 user 直接方向。

## 局限

- 凸表示假设可能在多模态结构空间下失效。
- 仅 10 样本就 <2% 误差的报告需要看 benchmark 是否过简单。
- 与 PyMKS / Materials Informatics 系列工作的方法学增量需要在主文中确认。

## 评分系统反馈

priority=Medium 合理；方法学是已知技术组合（two-point + PCA），不算 ADR-0024
"novelty=high"，应用域偏远，pathway=adjacent。**典型"中等借鉴价值"案例**。

## 跟进

低。但若 user 后续做骨小梁多尺度建模，此类 spatial statistics 描述符值得回看。
