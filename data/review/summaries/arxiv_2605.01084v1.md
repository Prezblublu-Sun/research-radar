# OsteoOpt++: Patient-Specific Optimization for Mandibular Reconstruction Planning with Enhanced Bone Union

- arXiv: 2605.01084v1（2026-05-01, cs.CV）
- 作者：Hamidreza Aftabi et al.（UBC + U. Toronto Sunnybrook + Medical U. of Vienna）
- 方向归类：ai_bioprinting（priority=High）
- **代码开源**：https://github.com/hamidreza-aftabi/OsteoOpt

## 研究问题
下颌骨切除重建（vascularized bone graft）的**供体-宿主 nonunion** 是临床主要并发症（37% 率）。现有 virtual surgical planning (VSP) 输出**几何方案**（donor-to-contour shape matching），但**两个 visually 同样的方案可能产生完全不同的 donor-host 接触 / union 条件**。临床缺一个 image-to-decision pipeline：把 CT 转成可优化的目标 + 系统搜索可控变量。

## 方法
**OsteoOpt++** = image-to-decision Bayesian optimization loop：

1. **个性化 digital twin 构造**：术前 CT → template-to-patient registration + CT-derived muscle/TMJ 参数 update → patient-specific FE 模型
2. **可控变量**：6 个 clinically controllable cut-plane orientation + donor-positioning 参数
3. **目标函数**：
   - apposition-driven（最大化 donor-mandible 接触）
   - safety-factor-regularized variant（兼顾力学安全性）
4. **Bayesian optimization with EI+ (expected-improvement-plus) acquisition**
5. **Longitudinal validation**：day-5 post-op CT 重建 surgeon-implemented baseline；year-1 post-op CT 作 ground truth 验证

## 关键结果
**Generic cases（body / symphysis / ramus-body 三种典型缺损）**：
- vs 常规手术：cycle-averaged apposition +29 percentage points
- **329% 相对改进**（这是大字号 headline）

**Patient-specific cases（4 个真实病例，3 优化 + 1 validation）**：
- vs day-5 post-op 实际配置：apposition +26 percentage points

**Sensitivity analysis**：11 个建模参数 ±10% 扰动 → 目标函数变化 ≤3% (generic) / ≤4% (patient-specific)

**Longitudinal validation**：predicted apposition vs year-1 实际骨形成 **Dice 0.70 / 0.76** —— 这是少见的"术前预测 vs 一年后真实结果"对照，说服力强。

## 与我研究方向的关联
**ai_bioprinting（直接相关）**：
- **Aftabi 团队 OsteoOpt line of work** 是 craniofacial 重建 + BO + digital twin 的活跃 thread，前作 [Aftabi 2024a/b, 2025a/b] 都值得追读
- "image → physics-based DT → BO → 可控手术变量"是 ai_bioprinting / 个性化植入物方向的范式参考
- 与本周已读 [[doi_10.1016_j.jconrel.2026.114983]] (AI-guided bioprinting for diabetic ulcer) + W19 [[arxiv_2605.09362v1]] FrameTwin (sparse-view DT for printing control) 形成"individual-specific DT + 优化反馈"集群
- **代码开源**是大加分项；可作为我未来"个性化骨科植入物 + AI 设计"工作的 reference architecture

## 局限
1. **仅 4 个真实病例**（3 优化 + 1 longitudinal validation）：临床证据偏少；prospective trial 是 future work
2. **目标函数是 apposition**：与"实际 bone union"是 surrogate 关系；Dice 0.70-0.76 显示尚有 gap
3. **6 个 design variable 较少**：实际手术决策空间更大（plate 选择、固定方案等）
4. **BO 在 6D 空间是 manageable**，但 EI+ 与 trust region BO 等 modern variant 的对比未给

## 是否值得跟进
**Priority High 完全合理**：
- 极少数同时满足"严肃临床问题 + 完整 image-to-decision pipeline + 代码开源 + longitudinal validation"的工作
- **跟进动作**：
  1. clone OsteoOpt repo
  2. 追读 Aftabi 2024/2025 series（craniofacial 重建 BO line of work）
  3. 作为我未来"个性化骨科 implant + BO"工作的 anchor paper

## 评分体系反馈
Direction 正确，priority High 合理（临床应用 + 代码开源 + longitudinal validation）。existing_summary 准确，包含 329% / Dice 0.76 关键数字。
