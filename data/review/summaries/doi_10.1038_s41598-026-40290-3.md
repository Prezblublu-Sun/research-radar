# Physics-Informed Neural Networks for Predicting Laser-Tissue Interaction in Maxillofacial Reconstruction Surgery

- DOI: 10.1038/s41598-026-40290-3（Scientific Reports 2026）
- 作者：Mohamed E. Yahia（Abu Dhabi Polytechnic）, Alireza Abdikian, Hasti Abdolrasuli（Malayer U., Iran）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
颌面外科激光手术（CO₂, Nd:YAG, Er:YAG, Diode 不同波长）下生物组织热动力学预测；传统数值方法昂贵。用 PINN 嵌入**热传导 + 辐射输运方程**做快速代理。

## 方法
- **3 隐层 PINN**, 50 neuron/layer, Tanh activation
- 嵌入热传输 + 辐射传输 PDE 残差到 loss
- 仅 1D 模型

## 关键结果
- vs analytical solution: final MSE 1.27 × 10⁻⁶
- 4 种激光的 thermal penetration depth：CO₂ 0.11mm, Nd:YAG 0.077mm, Er:YAG 0.063mm, Diode 0.055mm
- 不同年龄组（青少年 vs 老年）吸收系数差异导致 penetration 不同
- 识别 coagulation / vaporization / irreversible damage 阈值

## 与我研究方向的关联
**fea_surrogate (弱-中相关)**：
- 应用是激光-组织相互作用（医学激光物理），非我主线
- **方法仅 incremental**：标准 PINN 套到 1D 热-辐射方程
- 仅与 analytical 解对比、**无实验验证**（作者明示 future work）

## 局限
1. **1D 模型**：实际颌面手术是 3D 复杂几何
2. **未实验验证**：仅对 analytical 解 toy benchmark
3. **PINN 架构未优化**：3 层 50 神经元是非常基础的设置
4. **没有新的方法学贡献**：将已有 PINN 应用到新场景

## 是否值得跟进
**Priority Medium 略高，Low 更合理**。

- Scientific Reports 是 generalist journal，质量参差；本文偏 application + 标准 PINN 应用
- 与本周更强的 PINN 工作（DCP-INN, AdamFLIP, FVM-PINN, B-PINN theory）相比贡献弱
- **跟进动作**：仅 reference 收录。

## 评分体系反馈
- Direction 应为 `biomedical_pinn`；当前 `fea_surrogate` 偏。
- existing_summary 准确（PINN、热传导、激光、解析对比、无实验）。无错。
