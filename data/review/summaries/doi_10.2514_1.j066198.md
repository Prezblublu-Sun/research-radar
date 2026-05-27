# Efficient Fatigue Reliability Life Analysis Method Based on Sequential Adaptive Surrogate Model

- **id**: `doi:10.2514/1.j066198` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link（AIAA Journal）
- **来源**: 2026-05-18（**W21**）

## 复核 — 方法对接，应用域边缘

- **方向**：正确。自适应 Kriging 代理 + 疲劳可靠性 + FEA 替代，fea_surrogate 核心
  方法学。**应用是航空发动机涡轮盘和轴**——非生物力学，但**方法可直接迁移**到
  髋柄/植入物的疲劳可靠性。
- **优先级 Medium**：合理。理由：(a) 自适应 Kriging + 序贯采样是 fea_surrogate
  方法学成熟工具，本文是 incremental 改进；(b) "逆问题转正向 + 自适应"思路对
  user 的 hip stem 疲劳寿命概率分析有借鉴价值。
- **摘要质量**：好但缺关键指标——未报告样本数节省比例、最终精度数字。
- **跟进**：值得（与上面 Usman Ali 的 ML 疲劳预测论文搭配）。机构权限取 PDF 后看：
  (a) Kriging 自适应采样准则的具体形式；(b) 反向问题 → 正向问题的等价变换数学；
  (c) 是否能扩展到 multi-physics 疲劳（如骨-植入物界面的应力 + 微动腐蚀疲劳）。

## 评分系统反馈

这篇与 SSPC、SiP、地热那批不同——**虽然应用域是航空，但方法学（自适应 Kriging
+ 疲劳可靠性）是 fea_surrogate 直接可借鉴的工具**。判定 Medium 合理；不属于
routing noise。说明 fea_surrogate 边缘命中里要分辨"方法学可借鉴"vs"应用域电子"
两类。
