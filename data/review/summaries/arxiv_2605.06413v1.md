# Decoupled PFNs: Identifiable Epistemic–Aleatoric Decomposition via Structured Synthetic Priors

- arXiv: 2605.06413v1（2026-05-07, stat.ML）
- 作者：Richard Bergna, Jose Miguel Hernández-Lobato（Cambridge）, Stefan Depeweg（Siemens AG）
- 方向归类：fea_surrogate（priority=Medium）—— **direction 偏，应为 ML/BO/UQ**

## 研究问题
**Prior-Fitted Networks (PFN)**（如 TabPFN, TabICL）通过对合成数据 meta-learning 实现 in-context Bayesian prediction。但默认 PFN 输出的是**观测层后验** p(y*|x*, D)，把 epistemic (latent signal 不确定性) 和 aleatoric (噪声) 混在一起。**BO/active learning 需要的是 epistemic**（可减少 by data），而 total predictive variance 会重复采高噪声点浪费 budget。**作者证明这种 epistemic/aleatoric 分离从纯 posterior predictive 上是 not identifiable 的**。

## 方法
**Decoupled PFN**：利用 PFN 的关键优势 —— **合成数据生成过程完全可控**：
1. 在合成 prior 中每个 task 包含**显式 latent signal f(x) 和 noise variance σ²(x)**
2. 训练时 generator 提供 query-level label 对两者
3. 用两个独立 head：latent-signal head + aleatoric head
4. 观测层 predictive 由 latent signal distribution **convolution** noise model 得到（推断时）
5. **acquisition 用 epistemic-only**（不用 total variance）

## 关键结果
- 缓解"总方差 exploration 失败"问题（noisy + heteroscedastic 设置）
- HPO（hyperparameter optimization）+ 合成 BO 上 decoupled 模型 ≥ tuned baseline；best average rank
- 在 LCB-style acquisition 上 epistemic 选点 vs total 选点的对比图清晰

## 与我研究方向的关联
- **fea_surrogate (弱相关)**：本文是**通用 BO / acquisition 设计**层面方法，对 PDE/FEM 无直接接口
- **可借鉴价值**：与 [[arxiv_2605.09775v1]] vvBO 互补 —— vvBO 处理 multi-output 结构化测量，本文处理 acquisition 中 epistemic-aleatoric 分解。两者在 FEM-in-the-loop BO 优化里都可用。
- 与本周其他 UQ 工作（B-PINN 理论、functional-prior B-PINN、normalizing flow VI）共同覆盖"epistemic vs aleatoric"主题。

## 局限
1. **依赖合成 prior 结构**：方法只在 latent + noise 结构已知的合成 task 上工作；现实问题难直接对应
2. **PFN 本身的 in-context length 限制**：context dataset 太大时 PFN 退化（这是所有 PFN 共病）
3. **HPO 和合成 BO benchmark 弱**：没工程 PDE / FEM 应用对照
4. **代码 / 数据**：未给链接
5. **Direction misclassified**：scorer 把它放 fea_surrogate 不准确

## 是否值得跟进
**Priority Medium 偏高，Low-Medium 更合理**。

- 对我研究主线**间接相关**，reference 收录足够。
- 跟进动作：reference。如未来做 BO + heteroscedastic noise + acquisition 设计才用上。

## 评分体系反馈
- Direction 应为 `ml_bo / uq`，不是 `fea_surrogate`。本周已出现多次 direction misclassification 信号。
- existing_summary 准确。无错。
