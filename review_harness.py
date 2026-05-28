#!/usr/bin/env python3
"""
Research Radar — 文献精读 harness (可恢复 / 可暂停)

职责（确定性部分，全部由脚本完成）：
  - 发现 daily JSON 里 priority=High/Medium 且未处理的论文
  - 解析并下载 PDF（arxiv → Unpaywall(DOI) → OpenAlex oa_url）
  - 抽取 PDF 正文为纯文本
  - 维护断点状态 state.json（每篇处理完原子落盘）
  - 暂停 / 恢复（PAUSE 标记文件）
  - 按 ISO 周聚合已完成论文，产出周报清单 + 规范文件名

Claude Code 只负责“读正文 + 写总结/周报”，不维护任何状态。

CLI:
  python review_harness.py discover            # 扫描 daily，把 High/Medium 收进状态
  python review_harness.py status              # 进度概览
  python review_harness.py next                # 取下一篇（含已下载 PDF / 抽取正文路径），输出 JSON
  python review_harness.py done <id> --kind read|checked --summary <path>
  python review_harness.py fail <id> --reason "..."
  python review_harness.py pause               # 创建 PAUSE 标记
  python review_harness.py resume              # 删除 PAUSE 标记
  python review_harness.py weekly <YYYY-Www>   # 输出某周已完成论文清单 + 规范报告路径
"""

import argparse
import json
import os
import re
import sys
import time
import datetime as dt
from pathlib import Path

import urllib.request
import urllib.parse

# ----------------------------------------------------------------------------
# 配置：按你的仓库实际路径调整
# ----------------------------------------------------------------------------
ROOT        = Path(os.environ.get("RADAR_ROOT", "."))
DAILY_DIR   = ROOT / "data" / "daily"
REVIEW_DIR  = ROOT / "data" / "review"
SUMMARY_DIR = REVIEW_DIR / "summaries"
PDF_CACHE   = REVIEW_DIR / "pdf_cache"
TEXT_CACHE  = REVIEW_DIR / "text"
STATE_PATH  = REVIEW_DIR / "state.json"
PAUSE_FLAG  = REVIEW_DIR / "PAUSE"
REPORT_DIR  = ROOT / "reports" / "weekly"

# Unpaywall 需要一个邮箱（免费、必填）。设环境变量 UNPAYWALL_EMAIL。
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")

PRIORITIES = {"high", "medium"}          # 只精读这两档
MAX_ATTEMPTS = 3                          # 同一篇下载失败重试上限
HTTP_TIMEOUT = 40
UA = "ResearchRadarReviewer/1.0 (mailto:%s)" % (UNPAYWALL_EMAIL or "anon@example.com")

# discover 的时间窗口下界：REVIEW_SINCE=YYYY-MM-DD 覆盖，缺省 = 今天 - 6 周。
# 只接收 source_date >= 该日期 的论文，避免一次性把多年历史回填全塞进 state。
REVIEW_SINCE_DEFAULT_WEEKS = 6


def discover_since() -> str:
    env = os.environ.get("REVIEW_SINCE", "").strip()
    if env:
        return env
    return (dt.date.today() - dt.timedelta(weeks=REVIEW_SINCE_DEFAULT_WEEKS)).isoformat()


# ----------------------------------------------------------------------------
# 适配器：把你的 daily JSON v2 记录映射成统一字段。
# >>> 如果字段名和这里不一致，只改这一个函数即可。 <
# ----------------------------------------------------------------------------
def adapt_record(rec: dict) -> dict:
    """从一条 v2 daily 记录抽取统一字段。缺失的返回 ''。"""
    doi = (rec.get("doi") or "").strip()
    arxiv_id = (rec.get("arxiv_id") or "").strip()

    # ADR-0015 §4.4 identity_key: doi:<doi> | arxiv:<arxiv_id> | fallback rec.id
    if doi:
        ident = f"doi:{doi}"
    elif arxiv_id:
        ident = f"arxiv:{arxiv_id}"
    else:
        ident = rec.get("identity_key") or rec.get("id") or ""

    # v2: priority + zh/en 结构化摘要 都在 rec["llm"] 下
    llm = rec.get("llm") or {}
    priority = (llm.get("priority") or rec.get("priority") or "").strip()

    def _flatten_summary(s):
        if isinstance(s, dict):
            order = ("motivation", "method", "result", "validation")
            labels = {"motivation": "动机", "method": "方法",
                      "result": "结果", "validation": "验证"}
            parts = [f"【{labels[k]}】{s[k]}" for k in order if s.get(k)]
            return "\n".join(parts)
        return s or ""

    existing_summary = _flatten_summary(llm.get("summary_zh")) \
        or rec.get("summary") or rec.get("abstract_zh") or ""
    existing_summary_en = (rec.get("abstract")
                           or _flatten_summary(llm.get("summary_en"))
                           or rec.get("summary_en") or "")

    return {
        "id": ident,
        "title": rec.get("title") or "",
        "priority": priority,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "oa_url": (rec.get("oa_url") or rec.get("open_access_url") or "").strip(),
        "direction": rec.get("direction") or rec.get("direction_name") or rec.get("route") or "",
        "existing_summary": existing_summary,
        "existing_summary_en": existing_summary_en,
    }


