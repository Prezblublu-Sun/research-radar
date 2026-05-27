# Robust Foundation Model for Conservation Laws: Context-Injected Flux Neural Operators via Recurrent ViT

- arXiv: 2605.05488v1（2026-05-06）
- 方向归类：fea_surrogate（priority=Medium）

## 研究问题
神经算子在**未见过的守恒律**（不同 flux function）上泛化失败；需要 foundation-style model 处理多类守恒系统。

## 方法
- **循环 ViT** 作为上下文编码器，从 demonstration 中提取 conservation law / flux function 信息
- **超网络（hypernetwork）** 生成 conditional Flux Neural Operator 参数
- Train on multiple 守恒律 task family

## 关键结果
- 跨多种守恒系统保持 Flux NO 的 robustness + long-term prediction
- 在未见 flux function 上泛化

## 与我研究方向的关联
**fea_surrogate（相关）**：foundation model 趋势对 PDE surrogate 是 long-term direction。可作为本周 SpectraNet/CATO 等专门 PDE 算子的对比 baseline。但当前应用偏 fluid / generic conservation law，非工程 FEM。reference 级。

## 评分体系反馈
Direction 正确。existing_summary 准确。
