# NIMO Controller: a self-driving laboratory orchestrator based on the Model Context Protocol

- **id**: `arxiv:2605.15227v1` · 方向 ai_bioprinting · 优先级 Medium · **read**（摘要）
- **来源**: arXiv 2605.15227, 2026-05-13（**W20**）

## 核心思路

基于 MCP（Model Context Protocol，Anthropic 推动的标准）设计 self-driving lab
架构。所有 SDL 功能通过 MCP 服务器暴露，支持人类与 AI agent 统一访问。

## 与 user 关联

- ai_bioprinting 命中正确（SDL 是生物墨水/生物制造的工艺自动化平台）。
- 案例是"颜色匹配"——非生物医学，但架构思路对生物制造 SDL 通用。
- 与 W21 LABO / LGBO / LLM-AL（LLM-augmented BO/AL）形成上下游：LABO 等是
  "决策算法"层，NIMO 是"orchestration"层。

## 评分

priority=Medium 合理。novelty=medium（MCP 是新协议，但 SDL 概念成熟）。
pathway=none（颜色匹配 → 生物墨水需要平移）。

## 跟进

低-中。技术信息基础设施类工作，不必精读但值得知道存在。
