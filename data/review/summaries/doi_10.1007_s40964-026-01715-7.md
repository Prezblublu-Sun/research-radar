# Complex estimation of mechanical properties of SLM-printed gyroid AlSi10Mg structures: experimental and FE analysis

- **id**: `doi:10.1007/s40964-026-01715-7` · 方向 am_biomedical · 优先级 High · **read**（精读引论 + 摘要）
- **来源**: Progress in Additive Manufacturing, 2026-05-12（**W20**），Czech Tech University Prague

## ★ am_biomedical High，直接对接 user

SLM gyroid AlSi10Mg + 实验 + FE。**am_biomedical 方向的"工艺-性能-FEA 三件套"
标杆**——与 user 髋柄 SLM Ti6Al4V 工作流的方法学几乎完全同构（只是合金不同）。

## 研究问题

Gyroid TPMS 结构因连续曲率 + 非线性，传统结构/晶格结构的 FEA 方法不准。需要
"complex FE methods"才能准确评估。同时打印方向 + 体积分数 + 工艺影响显著。

## 方法

- SLM 3D 打印 + 多个打印方向 + 多个体积分数。
- 复杂 FE 方法（具体方法在正文展开）。
- 实验：拉伸 + 压缩 + 表面粗糙度（后处理前后）。

## 关键结果

- 提出**实验验证过的 FE 方法**，可准确预测不同体积分数下的力学性能。
- 基于实验数据，**导出预测方程**给任意体积分数预测 gyroid 性能。
- 打印方向各向异性 + 体积分数效应量化。

## 与我研究方向的关联

**对 am_biomedical：直接相关**。
- Gyroid TPMS 是骨整合段常用结构（与 W21 IWP/Primitive、本周 ijfatigue TPMS 同
  cluster）。
- AlSi10Mg 是航空合金，**但方法学完全可平移到 Ti6Al4V 髋柄 gyroid 段**。
- 预测方程对工程设计极有价值——免去每次设计变更都跑 FEA。

**对 hip_implant**：间接但有借鉴。

## 局限

- AlSi10Mg 不是医用合金，user 直接迁移需独立 Ti6Al4V 验证。
- "Complex FE methods" 具体细节需深入读。
- 单一 gyroid 几何，未对比 IWP/Primitive 等其他 TPMS 家族。

## 是否值得跟进

**值得（中-高）**。建议：
1. **优先取 PDF**，关注：(a) "complex FE methods"具体什么——是 nonlinear / contact /
   微观结构 embedded？(b) 预测方程的具体形式（参数化经验公式 vs 解析）。
2. 与 W21 jmbbm 径向梯度 SS lattice、本周 ijfatigue TPMS 疲劳、IMechE TPMS
   设计、ma19102092 NiTi 超弹性一起构成 am_biomedical "TPMS/晶格 工艺-力学"
   trend cluster。
3. 思考：若把 Ti6Al4V gyroid 髋柄段 + 本文方法做一遍，是非常直接的论文 idea。

## 评分

priority=High 合理。novelty=medium（complex FE methods 是工程实践，非新方法），
pathway=direct（同 SLM 工艺 + 同结构家族，方法可直接借鉴）。

W20 am_biomedical High 命中 2 篇（本文 + ijfatigue TPMS 疲劳）—— scorer 对该
方向 High 识别良好。
