# Reduced-Order Modeling of Parameterized Visco-Plastic Shallow Flows (TROM)

- arXiv: 2605.06526v1（2026-05-07, physics.flu-dyn）
- 作者：Md Rezwan Bin Mizan, Ilya Timofeyev, Maxim Olshanskii（University of Houston, Math Dept）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
**Visco-plastic shallow free-surface flow**（Herschel-Bulkley fluid，2D shallow water）描述泥石流、岩浆流、浆料、糊状物等；强非线性 + 非光滑 rheology + 移动 yield surface + plug region 让 ROM 极困难。Newtonian fluid ROM (POD / 操作 inference) 经过数十年开发，**non-Newtonian visco-plastic ROM 文献稀少**。

## 方法
**TROM (Tensorial ROM)**：
1. 非侵入式 ROM，用 **HOSVD（Higher-Order SVD）**做 low-rank tensor decomposition
2. **Offline 阶段**：在 structured parameter grid 上算 snapshot，HOSVD 提取 space/time/parameter 三个维度的 dominant mode
3. **Online 阶段**：新参数下在 tensor low-rank 格式中插值 + truncated SVD 编码 → multilinear 解码恢复 (space, time) 解轨迹；**无需解 reduced dynamical system**（不像 Galerkin projection ROM）
4. 可解读为 encoder-decoder：HOSVD = nonlinear encoder + multilinear decoder

## 关键结果
- 在 dam-break + topography 多参数下准确捕获 front propagation、plug/shear region、stopping dynamics
- 显著计算加速 vs full-order simulation（具体数字在论文中后部）

## 与我研究方向的关联
- **fea_surrogate（中等相关）**：非牛顿 ROM 与生物打印中**水凝胶 / 糊状物 extrusion** 直接相关 —— 我未来如要做 bioprinting fluid dynamics surrogate，本文方法 transferable。
- TROM 思路与 [[arxiv_2605.07738v1]] EquiNO 的"POD-DeepONet"理念一致，但用 HOSVD 替 POD（多维参数空间更适合 tensor）。

## 局限
1. **要求 structured parameter grid**：不能用 LHS / 随机采样
2. **仅 demo 2D shallow flow**：3D full Navier-Stokes 非牛顿没验证
3. **HOSVD scalability**：参数维度过高时 tensor 尺寸爆炸
4. **代码 / 数据**：未给链接

## 是否值得跟进
**Priority Medium 合理**。

- 对生物打印 fluid dynamics 子方向 transferable，但不是当前主线工作。
- Reference 收录。

## 评分体系反馈
- Direction 正确（fea_surrogate）。existing_summary 准确。无错。
