# Uncertainty Quantification for Cardiac Shape Reconstruction with DeepSDF via MCMC

- arXiv: 2605.07987v1（2026-05-08, eess.IV）
- 作者：Jan Verhülsdonk（Bonn）, Thomas Grandits（Graz）, Francisco Sahli Costabal（PUC Chile）, Thomas Beiert（UKB Bonn）, Simone Pezzuto（Trento + USI）, Alexander Effland（Bonn）
- 方向归类：fea_surrogate（priority=Medium）
- 投：IEEE Transactions on Biomedical Engineering
- 资助：DFG CRC 1720, EXC 2047/2151, SNSF "CardioTwin", CSCS Swiss Supercomputing

## 研究问题
Cardiac atlas-based shape reconstruction（用 MRI/CT/电解剖图重建左右心室）通常给出 deterministic point estimate，**不量化稀疏 / 噪声输入下的不确定性**，临床可靠性差。本文目标：在 DeepSDF（implicit shape via zero-level set of NN）的隐变量空间中做 Bayesian 推断 + MCMC 采样，得到 MAP + 后验分布。

## 方法
1. **DeepSDF Atlas**：训 NN f_θ 将 (x, z) 映射到 4 个 signed distance（LV/RV endo/epi），每个 patient 一个 latent code z_i ∈ R^d；训练 loss 含数据 fit + zero-mean Gaussian prior + Lipschitz regularization（softplus(c_i) ≥ ‖W_i‖_p）。
2. **MCMC 在 latent space**：用 HMC / NUTS 在 latent z 上采样；prior 是 Gaussian inferred from training latent codes；likelihood 来自 reconstruction loss。输出 MAP shape + posterior ensemble。
3. **同时建模 LV+RV endo/epi 四个表面**：multi-surface formulation。

## 关键结果
- 在公开 cardiac dataset 上做实验
- **accurate reconstructions + well-calibrated uncertainty**
- 是 DeepSDF 类 cardiac shape modeling **第一个 UQ framework**（作者明示）

## 与我研究方向的关联
- **fea_surrogate（弱相关）**：本文严格说是**医学影像 + DeepSDF UQ**，不是 FEM 代理。但与"CardioTwin" digital twin 项目（[[arxiv_2605.12544v1]] DCP-INN 是同一愿景的下游）相邻。
- **可借鉴方法学**：
  - **"latent-space MCMC for UQ"** 模板对任何 implicit representation（NeRF/SIREN/DeepSDF）都适用 —— 包括我可能用到的 3D microstructure 表征。
  - **Lipschitz-bounded DeepSDF** 是好的工程实践（避免 SDF 不连续 artifact）。
- 与本周其他 UQ 工作（[[arxiv_2605.08672v1]] B-PINN 理论, [[arxiv_2605.07060v2]] functional-prior B-PINN, [[arxiv_2605.09718v1]] normalizing flow VI）共享 "Bayesian latent inference" 主题。

## 局限
1. **eess.IV 不是 fea_surrogate**：scorer 把它归到 fea_surrogate 不太对，应归到 medical imaging + UQ。
2. **HMC 在高维 latent space 仍计算昂贵**：未给具体推断时长。
3. **没有对比 deep ensemble 或 normalizing-flow VI 等更轻量的 UQ 方法**。
4. **公开 cardiac dataset 规模未明示**；out-of-distribution 性能没强 evidence。
5. **代码 / 数据 链接未给**。

## 是否值得跟进
**Priority Medium 偏高，Low 更合理**。

- 对我研究主线**无直接价值**；与心血管 imaging 社群相关，不是 FEM 代理。
- **跟进动作**：仅做 reference。如果未来需要"latent-space MCMC for shape UQ"模板，可以借鉴。

## 评分体系反馈
- **Direction `fea_surrogate` 不准确**：本文严格来说是 medical_imaging + UQ。本周共出现至少两篇 cardiac/血管相关论文（[[arxiv_2605.12544v1]] DCP-INN 也是血管血流）—— 可考虑给 scorer 加一个独立的 "cardio_imaging" 子方向。
- existing_summary 准确，无修正。
