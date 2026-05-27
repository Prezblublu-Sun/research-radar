# ADR-0025: figshare / Zenodo 版本化 DOI 的 identity_key 规范化

**Status**: Draft（提案；尚未实施；不要在确认前修改 fetcher 或 ADR-0015）
**Date**: 2026-05-26
**Related**: ADR-0015 §4.4（identity_key, DOI-only strict dedup），
CLAUDE.md §4（"DOI-only 严格 dedup，不做模糊 dedup"），W21 pilot 周报 §5.2

## Context — pilot 信号

2026-W21 精读 pilot 出现两组**同一研究在 corpus 中以两个不同 identity_key
存在**的样本：

| 样本 | concept DOI | version DOI |
|---|---|---|
| Bioprinting β-CVAE | `doi:10.6084/m9.figshare.32345264` | `doi:10.6084/m9.figshare.32345264.v1` |
| 骨肿瘤 SLA 多功能支架 | `doi:10.6084/m9.figshare.32319710` | `doi:10.6084/m9.figshare.32319710.v1` |

两条**严格 DOI 字符串不相等**，所以 ADR-0015 §4.4 的 `identity_key(p)` 把它们
当作不同 paper；strict dedup 不去重。结果：

- 一个研究在 daily JSON / weekly report 里出现两次（精读循环也跑两次，浪费）。
- 两个版本的元数据可能略有不同（W21 pilot 中第二组的两版 existing_summary
  在"验证"部分描述就不一致），混淆 user 的判断。

## DataCite / figshare 的版本化 DOI 语义

figshare / Zenodo 等数据仓库为每次上传产生：

- **Concept DOI**（如 `10.6084/m9.figshare.32345264`）：永久指向"最新版本"。
- **Version DOIs**（如 `...32345264.v1`, `.v2`, ...）：永久指向"特定版本"。

DataCite 元数据规范上：concept DOI 通过 `IsVersionOf` / `HasVersion` 关系明确
关联 version DOIs。**两者在学术意义上是同一研究，不是不同 paper**。

OpenAlex 偶尔会同时索引 concept 和 version——这是上游数据源的行为，不是
Radar 的 router/fetcher 问题。

## 与 CLAUDE.md §4 "DOI-only 严格 dedup，不做模糊 dedup" 的关系

CLAUDE.md 明确：

> DOI-only 严格 dedup。**不做模糊 dedup——太多边界情况**。

本提案**不违反此原则**，因为：

- 模糊 dedup = 不同 DOI 字符串 → 启发式判定可能相同 → 容易出错。
- 版本化 DOI 规范化 = 同 namespace (`10.6084/m9.figshare.*` 或
  `10.5281/zenodo.*`) 内剥去 `.vN` 后缀 → **DataCite 规范明确指向同一研究**。

这是**namespace-aware DOI canonicalization**，不是模糊匹配。等价于把
`HTTPS://doi.org/10.x` 和 `http://doi.org/10.x` 视为同一 DOI——大小写/scheme
不应当成不同 paper。

## 提案

在 fetcher 层加一个 `_canonicalize_doi(doi)` 函数，**在 identity_key 构造之前**
被调用。规则**仅对已知数据仓库 namespace 生效**：

```python
_VERSION_SUFFIX_RE = re.compile(r"\.v\d+$")

_REPOSITORY_PREFIXES = (
    "10.6084/m9.figshare.",   # figshare
    "10.5281/zenodo.",         # Zenodo
    # 未来视情况追加 OSF / Dryad 等
)

def canonicalize_doi(doi: str) -> str:
    """对已知数据仓库的版本化 DOI 剥去 .vN 后缀。其他 DOI 原样返回。
    保留原 DOI 到 `raw_doi` 字段以便审计。"""
    if not doi:
        return doi
    low = doi.lower()
    if any(low.startswith(p) for p in _REPOSITORY_PREFIXES):
        return _VERSION_SUFFIX_RE.sub("", doi)
    return doi
```

数据模型增量（v2 schema 兼容）：

- `doi`: 规范化后的 DOI（即 identity_key 用的）
- `raw_doi`: 上游原 DOI（仅当 `doi != raw_doi` 时写入；可选字段）

`pipeline/v2_schema.identity_key(p)` **不变**——还是读 `p["doi"]`，但读到的
已经是规范化值。**不需要改 dedup 算法本身**。

## 数据迁移（一次性）

现有 v2 corpus 里已经存在的版本化 figshare DOI 条目：

- 全量扫描 `data/daily/*.json` 和 `data/historical/*` 中匹配
  `10.(6084/m9.figshare|5281/zenodo)\.\S+\.v\d+$` 的 DOI。
- 找到对应的 concept DOI 条目（若存在）→ first-seen-wins 合并；不存在则
  原地规范化 doi 字段，把原 DOI 写入 raw_doi。
- 写入一份 `data/migrations/2026-05-XX-figshare-version-normalization.jsonl`
  审计日志，每行记一次合并/重写。

## 影响评估

- W21 pilot：2 组重复（4 条 → 2 条），节省 ~7% 的精读循环时间。
- 6 周窗口（288 篇 corpus）：估计 5–8 组（待扫描确认），节省 5%–10%。
- 历史 corpus（11K papers）：未知，需扫描。

风险：

1. **误规范化**：如果某个 figshare DOI 的 `.v1` 和 concept DOI **真不指向同一
   研究**（极不常规但理论上可能），会错误合并。**缓解**：保留 raw_doi 字段，
   可审计回滚；migration 时打印每组合并的标题，人工抽查 5%。
2. **OpenAlex / Zotero 同步行为变化**：Zotero collection 里如果之前同时存在
   两版，迁移后可能产生孤儿条目。**缓解**：迁移脚本同时清理 Zotero（按
   data/zotero_sync_log/ 反查）。

## 不在本 ADR 范围

- **不**改 ADR-0015 的 `identity_key` 函数（保持纯粹）。
- **不**对非数据仓库 DOI 做任何规范化（如期刊 DOI、preprint DOI）。
- **不**做跨数据库 dedup（OpenAlex W-id ↔ DOI 的关系是另一个问题）。
- **不**做模糊 title-based dedup（CLAUDE.md 明确反对）。

## 实施前置条件

1. 全量扫描确认问题规模（数据仓库 DOI 占 corpus 比例）。
2. 选 3–5 组重复样本人工核对，确认 concept/version 内容一致性。
3. user 批准后实施。

## 验收标准

- 实施后再跑一次 W21 + 历史样本检查，零误合并。
- 后续 4 周内"同一研究两个 identity_key"信号 = 0。
- migration 审计日志可重放回滚。

## 决策日志条目（拟入 TODO.md Decision Log）

```
| 2026-05-26 | ADR-0025 草案 | figshare/Zenodo 版本化 DOI namespace 规范化 | Claude pilot W21 | Draft |
```
