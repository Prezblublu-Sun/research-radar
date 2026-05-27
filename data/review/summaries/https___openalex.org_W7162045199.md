# From Simple to Complex: Curriculum-Guided Physics-Informed Neural Networks via Gaussian Mixture Models

- **id**: `https://openalex.org/W7162045199` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link + 无 DOI / arxiv_id（fallback 到 OpenAlex URL 作 identity_key）
- **来源**: 2026-05-19（**W21**）

## 复核

- **方向**：正确。PINN + 课程学习 + 多尺度 PDE，fea_surrogate 核心。
- **优先级 Medium**：合理。技术增强类（GMM 拟合残差分布 + dynamic curriculum），
  对实际用 PINN 有用。
- **摘要质量**：好。具体技术（GMM、curriculum）+ 量化结果（97.8% L2 误差降低）+
  6 个 benchmark 数量。
- **跟进**：中。结合本周 CMA-PINN 诊断论文（doi:10.1016/j.cma.2026.119070）一起看：
  那篇说"异构约束削弱全局学习"，本篇用 curriculum 缓解，是同一痛点的两个视角。
  若做 PINN 工程实践，两者都需要。

## 评分系统反馈 — fallback identity_key 案例 ★

该条目没有 DOI 也没有 arxiv_id，identity_key 退到 OpenAlex URL，导致：
- `safe_id` 把 https:// 转成 `https___openalex.org_W7162045199`，文件名不雅观。
- 下次同一论文若被另一个 source（如后续 DOI 注册）拉到，会因 identity_key 不同
  造成 dedup 失效。

属于 ADR-0015 §4.4 "Papers with empty identity_key cannot be deduped" 的已知问题，
本周报应该把这种 fallback 情况单独统计——本周 288 papers 里"id-prefix=https"是
12 条，占 4.2%，可接受。
