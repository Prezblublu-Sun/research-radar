# Machine learning framework for fatigue life prediction of LPBF AM FCC/BCC/HCP crystallographic structures

- **id**: `doi:10.1007/s43939-026-00696-2` · 方向 am_biomedical · 优先级 Medium · checked
  （Springer 着陆页 7KB，只能读到摘要）
- **来源**: Discover Materials, 2026-05-18（**W21**）
- **作者**: Usman Ali（单作者）

## 复核（基于摘要）

- **方向**：am_biomedical 命中正确——LPBF 制造件疲劳寿命是 user 主线核心问题
  （髋柄 LPBF 制造、疲劳寿命预测是临床批准的关键瓶颈）。
- **优先级 Medium → 边界 High**：偏低。理由偏 High：(a) LPBF 部件疲劳是 user 直接
  关心的工程问题；(b) 跨晶体结构（FCC/BCC/HCP）建模在医用合金（Ti6Al4V=HCP/BCC、
  CoCrMo=HCP、不锈钢=FCC）上覆盖广；(c) R²=0.932 + Basquin S-N 预测有实用意义。
  保留 Medium 的合理理由：ANN 是 incremental（非新颖架构），且单作者 + 期刊较新
  （Discover Materials 影响因子未稳定）。
- **摘要质量**：很好。具体输入特征（晶体结构、quasi-static、疲劳数据）+ 涵盖
  R-ratio、orientation、post-processing 条件 + 量化指标（R²、MSE）+ 验证形式
  （Basquin S-N 曲线）。
- **跟进**：**强烈建议**。机构权限取 PDF 后看：(a) 训练数据集来源与规模；
  (b) 输入特征工程的具体形式（多少维？如何编码晶体结构？）；(c) 是否包含
  Ti6Al4V 这类骨科常用合金；(d) 是否预测了多种 post-processing（HIP、热处理）
  下的疲劳差异——这对 user am_biomedical 工艺优化有直接借鉴。

## 评分系统反馈

priority=Medium 是边界判断——疲劳寿命 ML 预测在医用 LPBF 是真硬痛点，
**建议 scorer 在 LPBF + 疲劳 + 医用合金（Ti6Al4V/CoCrMo/SS316L）共现时优先级
上调**。本周报应记录这条 prompt 改进建议。
