# Generative AI-guided in silico closed-loop optimisation of deposition morphology for 3D bioprinting applications (.v1)

- **id**: `doi:10.6084/m9.figshare.32345264.v1` · 方向 ai_bioprinting · 优先级 High · checked
- **失败原因**: figshare DOI 404；**且**这是上一条 `doi:10.6084/m9.figshare.32345264`
  的版本化 DOI（同标题同摘要）。

## 复核 + dedup gap 提示

- 内容判定与无 `.v1` 版本完全一致（同标题、同摘要、同方向、同优先级），见上一条
  的复核结论。本条不重复展开。

## 评分/dedup 系统反馈（重要）

**严格 DOI dedup 在 figshare 类版本化 DOI 上失效**——同一研究产生两个条目：
- `doi:10.6084/m9.figshare.32345264`（concept DOI）
- `doi:10.6084/m9.figshare.32345264.v1`（version DOI）

DataCite/figshare 规范上这两个 DOI 指向相同内容，前者总是指向最新版。CLAUDE.md
明确说"DOI-only 严格 dedup，不做模糊 dedup"——这个规则在期刊文章上是对的，但
figshare/Zenodo 类数据仓库会规律性产生这种"看起来不同但内容相同"的 DOI。

**轻量修复建议**（不破坏 ADR-0015 §4.4 first-seen-wins）：fetcher 层对
`10.6084/m9.figshare.*` 或 `10.5281/zenodo.*` 这类已知数据仓库 DOI 做 prefix
正规化（剥去 `.vN` 后缀作为 identity key），其他 DOI 不动。这不是模糊 dedup，
是版本化 DOI 的规范化。
