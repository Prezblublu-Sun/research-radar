# 复核：W7161090235 — Posterior Concentration of Bayesian PINNs for Elliptic PDEs

- OpenAlex W7161090235，pdf_found=false（no_open_access_link）
- 方向归类：fea_surrogate（priority=Medium）

## 关键判断：与 arxiv:2605.08672v1 的关系
**这是同一篇论文的 OpenAlex 入口。** 标题逐字相同；同一篇 Zhao & Lu (UMN, ICML 2026) 论文。详细总结见 [[arxiv_2605.08672v1]]，已做完整精读。

**去重缺口（与本周 [[https___openalex.org_W7161090206]] 同源）**：arXiv preprint 通常无 DOI，OpenAlex 入口 dedup 自然漏掉；不是 bug。

## 摘要 / Priority 复核
existing_summary 与 arXiv 版完全一致，描述准确。Priority Medium 合理（纯理论 ICML 文章，对工程实践影响有限）。

## 处置
checked。本条不再单独跟进；merge 到 [[arxiv_2605.08672v1]]。

## 评分体系反馈
**本周 [[https___openalex.org_W7161090206]] vvBO 重复 + 本条 B-PINN 重复，是同一类 dedup 边界 case**，建议：
- 短期：在 weekly 报告阶段做一次 title-similarity audit（Levenshtein < 0.05 即合并）
- 长期：考虑给 arXiv preprint 增加伪 DOI 形式（如 `arxiv:2605.08672` 转 `doi:10.48550/arXiv.2605.08672`）使得 OpenAlex 与 arXiv 入口自动合并 —— 这是 [[ADR-0025]] figshare/zenodo version DOI normalization 的相邻问题。
