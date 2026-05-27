# A spatially engineered multifunctional scaffold for bone tumor repair via stereolithography (.v1)

- **id**: `doi:10.6084/m9.figshare.32319710.v1` · 方向 am_biomedical · 优先级 Medium · checked
- **失败原因**: figshare DOI 404 + 是 `doi:10.6084/m9.figshare.32319710` 的版本化重复
  （内容判定见 concept-DOI 条目）
- **来源**: 2026-05-18（W21）

## 复核 + dedup gap 确认

**注意 existing_summary 与 concept-DOI 版本略有差异**：
- 这条 .v1 写"数值模拟验证力学匹配，未进行实验测试"
- 主 DOI 版写"力学测试、药物释放实验和细胞实验验证"

说明 figshare 的不同版本可能上传不同摘要/元数据，**不是完全相同条目**——这进一步
复杂化 dedup：是把两条都保留还是按 concept-DOI 合并？

## 评分系统反馈（强化版）★

本周已确认两组 figshare concept+version 重复条目（32345264 + .v1，32319710 + .v1）。
**建议升级为 ADR**：
1. 在 fetcher 层对 `10.6084/m9.figshare.*` 和 `10.5281/zenodo.*` DOI 做规范化：
   剥去 `.vN` 后缀作为 identity_key 主键，原 DOI 保留为副字段。
2. 摘要内容若两版差异 > 阈值（如 token Jaccard < 0.7），合并展示双版本摘要。
3. 不需要修改主 dedup 算法（DOI-only 严格保留），只在数据仓库 DOI 这个明确 namespace
   下做规范化——与 CLAUDE.md "DOI-only strict dedup, no fuzzy dedup" 不矛盾。

本周报应作为正式 backlog 入 TODO。
