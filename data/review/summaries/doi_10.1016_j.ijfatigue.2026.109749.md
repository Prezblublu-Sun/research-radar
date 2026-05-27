# An integrated computational modeling framework for predicting fatigue crack growth in additive manufactured TPMS structures

- **id**: `doi:10.1016/j.ijfatigue.2026.109749` · 方向 am_biomedical · 优先级 High · checked
- **失败原因**: `not_article_like_or_landing_page`（新 harness gate 正确判定 landing page）
- **来源**: International Journal of Fatigue, 2026-05-15（**W20**）

## 复核

- **方向**：正确。LPBF + TPMS + 疲劳裂纹扩展 + 集成多尺度建模 + 残余应力 + 微观
  结构异质性 + 紧凑拉伸实验，**am_biomedical 核心 + 与 hip_implant 强相关**
  （髋柄/植入物 TPMS 段疲劳寿命是临床认证瓶颈）。
- **优先级 High**：合理。理由：(a) IJ Fatigue 是断裂力学一线期刊；(b) "TPMS 疲劳
  裂纹扩展"主题 + 多尺度建模 + 实验验证是 user 直接关心的工程问题；(c) 涵盖
  打印方向、热处理、相对密度三个工艺变量对疲劳寿命的影响。
- **摘要质量**：很好。具体技术（多尺度建模 + 断裂力学 + 热-力 FE）+ 实验配套
  （紧凑拉伸）+ 工艺变量明确。
- **跟进**：**强烈建议**。机构权限取 PDF 后看：(a) 残余应力的多尺度建模具体如何
  耦合到裂纹扩展（这是技术核心）；(b) 紧凑拉伸结果与模拟吻合的具体定量指标；
  (c) 是否可平移到 Ti6Al4V TPMS 髋柄段。

## 与 W21 LPBF 疲劳 ML（Usman Ali）的呼应

W21 已有"LPBF FCC/BCC/HCP 疲劳 ANN 预测"，本周本文是"LPBF TPMS 疲劳裂纹扩展
多尺度建模"——两者**互补**：前者是数据驱动 ML 端到端预测，后者是物理驱动多尺度
建模。**LPBF 疲劳预测是 W20+W21 两周的明显热点 cluster**，对 user am_biomedical
方向有重要信号——值得在 W20 周报正式标记。

## 评分系统反馈

priority=High 正确。LPBF 疲劳类工作连续两周 High 命中，scorer 对 user 核心
am_biomedical 工程问题识别良好。
