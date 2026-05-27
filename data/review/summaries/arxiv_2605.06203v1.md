# Adaptive Coordinate Transforms for Neural Operators (ACT)

- arXiv: 2605.06203v1（2026-05-07, cs.CE）
- 作者：Chaoyu Liu, Zhonghao Li（共同一作）等；**Cambridge DAMTP + HIT Shenzhen + HK PolyU**；通讯 cl920@cam.ac.uk；senior author Carola-Bibiane Schönlieb
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
神经算子（FNO, CNextU, Transolver）多数建立在**固定 Eulerian 坐标系**，与演化的物理结构（传播波、移动 vortex）spatially misaligned ⟹ 算子映射不必要地非局部 + 偏好平滑（spectral bias）⟹ 模糊 shock / sharp transition。**经典 PDE 数值方法**用 ALE / moving mesh 等自适应坐标变换处理这个问题；本文目标：把这种"自适应坐标"思想做成可插拔的神经算子模块。

## 方法
**ACT (Adaptive Coordinate Transform) block**：plug-and-play module，**逐层**插入 FNO / CNextU / Transolver backbone：

1. 给定 feature map x，ACT block 预测 **coordinate adjustment field**（local offset）
2. 用 **differentiable sampling**（类似 Spatial Transformer Networks）按变换后的坐标重采样 feature
3. **Residual connection**：输出 = 原 feature + 重采样 feature（保 stability）
4. 重要的"**autonomous role decoupling**"现象：
   - **中间层 ACT**：作为 "progressive spatial tracker"，对齐 latent space 中的演化结构
   - **末层 ACT**：作为 "regularity modulator"，通过 implicit local coordinate compression + Jacobian multiplier **放大空间梯度**，抵消 smoothness preference 恢复 sharp transitions

## 关键结果
- 在多个 PDE benchmark + 三种 backbone（FNO, CNextU, Transolver）上一致提升精度
- 揭示 ACT block 自动学到不同 "role"（spatial tracker vs regularity modulator）

## 与我研究方向的关联
- **fea_surrogate（强相关）**：
  - **与 [[arxiv_2605.09016v1]] CATO 直接对比**：CATO 学一个**全局**的 chart Φ_chart 在 attention 前；ACT 是**逐层 local** 坐标变换 + 多个 backbone 兼容。CATO 是 "single transformation for whole network"，ACT 是 "distributed transformations per layer"。两个 design 都各有所长。
  - **与本周整体 trend 呼应**：CATO + ACT + HS-FNO（time-axis）+ SpectraNet（residual + multi-scale）共同指向"**inductive bias > loss function tricks**"的设计哲学。
- **方法学价值**：differentiable sampling 模块 + role decoupling 现象是 transferable 设计模式。

## 局限
1. **未在主文中给出 absolute 数字**（abstract 只说 "consistent and significant improvements"）—— 需要看 Section 4 实验表才能判断量级
2. **ACT block 自身参数开销 + 额外重采样成本**未量化
3. **可能与 CATO 的 chart 学习有 overlap**：作者引用 [Hu et al., 2024] 但未与 CATO 在同一 benchmark 直接对照
4. **3D / 不规则几何应用未提**：仅讨论 fixed Eulerian → 自适应；非结构网格未讨论
5. **代码 / 数据**：未给链接

## 是否值得跟进
**Priority Medium 合理**：

- Cambridge DAMTP + Schönlieb 团队 = 高 quality 信号
- 方法 incremental 但概念清晰；与 CATO 形成 design space 探索
- **跟进动作**：等正式版本（有完整 results table）；如未来用 FNO / Transolver 做 surrogate，把 ACT 当作 layer-wise plugin

## 评分体系反馈
- Direction 正确。Priority Medium 合理。
- existing_summary 准确（自适应坐标变换、可微采样、多 backbone 一致提升）。无错。
