# Additively manufactured radially graded stainless steel lattices for structural biomedical applications

- **id**: `doi:10.1016/j.jmbbm.2026.107404`
- **方向**: am_biomedical
- **优先级**: High（pipeline 评分）
- **本次处理**: checked（PDF 不可获取：no_open_access_link，JMBBM Elsevier 期刊无 OA 副本）
- **来源日期**: 2026-06-01（未来日期预印本）

## 复核结论

**方向归类**：正确。LPBF + D-TPMS 径向梯度晶格 + 应力屏蔽降低，明确属
am_biomedical（增材制造生物医学材料）。其方法本身（径向壁厚梯度的 TPMS 设计）
也是 hip_implant 方向的相邻技术——可考虑加 hip_implant 二级方向（routing 单 direction
未必能反映这种跨方向相关性，但 hip_implant 不是其首要应用）。

**优先级 High**：判定合理。理由：
1. 「径向梯度 D-TPMS + 不锈钢 LPBF + 同时降低 E 且保持 σy」是 am_biomedical
   核心三件套，每一项单独都够 High。
2. 同时跑有限元 + 压缩实验，方法学完整。
3. 「与皮质骨相当的屈服强度」是关键临床表述，意味着可考虑承重植入。

**摘要质量**：高质量。motivation 直接点出应力屏蔽（user 核心痛点）；method 完整
（LPBF + 径向梯度 + D-TPMS 三要素都齐）；result 给了关键比较基准（vs 皮质骨）；
validation 双轨（FEA + 实验）。无幻觉。

**摘要可改进点**：未给出具体壁厚梯度范围（如 0.3mm→0.6mm）、未报告 E 降幅
（如 50% 等），但这属于摘要详略权衡，非错误。

**是否值得跟进**：是，**高优先级**。理由：
- 与 fea_surrogate 方向有交集：径向梯度 TPMS 的 unit cell 力学是典型代理建模问题。
- 与 hip_implant 方向有交集：径向梯度策略可借鉴到髋柄外层/骨界面段设计。
- 不锈钢 vs 钛合金的弹性匹配差异本身是个独立可比研究问题。

待下次手动找 PDF（机构权限）。读 PDF 时优先看：(a) 径向梯度的解析函数 vs 离散
分段；(b) LPBF 工艺约束如何影响梯度可制造性；(c) FEA 边界条件是否对应到髋柄/
脊柱植入物典型加载。

## 抓取失败说明

- 失败原因：`no_open_access_link` —— Unpaywall 未返回可用 PDF URL。
- 不必重试。
