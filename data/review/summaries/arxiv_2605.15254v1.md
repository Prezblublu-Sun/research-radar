# Curriculum Learning of Physics-Informed Neural Networks based on Spatial Correlation (arxiv 版本)

- **id**: `arxiv:2605.15254v1` · 方向 fea_surrogate · 优先级 Medium · checked
- **来源**: arXiv 2605.15254, Tsinghua Automation, 2026-05-14（**W20**）
- **注**: **重复条目** —— 与上面 `https://openalex.org/W7161655141`（同一日同题论文）
  是同一研究。OpenAlex 那条没识别到 arxiv_id，fallback 到 OpenAlex URL；本条
  有完整 arxiv_id。两条 identity_key 不同，dedup 失效。

## 内容（基于正文确认）

- 作者 Xujia Chen 等 (Tsinghua Automation Dept)，发布 2026-05-14。
- 三个机制：(1) spatial causal weights（boundary → inward）；(2) low-frequency
  information bridge（pseudo-label cross-region consistency）；(3) region-adaptive
  reweighting。
- 代码开源：https://github.com/pigofmomo/CurriculumLearningPINN
- 验证：PDE benchmark，"comparable cost 下缓解 training failure"——具体数字
  需深入读，但摘要 + 引论与 OpenAlex 条目完全一致。
- AMS classification 包含 35Q68 (PDE applications)、68T07 (ML)、65M99/65N99
  (numerical PDE)——综合分类合理。

## 评分（与 OpenAlex 重复条目一致）

priority=Medium；novelty=medium（三个机制是有意义的组合，但每个单看不算 first-of-kind）；
pathway=adjacent（PINN 训练稳定性改善对生物力学 PINN 实操有借鉴）。

## 跟进

中。代码开源可直接试。但优先级排在 W21 GMM-curriculum-PINN 与 CMA-PINN 诊断之后。

## 评分 / dedup 系统反馈 ★

**确认了一类新的 dedup gap**：**同一 arxiv 论文在 corpus 中以两个 identity_key
存在**——其中一个来源（OpenAlex）没识别 arxiv_id，另一来源（arxiv 直接）识别了。

这与 W21 的 figshare `.v1` 重复**不同**——figshare 是版本化 DOI，本案例是
**跨源 ID 不一致**。修复路径不同：
- figshare：fetcher 层 namespace 规范化（ADR-0025）。
- 本案例：**OpenAlex fetcher 应解析 abstract / title / authors 来反查 arxiv_id**，
  补全 arxiv_id 字段。失败则 fallback 到现行 OpenAlex URL。

**建议补充 ADR-0026 草案**："OpenAlex 条目的 arxiv_id 回补"。
两组 dedup gap（figshare versioning + OpenAlex/arxiv cross-source）一起处理。
