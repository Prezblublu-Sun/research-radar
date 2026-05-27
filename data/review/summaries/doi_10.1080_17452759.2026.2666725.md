# Laser powder bed fusion of NiTi ternary alloys: a review

- **id**: `doi:10.1080/17452759.2026.2666725` · 方向 am_biomedical · 优先级 Medium · **read**（255KB OA 全文 + 综述节选式阅读）
- **来源**: Virtual and Physical Prototyping, Vol 21 Iss 1, 2026-05-18（**W21**）
- **作者**: Abdelhady（Twente）+ Biffi（CNR Lecco）+ Molotnikov（RMIT）+ Vaneker / Gibson /
  Mehrpouya（Twente，通讯）

## 研究问题

NiTi（Nitinol）是形状记忆合金（SMA），高耐腐蚀 + 优延展 + 加工硬化 → 医疗器械
（尤其支架 stents）、航空航天致动器/变形结构核心材料。但传统加工方法（铸造、
冷轧）几何受限。**LPBF 能造复杂几何 + 精确控制合金化学和微观结构**——过去十
年研究焦点在 binary NiTi 工艺优化和热弹行为，但 feedstock/工艺敏感性大。
**三元合金化（Hf, Cu, Nb, Fe）** 是进一步提升性能的方向。本综述系统梳理。

## 主要内容（基于章节结构）

1. **第 2.1**：LPBF 工艺通则（粒度、扫描参数、能量密度）。
2. **第 2.2**：Binary NiTi 的 LPBF 现状基线。
3. **第 2.3**：四种三元体系的可打印性
   - 2.3.1 NiTi-**Hf**：相变温度可提升到 **300°C**（高温 SMA 应用，超出 Nitinol 常规）。
   - 2.3.2 NiTi-**Cu**：相稳定性 + 热循环能力提升。
   - 2.3.3 NiTi-**Nb**：力学性能提升（屈服强度、平台应变）；**Nb 也提升生物兼容性**
     （bioavailability of Nb，行 2230）。
   - 2.3.4 其他 NiTi-X（Fe 等）。
4. **第 2.4**：LPBFed 部件微观结构评估（cellular grains、(Ti,Hf)₂Ni 析出等）。
5. **结论**（位置较后）。

## 与我研究方向的关联

**对 am_biomedical：直接相关，方向核心综述。**

- NiTi LPBF 在医疗领域的应用集中在**支架（stents）**（行 607），**多孔结构控孔隙
  率改善生物兼容性 + 力学**（行 616-618）也明确点到。
- "NiTi-based 合金特别在生物医学领域的应用变得 [重要]" —— 行 626 直接说明。
- **NiTi-Nb 的生物兼容性提升**（行 2230）是 user am_biomedical 方向有价值的线索：
  Nb 添加可能让 NiTi 在骨科植入物中比 Ti6Al4V 更有竞争力（NiTi 超弹性 + Nb
  生物兼容）。
- 与上面 Usman Ali 的 ML 疲劳预测论文搭配：那篇要"晶体结构 FCC/BCC/HCP"，NiTi
  是 B2/B19' 体系（intermetallic ordered lattice），是本文系列的延伸方向。

**对 hip_implant**：间接但有潜力。NiTi 超弹性可缓解应力屏蔽（user 核心痛点），
理论上比 Ti6Al4V 更接近骨弹性模量——但临床上 Ni 离子释放仍是顾虑。本综述提供了
LPBF NiTi-X 微观结构调控的工具书。

**对 fea_surrogate / ai_bioprinting**：弱关联。

## 局限（本综述自身）

- 综述范围限定 LPBF + 三元合金。未涵盖其他 AM（EBM、DED）或四元合金。
- 生物医学性能（疲劳 / 长期生物相容性 / 骨整合）只是顺带提及，深度有限——
  本综述更偏材料学/工艺学，少临床数据。
- 缺定量综合表（如所有 LPBF NiTi-X 工艺参数对比表）——这种综述工具表对工程
  实践极有价值，希望作者补充。

## 是否值得跟进

**强烈建议跟进**——am_biomedical 方向的核心综述。建议：
1. **下载 PDF 收入文献库**作为 NiTi LPBF 方向背景文献。
2. 若 user 后续考虑 NiTi 用于骨科植入物，本文是"工艺基线 + 三元合金选型"的
   一站式参考。
3. 关注作者 Mehrshad Mehrpouya（Twente）实验室的后续工作。

## 评分系统反馈

priority=Medium 合理（综述类约定）。如本周报建议——主题与 user 80%+ 重合的综述
可考虑上调到 High。本文与 cis.2026.103949（多孔钛表面综述）是本周两篇极对口
综述，可在周报中作为"本周综述精选"专门提。
