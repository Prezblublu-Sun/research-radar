# IKNO: Infinite-order Kernel Neural Operators

- **id**: `arxiv:2605.22182v1` · 方向 fea_surrogate · 优先级 Medium · **read**
- **来源**: arXiv 2605.22182（preprint May 2026），NTU + A*STAR CFAR

## 研究问题

现有 neural operator（FNO、GINO、Transolver、GAOT 等）的 kernel integral 都只到
**一阶**，表达能力受限。作者预实验显示：在 Poisson-C-Sines 上，把 finite-order
kernel propagation 从 1 提升到 4，error 单调下降——暗示更高阶聚合更全局。能否
"穷尽到无穷阶"且保持可计算？

## 方法

**IKNO** 通过 infinite-order kernel integral 构造算子，关键是导出**闭式有限近似**：
- 形如 V_G = (I_M - α·K)^(-1) · K_GP · V_P，几何级数收敛到 resolvent 形式。
- 两个变体：
  - **IKNO-Vanilla**：在 product grid 上用 Kronecker eigendecomposition 算 full-kernel
    resolvent。
  - **IKNO-TP**：tensor-product，按各轴 resolvent 组合，隐式 functional regularization。
- 预处理成本从 O(N^3d) 降到 **O(d·N^3)**，挂钟时间几乎一致——大点云上可行。

架构：(i) NeRF-style positional encoding + MLP tokenization → (ii) Infinite Kernel
Encoding (point cloud → latent grid) → (iii) Latent Processor → (iv) Infinite Kernel
Decoding (grid → query points)。

## 关键结果

15 个 benchmark 上对比 GAOT（前 SOTA）、Transolver++、RIGNO 等：
- **时间无关**（6 个）：Elasticity、Poisson-Gauss、NACA0012/2412、RAE2822、Poisson-C-Sines
- **时间有关**（8 个）：NS-Gauss/PwC/SL/SVS、CE-Gauss/RP、Wave-Layer/C-Sines
- **工业规模**：NASA CRM（440K 空间点 × 105 训练样本 × 44 测试），预测压力 P 和摩擦系数 Cf

IKNO 在大多数 benchmark 上 SOTA，IKNO-TP 总体最强，IKNO-Vanilla 是非张量化的有竞争力的
替代。具体数字论文展开（表格中），整体趋势是"15 个里赢 12+"。

## 与我研究方向的关联

**对 fea_surrogate：直接相关，高方法学价值。**

1. **Elasticity benchmark 是 user 直接对接的物理**：irregular mesh + 中心孔的应力问题，
   就是孔周应力集中类的代理建模——髋臼杯/植入物孔周应力同类问题。可以把 IKNO
   当作 fea_surrogate 中"非规则网格 + 大点云"的新一代候选架构。
2. **无穷阶 = 更好的全局信息聚合**：对生物力学有意义——骨/植入物界面的应力传递
   本质上是远距离耦合（远场载荷影响局部接触压力），一阶 kernel 难以捕捉。
3. **NASA CRM (440K points × 105 samples) 体现"大几何 + 小样本" scaling**：
   患者特异 FEA 也是大网格 + 少量病例的场景。
4. **可与 Therm-FM 形成对照**：IKNO 主打"算子表达能力"，Therm-FM 主打"foundation
   model 预训练"。两条路线互补——IKNO 提供更强 backbone，Therm-FM 提供训练范式。

**对 hip_implant / am_biomedical**：间接相关。生物力学 FEA 工作流可考虑评估 IKNO。

## 局限

- 仍是 supervised learning，需要充分的 FEA ground truth 训练数据。
- α 的选择影响收敛：α 必须使 αK 谱半径 < 1（resolvent 收敛条件），论文用固定
  值，未系统化研究自适应 α。
- 对工业 CRM 的"105 训练 + 44 测试"是个小样本测试，泛化性还需更多工业 case 验证。
- 与 PDE foundation model 路线（Poseidon/DPOT/Therm-FM）相比，IKNO 仍是 per-task
  训练，没解决跨问题迁移。
- 论文公开数据但代码地址未见。

## 是否值得跟进

**值得**。建议：
1. 关注其代码开源进度，若有可用 PyTorch 实现，在 Elasticity benchmark 上跑一次对比
   实验是有价值的方向探索。
2. 把 IKNO 记入 fea_surrogate "架构候选"清单（与 Transolver++、GAOT、RIGNO 并列）。
3. 长期看：能否把 IKNO 的 infinite-order kernel 嵌入 PDE foundation model（如做
   IKNO + Poseidon 风格预训练）？这是一个明显的下一篇论文 idea。