def load_daily_records():
    """遍历 data/daily/*.json，返回 [(source_date, adapted_record), ...]。"""
    out = []
    if not DAILY_DIR.exists():
        return out
    for fp in sorted(DAILY_DIR.glob("*.json")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", fp.stem)
        date_str = m.group(1) if m else fp.stem
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] 跳过无法解析的 {fp.name}: {e}", file=sys.stderr)
            continue
        records = data.get("papers", data) if isinstance(data, dict) else data
        if not isinstance(records, list):
            continue
        for rec in records:
            if isinstance(rec, dict):
                out.append((date_str, adapt_record(rec)))
    return out


# ----------------------------------------------------------------------------
# 状态管理（原子写）
# ----------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "papers": {}}


def save_state(state: dict):
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)   # 原子替换：崩溃不会留下半截文件


def iso_week(date_str: str) -> str:
    try:
        d = dt.date.fromisoformat(date_str)
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    except Exception:
        return "unknown"


def safe_id(ident: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", ident)[:120]


# ----------------------------------------------------------------------------
# PDF 解析 + 下载 + 正文抽取
# ----------------------------------------------------------------------------
def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
        return r.read()


def resolve_pdf_url(p: dict):
    """按优先级返回 (pdf_url, source)；找不到返回 (None, reason)。"""
    if p.get("arxiv_id"):
        aid = p["arxiv_id"].split("v")[0]
        return f"https://arxiv.org/pdf/{aid}.pdf", "arxiv"
    if p.get("doi") and UNPAYWALL_EMAIL:
        try:
            doi = urllib.parse.quote(p["doi"], safe="")
            url = f"https://api.unpaywall.org/v2/{doi}?email={UNPAYWALL_EMAIL}"
            meta = json.loads(_http_get(url).decode("utf-8"))
            loc = meta.get("best_oa_location") or {}
            pdf = loc.get("url_for_pdf") or loc.get("url")
            if pdf:
                return pdf, "unpaywall"
        except Exception as e:
            print(f"[warn] unpaywall 查询失败 {p['doi']}: {e}", file=sys.stderr)
    if p.get("oa_url"):
        return p["oa_url"], "oa_url"
    return None, "no_open_access_link"


MIN_ARTICLE_BYTES = 6000          # 200B 太松，会把出版商着陆页判成正文（W21 pilot 实证）
MIN_BODY_MARKERS = 5              # 文章应至少出现 5 个正文区段词
MAX_BULLET_RATIO = 0.25           # >25% bullet-led 行 → 像导航菜单。W20 GRAFT 调整：
                                  # 长文 itemize 列表可推到 17%，安全上限取 25%。
                                  # 已知 landing pages 最低 20.7% 但 markers<5，
                                  # 仍然被 markers 检查拦下；两条规则同时使用。
_BODY_MARKERS = (
    "introduction", "method", "result", "conclusion", "discussion",
    "experiment", "we propose", "we present", "et al.",
    "引言", "方法", "结果", "结论", "实验",
)
_NAV_BULLET_PREFIXES = ("•", "→", "■", "○", "►")


def _looks_like_article(text: str) -> bool:
    """启发式：text 是否像正文，而不是出版商着陆页（Wiley / BMC / Springer 等的
    nav 菜单）。W21 pilot 数据上，真正文 bullet 比例 0.1%–5.8% / 正文词 6–8；
    着陆页 bullet 20%–48% / 正文词 0–4——两条规则同时使用即可清分。"""
    if len(text) < MIN_ARTICLE_BYTES:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    bullet_lines = sum(1 for ln in lines if ln.startswith(_NAV_BULLET_PREFIXES))
    if bullet_lines / len(lines) > MAX_BULLET_RATIO:
        return False
    lower = text.lower()
    body_hits = sum(1 for m in _BODY_MARKERS if m in lower)
    return body_hits >= MIN_BODY_MARKERS


def download_and_extract(ident: str, p: dict):
    """返回 (text_path|None, info_dict)。下载失败时 text_path=None。"""
    PDF_CACHE.mkdir(parents=True, exist_ok=True)
    TEXT_CACHE.mkdir(parents=True, exist_ok=True)
    sid = safe_id(ident)
    pdf_path = PDF_CACHE / f"{sid}.pdf"
    text_path = TEXT_CACHE / f"{sid}.txt"

    # 缓存命中也要过 sanity check——老版本写入过低于阈值或着陆页的 .txt。
    if text_path.exists():
        cached = text_path.read_text(encoding="utf-8", errors="ignore")
        if _looks_like_article(cached):
            return str(text_path), {"cached": True, "pdf_path": str(pdf_path)}

    url, source = resolve_pdf_url(p)
    if not url:
        return None, {"reason": source}

    try:
        data = _http_get(url)
        if not data or len(data) < 1000:
            return None, {"reason": "download_too_small", "url": url}
        pdf_path.write_bytes(data)
    except Exception as e:
        return None, {"reason": f"download_error: {e}", "url": url}

    text = extract_text(pdf_path)
    if not _looks_like_article(text):
        # 仍写下文件以便人工检查 / 复核，但 pdf_found=false。
        if text:
            text_path.write_text(text, encoding="utf-8")
        return None, {"reason": "not_article_like_or_landing_page",
                      "pdf_path": str(pdf_path),
                      "text_chars": len(text or "")}
    text_path.write_text(text, encoding="utf-8")
    return str(text_path), {"pdf_path": str(pdf_path), "source": source, "chars": len(text)}


def extract_text(pdf_path: Path) -> str:
    # 优先 PyMuPDF，回退 pdfplumber
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        return "\n".join(page.get_text() for page in doc)
    except Exception:
        pass
    try:
        import pdfplumber  # noqa: SCOPE-FI001 (personal reading tool; intentional full-text parse, see SCOPE.md exception)
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    except Exception as e:
        print(f"[warn] 正文抽取失败 {pdf_path.name}: {e}", file=sys.stderr)
        return ""


# ----------------------------------------------------------------------------
# 命令实现
# ----------------------------------------------------------------------------
def cmd_discover(_args):
    state = load_state()
    papers = state["papers"]
    since = discover_since()
    added = 0
    skipped_old = 0
    for date_str, rec in load_daily_records():
        if date_str < since:
            skipped_old += 1
            continue
        if rec["priority"].lower() not in PRIORITIES:
            continue
        ident = rec["id"]
        if not ident or ident in papers:
            continue
        papers[ident] = {
            "status": "pending",
            "priority": rec["priority"],
            "title": rec["title"],
            "direction": rec["direction"],
            "doi": rec["doi"],
            "arxiv_id": rec["arxiv_id"],
            "oa_url": rec["oa_url"],
            "existing_summary": rec["existing_summary"],
            "source_date": date_str,
            "week": iso_week(date_str),
            "attempts": 0,
            "pdf_found": None,
            "summary_path": None,
            "last_error": None,
            "updated_at": None,
        }
        added += 1
    save_state(state)
    pending = sum(1 for v in papers.values() if v["status"] == "pending")
    print(f"discover: 时间窗 >= {since}（窗外跳过 {skipped_old} 条记录）；新增 {added} 篇，待处理库共 {pending} 篇 pending")


def cmd_status(_args):
    state = load_state()
    from collections import Counter
    c = Counter(v["status"] for v in state["papers"].values())
    total = sum(c.values())
    paused = PAUSE_FLAG.exists()
    print(f"=== Review 进度（PAUSE={'ON' if paused else 'off'}）===")
    print(f"总计纳入: {total}")
    for st in ["pending", "reading", "read", "checked", "failed"]:
        print(f"  {st:8s}: {c.get(st,0)}")
    weeks = {}
    for v in state["papers"].values():
        weeks.setdefault(v["week"], Counter())[v["status"]] += 1
    print("--- 按 ISO 周 ---")
    for wk in sorted(weeks):
        cc = weeks[wk]
        done = cc.get("read", 0) + cc.get("checked", 0)
        print(f"  {wk}: 完成 {done}/{sum(cc.values())}")


def cmd_next(_args):
    if PAUSE_FLAG.exists():
        print(json.dumps({"status": "PAUSED",
                          "hint": "存在 PAUSE 标记，删除它或运行 `resume` 后再继续。"},
                         ensure_ascii=False))
        return
    state = load_state()
    papers = state["papers"]

    def sort_key(item):
        _id, v = item
        pr = 0 if v["priority"].lower() == "high" else 1
        # date-primary newest-first; priority only orders within a date.
        # weekly-report cadence dominates: finish W21 before starting W20.
        try:
            date_rank = -dt.date.fromisoformat(v["source_date"]).toordinal()
        except Exception:
            date_rank = 0
        return (0 if v["status"] == "reading" else 1, date_rank, pr, _id)

    candidates = [(i, v) for i, v in papers.items()
                  if v["status"] in ("pending", "reading") and v["attempts"] < MAX_ATTEMPTS]
    if not candidates:
        remaining = sum(1 for v in papers.values() if v["status"] == "pending")
        print(json.dumps({"status": "DONE",
                          "hint": f"没有可处理的论文了（pending={remaining}，可能都已达重试上限）。"},
                         ensure_ascii=False))
        return

    ident, v = sorted(candidates, key=sort_key)[0]
    v["status"] = "reading"
    v["attempts"] += 1
    v["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state)

    text_path, info = download_and_extract(ident, v)
    v["pdf_found"] = bool(text_path)
    if not text_path:
        v["last_error"] = info.get("reason")
    save_state(state)

    payload = {
        "status": "READY",
        "id": ident,
        "title": v["title"],
        "priority": v["priority"],
        "direction": v["direction"],
        "week": v["week"],
        "source_date": v["source_date"],
        "existing_summary": v["existing_summary"],
        "pdf_found": bool(text_path),
        "text_path": text_path,
        "fail_reason": v["last_error"],
        "summary_target": str(SUMMARY_DIR / f"{safe_id(ident)}.md"),
        "instruction": ("有正文：精读 text_path，写详细总结到 summary_target，然后 "
                        "`done <id> --kind read --summary <summary_target>`。"
                        if text_path else
                        "无正文：复核 existing_summary 与 priority 是否合理，写复核记录到 "
                        "summary_target，然后 `done <id> --kind checked --summary <summary_target>`。"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_done(args):
    state = load_state()
    v = state["papers"].get(args.id)
    if not v:
        print(f"[error] 未知 id: {args.id}", file=sys.stderr)
        sys.exit(1)
    v["status"] = "read" if args.kind == "read" else "checked"
    v["summary_path"] = args.summary
    v["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state)
    print(f"done: {args.id} -> {v['status']}")


def cmd_fail(args):
    state = load_state()
    v = state["papers"].get(args.id)
    if not v:
        print(f"[error] 未知 id: {args.id}", file=sys.stderr)
        sys.exit(1)
    v["status"] = "failed"
    v["last_error"] = args.reason
    v["updated_at"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state)
    print(f"fail: {args.id} 已标记 failed（{args.reason}）")


def cmd_pause(_args):
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    PAUSE_FLAG.write_text(dt.datetime.now().isoformat(), encoding="utf-8")
    print("已暂停：next 将返回 PAUSED，直到运行 resume。")


def cmd_resume(_args):
    if PAUSE_FLAG.exists():
        PAUSE_FLAG.unlink()
    print("已恢复。")


def cmd_weekly(args):
    week = args.week
    state = load_state()
    items = [(i, v) for i, v in state["papers"].items()
             if v["week"] == week and v["status"] in ("read", "checked")]
    items.sort(key=lambda kv: (0 if kv[1]["priority"].lower() == "high" else 1,
                               kv[1]["source_date"]))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{week}_周报.md"
    manifest = {
        "week": week,
        "report_path": str(report_path),
        "count": len(items),
        "papers": [{
            "id": i,
            "title": v["title"],
            "priority": v["priority"],
            "direction": v["direction"],
            "kind": v["status"],
            "pdf_found": v["pdf_found"],
            "summary_path": v["summary_path"],
        } for i, v in items],
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description="Research Radar 文献精读 harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover").set_defaults(func=cmd_discover)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("next").set_defaults(func=cmd_next)
    sub.add_parser("pause").set_defaults(func=cmd_pause)
    sub.add_parser("resume").set_defaults(func=cmd_resume)
    d = sub.add_parser("done"); d.add_argument("id"); d.add_argument("--kind", choices=["read", "checked"], required=True); d.add_argument("--summary", required=True); d.set_defaults(func=cmd_done)
    f = sub.add_parser("fail"); f.add_argument("id"); f.add_argument("--reason", required=True); f.set_defaults(func=cmd_fail)
    w = sub.add_parser("weekly"); w.add_argument("week"); w.set_defaults(func=cmd_weekly)
    args = ap.parse_args()
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    args.func(args)


if __name__ == "__main__":
    main()
