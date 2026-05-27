# Elicitation-Augmented Bayesian Optimization (OpenAlex duplicate)

- **id**: `https://openalex.org/W7161204841` · 方向 fea_surrogate · 优先级 Medium · checked
- **失败原因**: no_open_access_link, no DOI/arxiv (OpenAlex fallback)
- **来源**: 2026-05-12（**W20**）

## ★ 第二组跨源重复 — 强化 ADR-0026 草案需求

**与 `arxiv:2605.12079v1` 是同一论文**（同标题 "Elicitation-Augmented Bayesian
Optimization"，同期，同方向）。本条由 OpenAlex 索引但未识别 arxiv_id，fallback
到 OpenAlex URL；前一条由 arxiv 直接索引带 arxiv_id。**dedup 失败原因与之前
arxiv:2605.15254v1 vs https://openalex.org/W7161655141（Curriculum Learning PINN）
完全相同**。

本周两组同类跨源重复 + W21 两组 figshare 版本重复 = **dedup 系统在两个不同
namespace 都有规律性失效**。

## 复核

内容判定见 arxiv:2605.12079v1 条目。两条 existing_summary 内容一致（一处细微
"成本感知" wording 差异）。

## ADR-0026 草案优先级提升 ★

W20 又出现一组同类跨源重复（pairwise comparison BO），加上 W20 之前的
Curriculum-PINN 重复，**两周累计 2 组跨源重复 + 2 组 figshare 重复 = 4 组**。
**ADR-0026（OpenAlex arxiv_id 回补）的紧迫性提升**——单一 ADR-0025（figshare
namespace 规范化）不足以覆盖所有 dedup gap。
