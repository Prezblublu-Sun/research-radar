# 复核：SLM Process Parameters on Young's Modulus, Poisson's Ratio, and Impact Toughness of Ti6Al4V

- DOI: 10.3390/app16104652（Applied Sciences 2026，MDPI）
- 方向归类：am_biomedical（priority=Medium）
- pdf_found=false（HTTP 403；MDPI 在某些 IP 上有限流）

## 摘要复核
是典型的 **SLM 工艺-性能关系实验研究**：
- ✅ Ti6Al4V 是骨科 / 生物医学 SLM 的主流合金
- ✅ 三个力学指标（E、ν、冲击韧性）随工艺参数（激光功率 / 扫描速度 / 层厚等）呈非线性变化是已知现象
- ✅ "三性能呈抛物线趋势"、"冲击韧性最敏感、ν 最不敏感"——是合理且常见的实验发现
- ✅ "缺陷统计 + 断口 + 微观组织"是 SLM 力学研究标准三件套

## 优先级复核
**保留 Medium 合理**：
- Applied Sciences 是 MDPI 中等档次期刊；通常质量参差，但 SLM Ti6Al4V 是成熟方向，数据可信。
- 直接对应 am_biomedical 方向，是"工艺-结构-性能"关系的 input data 来源。
- **特别 valuable 的是泊松比 ν 的研究**：SLM Ti6Al4V 的 ν 测量在文献里相对稀少（通常假设 0.34 不变），本文若给出 ν 随参数变化的数据可作为 FEM 仿真的 input prior。

## 处置
checked。**值得拿 PDF**：UCL 图书馆 / sci-hub 可获得；如果未来做 SLM 工艺-FEA 联合 surrogate 工作，本文是 input prior 来源。

## 评分体系反馈
- Direction 与 priority 都合理。
- **HTTP 403 download error**：MDPI 对国内 / IP 有访问限制是已知问题。建议 harness 把 `download_error: 403` 单独标记 vs `no_open_access_link`，方便后续重试（403 是临时性的，no_link 是结构性的）。
