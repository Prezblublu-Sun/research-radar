# Developmentally Inspired Bioprinting of Nascent Multicellular Human Heart Tissue Through in Situ Differentiation and Morphogenesis of iPSCs

- **id**: `doi:10.1002/advs.202522241` · 方向 ai_bioprinting · 优先级 Medium · checked
- **失败原因**: Wiley OA 链接重定向到登录/导航页（3957 字节，全是 Wiley 站内导航菜单，
  无正文）。harness 的 200B 文本阈值太低，应触发"假阳性 pdf_found"标记。
- **来源日期**: 2026-05-20（**W21**）

## 复核

- **方向**：正确。Matrigel 嵌入式生物打印 + iPSC 原位分化 + 多细胞心脏组织，
  ai_bioprinting 核心。
- **优先级 Medium**：合理。心脏组织工程偏发育生物学应用，与 user 骨/植入物主线
  距离很远。技术上 "embedded bioprinting + 粘弹支撑浴 + 原位分化" 是漂亮工作但不
  对接 user 需求。
- **摘要质量**：好。覆盖关键技术（嵌入式、Matrigel、粘弹调控、iPSC）和验证手段
  （免疫荧光 + 基因表达）。
- **跟进**：低。仅作 ai_bioprinting 方向的发育/组织工程前沿了解。

## harness 反馈（重要）★

`download_and_extract` 中 `text_path.stat().st_size > 200` 这个阈值不足以排除 Wiley
风格的导航页（4KB 全是站内链接）。建议：
1. 阈值上调到 2KB 或 5KB；
2. 或在抽取后做"内容性"启发式检查：若文本里 article-body 标志词（abstract / methods
   / references / figure / et al. / DOI:）出现频次过低，判为非正文 → pdf_found=false。
本周报应正式记录此 harness 改进项。
