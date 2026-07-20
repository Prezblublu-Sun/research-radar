"""Render daily HTML pages with top-bar navigation and version footer."""

from __future__ import annotations
import hashlib
import html
import json
import pathlib
import re

from render import corpus_view


def _load_papers_v2_or_v1(path: pathlib.Path) -> tuple[list[dict], dict]:
    """Return (papers, file_meta) for a daily JSON, v2-dict or stray v1-list.

    v2 (ADR-0015 §4.5): {schema_version, date, date_precision, papers, counts}
    v1 (pre-migration): top-level list of paper dicts.
    Backward-compat path tolerates anything else by returning ([], {}).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], {}
    if isinstance(data, list):
        return data, {}
    if isinstance(data, dict):
        papers = data.get("papers", [])
        if not isinstance(papers, list):
            papers = []
        meta = {k: v for k, v in data.items() if k != "papers"}
        return papers, meta
    return [], {}


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _clean_html(document: str) -> str:
    """Keep generated diffs clean when optional template rows are empty."""
    return "\n".join(line.rstrip() for line in document.split("\n"))


def _public_identity_key(p: dict, bucket_date: str = "",
                         position: int | None = None) -> str:
    """Return a stable UI key without deduplicating identity-less records."""
    strict = corpus_view.identity_key(p)
    if strict:
        return strict
    seed = "|".join((
        bucket_date or str(p.get("date") or ""),
        "" if position is None else str(position),
        str(p.get("source") or ""),
        str(p.get("title") or ""),
    )).encode("utf-8")
    return "noid:" + hashlib.sha1(seed).hexdigest()[:16]


def _identity_key(p: dict) -> str:
    """Return a strict corpus key or deterministic UI-only no-ID fallback."""
    return _public_identity_key(p)


def _anchor_id(identity_key: str) -> str:
    """URL/HTML-fragment-safe form of an identity key for in-page anchors."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", identity_key)


def _card_tools(p: dict, identity_key: str | None = None) -> str:
    """ADR-0016 D4 (mark + note) and D5 (promote) per-card controls.

    Rendered statically; all behaviour is wired client-side by
    render/static/radar-ui.js reading the card's `data-identity-key`.
    """
    idkey = identity_key or _identity_key(p)
    name = f"rui-mark-{_anchor_id(idkey)}"
    states = [
        ("to-read", "待阅读"), ("read", "已阅读"),
        ("interesting", "有启发"), ("ignore", "忽略"),
    ]
    radios = "".join(
        f'<label class="m-{val}"><input type="radio" class="rui-mark-radio" '
        f'name="{_esc(name)}" value="{val}">{_esc(lbl)}</label>'
        for val, lbl in states
    )
    return f"""
  <div class="rui-card-tools">
    <span class="rui-mark-group"><b>标记：</b> {radios}</span>
    <button type="button" class="rui-note-btn">笔记</button>
    <button type="button" class="rui-promote-btn">发送到 lit-system</button>
    <div class="rui-note-wrap">
      <textarea class="rui-note-ta" placeholder="私人笔记（失焦自动保存，仅限当前浏览器）"></textarea>
    </div>
  </div>"""


def _paper_card(p: dict, dir_color: str, daily_link_date: str | None = None,
                identity_key: str | None = None) -> str:
    llm = p.get("llm") or {}
    priority = llm.get("priority") or "Low"
    s = llm.get("summary_zh") or {}
    s_en = llm.get("summary_en") or {}
    key_terms = llm.get("key_terms") or []
    flags = llm.get("flags") or {}
    relevance_level = llm.get("relevance_level") or ""
    read_action = llm.get("read_action") or ""
    why_not_core = llm.get("why_not_core") or ""
    validation_kind = llm.get("validation_kind") or ""

    badge_flags = []
    if flags.get("has_experimental_validation"):
        badge_flags.append("Exp. validation")
    if flags.get("has_uncertainty_quantification"):
        badge_flags.append("UQ")
    if flags.get("is_patient_specific"):
        badge_flags.append("Patient-specific")
    if flags.get("is_review"):
        badge_flags.append("Review")
    flag_html = " ".join(f'<span class="flag">{_esc(f)}</span>' for f in badge_flags)
    tags_html = " ".join(
        f'<span class="tag">{_esc(t)}</span>'
        for t in (llm.get("tags") or [])
    )

    authors = ", ".join(p.get("authors", [])[:5])
    if len(p.get("authors", [])) > 5:
        authors += " et al."
    first_aff = p.get("first_author_affiliation", "")
    # Only keep corresponding entries that actually have an affiliation
    corresp_list = [c for c in (p.get("corresponding_authors") or []) if c.get("affiliation")]

    doi_link = ""
    if p.get("doi"):
        doi_link = f'<a href="https://doi.org/{_esc(p["doi"])}" target="_blank">{_esc(p["doi"])}</a>'
    elif p.get("url"):
        doi_link = f'<a href="{_esc(p["url"])}" target="_blank">link</a>'

    idkey = identity_key or _identity_key(p)
    daily_link = ""
    if daily_link_date:
        daily_link = (f'<a class="rui-link-tool" '
                      f'href="{_esc(daily_link_date)}.html#{_anchor_id(idkey)}">'
                      f'→ {_esc(daily_link_date)} page</a>')

    return f"""
<article class="paper" id="{_anchor_id(idkey)}" data-direction="{_esc(p.get('direction',''))}" data-priority="{_esc(priority)}" data-identity-key="{_esc(idkey)}" data-title="{_esc(p.get('title',''))}" data-date="{_esc(p.get('date',''))}">
  <h3 class="paper-title">{_esc(p.get('title',''))}</h3>
  <div class="paper-head">
    <span class="priority priority--{_esc(priority.lower())}">{_esc(priority)}</span>
    <span class="direction-pill" style="background:{dir_color}20;color:{dir_color}">{_esc(p.get('direction_name',''))}</span>
    <span class="source">{_esc(p.get('source',''))}</span>
    {f'<span class="relevance-level lvl-{relevance_level.lower()}">{_esc(relevance_level)}</span>' if relevance_level else ''}
    {f'<span class="read-action act-{read_action.lower().replace(" ", "-")}">{_esc(read_action)}</span>' if read_action else ''}
    {f'<span class="validation-kind">{_esc(validation_kind)}</span>' if validation_kind else ''}
    {flag_html}
  </div>
  <div class="meta">
    <span class="authors">{_esc(authors)}</span>
    <span class="venue">{_esc(p.get('venue',''))}</span>
    <span class="date">{_esc(p.get('date',''))}</span>
    <span class="doi">{doi_link}</span>
  </div>
  {f'<div class="affiliations"><b>单位:</b> {_esc(first_aff[:200])}</div>' if first_aff else ''}
  {('<div class="corresponding"><b>通讯:</b> ' + ' &nbsp;|&nbsp; '.join(f'{_esc(c["name"])} <span class="corresp-aff">@ {_esc(c["affiliation"][:120])}</span>' + (' <i>[推断]</i>' if c.get('inferred') else '') for c in corresp_list) + '</div>') if corresp_list else ''}
  <div class="relevance"><b>相关性:</b> {_esc(llm.get('relevance_to_user',''))}</div>
  {f'<div class="why-not-core"><b>边界:</b> {_esc(why_not_core)}</div>' if why_not_core else ''}
  <div class="summary">
    <div><b>动机·</b> {_esc(s.get('motivation',''))}</div>
    <div><b>方法·</b> {_esc(s.get('method',''))}</div>
    <div><b>结果·</b> {_esc(s.get('result',''))}</div>
    <div><b>验证·</b> {_esc(s.get('validation',''))}</div>
  </div>
  <details class="summary-en">
    <summary>英文摘要与术语</summary>
    <div class="summary en">
      <div><b>Motivation·</b> {_esc(s_en.get('motivation',''))}</div>
      <div><b>Method·</b> {_esc(s_en.get('method',''))}</div>
      <div><b>Result·</b> {_esc(s_en.get('result',''))}</div>
      <div><b>Validation·</b> {_esc(s_en.get('validation',''))}</div>
    </div>
    <div class="key-terms">
      {''.join(f'<span class="term"><b>{_esc(t.get("en",""))}</b> · {_esc(t.get("zh",""))}</span>' for t in key_terms)}
    </div>
  </details>
  <div class="tags-row">{tags_html}</div>
  {daily_link}
  {_card_tools(p, idkey)}
</article>"""


def _stats_row(papers: list[dict], directions_cfg: dict) -> str:
    total = {"High": 0, "Medium": 0, "Low": 0, "Exclude": 0}
    for p in papers:
        prio = (p.get("llm") or {}).get("priority") or "Low"
        total[prio] = total.get(prio, 0) + 1
    cards = [f'<div class="stat"><div class="stat-label">论文总数</div><div class="stat-val">{sum(total.values())}</div></div>']
    for prio, color in [("High", "#27500A"), ("Medium", "#633806"), ("Low", "#5F5E5A")]:
        cards.append(f'<div class="stat"><div class="stat-label">{prio}</div><div class="stat-val" style="color:{color}">{total[prio]}</div></div>')
    return '<div class="stats">' + "".join(cards) + "</div>"


def _direction_tabs(directions_cfg: dict) -> str:
    tabs = ['<button class="tab active" data-filter="all">全部方向</button>']
    for dkey, dcfg in directions_cfg.items():
        tabs.append(f'<button class="tab" data-filter="{_esc(dkey)}">{_esc(dcfg["display_name"])}</button>')
    return '<div class="tabs" aria-label="研究方向筛选">' + "".join(tabs) + "</div>"


def _priority_filter_bar() -> str:
    """ADR-0016 D3: client-side priority checkboxes.

    Defaults (High+Medium on) live in radar-ui.js; it overrides `checked`
    here from localStorage `radar:filter:priority` on load, so the static
    `checked` markup is only the first-visit default.
    """
    boxes = []
    for prio in ("High", "Medium", "Low", "Exclude"):
        checked = " checked" if prio in ("High", "Medium") else ""
        boxes.append(
            f'<label><input type="checkbox" class="rui-pf-cb" '
            f'value="{prio}"{checked}>{prio}</label>'
        )
    return ('<div class="rui-filter-bar" id="rui-priority-filter">'
            '<b>等级：</b> ' + " ".join(boxes) + "</div>")


def _marks_filter_bar() -> str:
    """ADR-0016 D4: client-side "filter to my marks" checkboxes."""
    opts = [
        ("to-read", "待阅读"), ("read", "已阅读"),
        ("interesting", "有启发"), ("ignore", "忽略"),
        ("none", "未标记"),
    ]
    boxes = "".join(
        f'<label><input type="checkbox" class="rui-mf-cb" '
        f'value="{val}" checked>{_esc(lbl)}</label>'
        for val, lbl in opts
    )
    return ('<div class="rui-filter-bar" id="rui-marks-filter">'
            '<b>我的标记：</b> ' + boxes + "</div>")


def _topbar(date: str, archive_dates: list[str]) -> str:
    """Top navigation: prev/next day buttons + Archive dropdown."""
    if not archive_dates:
        archive_dates = [date]
    sorted_dates = sorted(archive_dates)
    try:
        idx = sorted_dates.index(date)
    except ValueError:
        idx = len(sorted_dates) - 1
    prev_date = sorted_dates[idx - 1] if idx > 0 else None
    next_date = sorted_dates[idx + 1] if idx < len(sorted_dates) - 1 else None

    prev_btn = (f'<a class="navbtn" href="{prev_date}.html">← {prev_date}</a>'
                if prev_date else '<span class="navbtn disabled">← 最早</span>')
    next_btn = (f'<a class="navbtn" href="{next_date}.html">{next_date} →</a>'
                if next_date else '<span class="navbtn disabled">最新 →</span>')

    options = "".join(
        f'<option value="{d}.html"{" selected" if d == date else ""}>{d}</option>'
        for d in reversed(sorted_dates)
    )
    dropdown = f'<select class="archive-select" onchange="if(this.value)window.location.href=this.value">{options}</select>'

    return f'<div class="topbar">{prev_btn}{dropdown}{next_btn}</div>'


def _site_nav(active: str = "") -> str:
    """Primary information architecture shared by every public page."""
    links = [
        ("today", "index.html", "今日"),
        ("queue", "queue.html", "队列"),
        ("search", "search.html", "搜索"),
        ("library", "library.html", "资料库"),
        ("archive", "archive.html", "归档"),
    ]
    rendered = []
    for key, href, label in links:
        current = ' aria-current="page" class="site-nav__link is-active"' \
            if key == active else ' class="site-nav__link"'
        rendered.append(f'<a href="{href}"{current}>{label}</a>')
    admin_open = " open" if active == "admin" else ""
    return (
        '<nav class="site-nav" aria-label="主导航">'
        '<a class="site-nav__brand" href="index.html">Research Radar</a>'
        '<div class="site-nav__links">' + "".join(rendered) +
        f'<details class="site-nav__admin"{admin_open}>'
        '<summary>系统</summary><div class="site-nav__menu">'
        '<a href="status.html">运行状态</a>'
        '<a href="weekly/index.html">周报</a>'
        '</div></details></div></nav>'
    )


def _version_footer(manifest: dict | None) -> str:
    if not manifest:
        return ""
    cfg = manifest.get("config", {})
    llm = manifest.get("llm", {})
    return f"""
<footer class="run-info">
  <details><summary>Run version info</summary>
    <table>
      <tr><td>run_id</td><td>{_esc(manifest.get('run_id'))}</td></tr>
      <tr><td>git_commit</td><td><code>{_esc(manifest.get('git_commit'))}</code></td></tr>
      <tr><td>directions.yaml</td><td><code>{_esc(cfg.get('directions_yaml'))}</code></td></tr>
      <tr><td>scorer prompt</td><td>{_esc(cfg.get('scorer_prompt_file'))} <code>{_esc(cfg.get('scorer_prompt'))}</code></td></tr>
      <tr><td>LLM model</td><td>{_esc(llm.get('model_alias'))} (snapshot: <code>{_esc(llm.get('model_snapshot_observed') or '—')}</code>)</td></tr>
      <tr><td>temperature</td><td>{_esc(llm.get('temperature'))}</td></tr>
    </table>
  </details>
</footer>"""


# V1 design tokens (ADR-0016 visual refresh). Single source of truth for
# the palette/spacing/shadow scale. Inlined at the top of the base CSS so
# both the inlined <style> block AND the shared radar-ui.css resolve the
# same var(--…) values; radar-ui.css repeats an identical :root so it also
# renders correctly if ever opened standalone.
DESIGN_TOKENS = """
:root{
--c-brand:#1B4D7E;--c-accent:#E89C3A;--c-bg:#FAFAF7;--c-card-bg:#FFFFFF;--c-card-border:#ECEAE3;
--c-text-primary:#1F2937;--c-text-secondary:#4B5563;--c-text-meta:#8B8980;--c-text-muted:#B5B3AA;
--c-priority-h:#C8362A;--c-priority-m:#E89C3A;--c-priority-l:#A0A0A0;--c-priority-x:#D5D5D5;
--c-mark-toread:#E8B538;--c-mark-read:#5B8C5A;--c-mark-int:#4A6FB5;--c-mark-ignore:#999999;
--space-xs:4px;--space-sm:8px;--space-md:12px;--space-lg:20px;--space-xl:32px;
--radius-sm:4px;--radius-md:8px;--radius-lg:12px;
--text-xs:11px;--text-sm:13px;--text-md:14px;--text-lg:16px;--text-xl:22px;--text-h1:28px;
--shadow-card:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.06);
--shadow-hover:0 4px 12px rgba(27,77,126,0.10),0 2px 4px rgba(0,0,0,0.06);
}
"""

# Base typography + the daily-page component rules, all rewritten to
# consume the tokens above. Selectors and structural box-model values are
# unchanged (daily-page structure stays per the visual-refresh scope);
# only colour/radius/shadow values now flow from the token scale.
CSS = DESIGN_TOKENS + """
body{font-family:-apple-system,'PingFang SC',BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;background:var(--c-bg);color:var(--c-text-primary);line-height:1.5}
h1{font-size:var(--text-h1);font-weight:600;margin:0 0 var(--space-xs);color:var(--c-brand)}
.subtitle{color:var(--c-text-meta);font-size:var(--text-sm);margin-bottom:var(--space-xl)}
.topbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 0;margin-bottom:1.25rem;border-bottom:1px solid var(--c-card-border)}
.navbtn{font-size:var(--text-sm);background:var(--c-card-bg);color:var(--c-text-secondary);padding:6px 12px;border:1px solid var(--c-card-border);border-radius:var(--radius-md);text-decoration:none}
.navbtn:hover{background:var(--c-brand);color:#fff;border-color:var(--c-brand)}
.navbtn.disabled{color:var(--c-text-muted);background:var(--c-bg);cursor:default}
.archive-select{font-size:var(--text-sm);padding:6px 10px;border:1px solid var(--c-card-border);border-radius:var(--radius-md);background:var(--c-card-bg);color:var(--c-text-secondary);cursor:pointer}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-md);margin-bottom:1.5rem}
.stat{background:var(--c-card-bg);border:1px solid var(--c-card-border);border-radius:var(--radius-md);padding:.75rem 1rem}
.stat-label{font-size:12px;color:var(--c-text-meta)}
.stat-val{font-size:var(--text-xl);font-weight:600;margin-top:2px}
.tabs,.prio-filter{display:flex;gap:var(--space-sm);flex-wrap:wrap;margin-bottom:.75rem}
.tab,.pf{background:transparent;border:1px solid var(--c-card-border);border-radius:var(--radius-md);padding:6px 14px;font-size:var(--text-sm);cursor:pointer;color:var(--c-text-secondary)}
.tab.active,.pf.active{background:var(--c-brand);color:#fff;border-color:var(--c-brand)}
.paper{background:var(--c-card-bg);border:1px solid var(--c-card-border);border-radius:var(--radius-lg);padding:1rem 1.25rem;margin-bottom:var(--space-md)}
.paper-head{display:flex;gap:var(--space-sm);align-items:center;flex-wrap:wrap;margin-bottom:var(--space-sm)}
.priority{font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px}
.direction-pill{font-size:var(--text-xs);padding:3px 8px;border-radius:var(--radius-md)}
.source{font-size:var(--text-xs);color:var(--c-text-muted);text-transform:uppercase}
.flag{font-size:var(--text-xs);background:#EEF2F8;color:var(--c-brand);padding:2px 7px;border-radius:6px}
.paper-title{font-size:15px;font-weight:600;line-height:1.4;margin:4px 0;color:var(--c-text-primary)}
.meta{font-size:12px;color:var(--c-text-meta);margin-bottom:10px}
.meta>span{margin-right:12px}
.relevance{font-size:var(--text-sm);background:var(--c-bg);padding:6px 10px;border-radius:6px;margin-bottom:var(--space-sm)}
.summary{font-size:var(--text-sm);line-height:1.65}
.summary>div{margin-bottom:4px}
.tags-row{margin-top:var(--space-sm)}
.tag{font-size:var(--text-xs);background:#EEF2F8;color:var(--c-brand);padding:2px 8px;border-radius:10px;font-weight:500;margin-right:4px}
.paper[data-hidden="1"]{display:none}
footer.run-info{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--c-card-border);font-size:12px;color:var(--c-text-meta)}
footer.run-info summary{cursor:pointer;color:var(--c-text-secondary)}
footer.run-info table{margin-top:var(--space-sm);font-family:ui-monospace,monospace;font-size:var(--text-xs)}
footer.run-info td{padding:2px 12px 2px 0;vertical-align:top}
footer.run-info td:first-child{color:var(--c-text-meta);width:140px}
details.summary-en{margin-top:var(--space-sm);background:var(--c-bg);border-radius:var(--radius-md);padding:6px 12px;border:1px solid var(--c-card-border)}
details.summary-en summary{cursor:pointer;font-size:12px;color:var(--c-text-secondary);font-weight:600}
details.summary-en[open] summary{margin-bottom:var(--space-sm)}
.summary.en{font-size:var(--text-sm);color:var(--c-text-secondary);line-height:1.55}
.summary.en>div{margin-bottom:3px}
.key-terms{margin-top:var(--space-sm);display:flex;flex-wrap:wrap;gap:6px}
.term{font-size:var(--text-xs);background:var(--c-card-bg);border:1px solid var(--c-card-border);padding:3px 8px;border-radius:6px;color:var(--c-text-secondary)}
.term b{color:var(--c-text-primary);font-weight:600}
.affiliations{font-size:12px;color:var(--c-text-meta);margin-top:6px;padding-left:6px;border-left:2px solid var(--c-card-border)}
.affiliations b{color:var(--c-text-secondary);font-weight:600}
.corresponding{font-size:12px;color:var(--c-text-secondary);margin-top:3px;padding-left:6px;border-left:2px solid #aac}
.corresponding b{color:#3F2E7E;font-weight:600}
.corresp-aff{color:var(--c-text-meta)}
.corresponding i{color:var(--c-text-meta);font-size:var(--text-xs)}
.relevance-level{font-size:var(--text-xs);padding:3px 8px;border-radius:var(--radius-md);font-weight:600}
.lvl-direct{background:#D4EBC4;color:#2D5A14}
.lvl-transferable{background:#E0DDF4;color:#3F2E7E}
.lvl-peripheral{background:#F1EFE8;color:#666}
.read-action{font-size:var(--text-xs);padding:3px 8px;border-radius:var(--radius-md);font-weight:600;font-style:italic}
.act-read-now{background:#FFE8D6;color:#7D4515}
.act-save-for-project{background:#E6E1F5;color:#3A2C7A}
.act-skim-only{background:#F0F0E8;color:#5C5C50}
.act-background-only{background:#F5F5F0;color:#777}
.act-ignore{background:#F5E8E8;color:#7A3A3A}
.validation-kind{font-size:10px;background:#EDF4FA;color:#1F4A6B;padding:2px 7px;border-radius:6px}
.why-not-core{font-size:12px;background:#FCF5E8;border-left:3px solid var(--c-accent);padding:5px 10px;margin-top:4px;color:#5A4318;border-radius:0 6px 6px 0}
"""


# NOTE: the former inline daily-page JS (direction tabs + priority buttons)
# now lives in render/static/radar-ui.js, which also adds ADR-0016 D3/D4/D5.
# Per ADR-0016 the script is an external, cacheable file — never inlined.
ASSET_HEAD = (
    '<link rel="stylesheet" href="radar-ui.css">'
    '<script src="radar-ui.js" defer></script>'
)


def _render_daily(papers, date, directions_cfg, archive_dates, manifest):
    order = {"High": 0, "Medium": 1, "Low": 2, "Exclude": 3}
    identity_by_object = {
        id(paper): _public_identity_key(paper, date, position)
        for position, paper in enumerate(papers)
    }
    papers_sorted = sorted(
        papers,
        key=lambda p: (order.get(
                           (p.get("llm") or {}).get("priority") or "Low", 9),
                       p.get("direction", "zzz")),
    )
    cards = []
    for p in papers_sorted:
        d = p.get("direction")
        color = directions_cfg[d]["color"] if d in directions_cfg else "#888"
        cards.append(_paper_card(
            p, color, identity_key=identity_by_object[id(p)]
        ))

    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — {_esc(date)}</title>
{ASSET_HEAD}</head><body>
{_site_nav("archive")}
<main id="main-content">
<div class="eyebrow">发表日期</div>
<h1>{_esc(date)}</h1>
<div class="subtitle">按论文发表日期归档 · 默认显示 High 与 Medium</div>
{_topbar(date, archive_dates)}
{_stats_row(papers, directions_cfg)}
{_direction_tabs(directions_cfg)}
{_priority_filter_bar()}
{_marks_filter_bar()}
{''.join(cards) if cards else '<p style="color:#888">No papers today.</p>'}
{_version_footer(manifest)}
</main>
</body></html>"""


def _nav_row() -> str:
    """ADR-0016 D2/D4/D5 cross-corpus + curation entry points."""
    return ('<div class="rui-navrow">'
            '<a href="high-priority.html">⭐ High-priority (all dates)</a>'
            '<a href="medium-priority.html">Medium-priority (all dates)</a>'
            '<a href="my-marks.html">🔖 My marks</a>'
            '<a href="my-promotes.html">➜ Promote queue</a>'
            '<a href="search.html">🔍 Search</a>'
            '<a href="status.html">📊 Status</a>'
            "</div>")


def _day_count_badge(counts: dict) -> str:
    """V1: priority-count pills. One `.pill .pill--<level>` per non-zero
    level (a 0-count level renders no pill, matching the mockup). Caller
    wraps the result in a `.day-card__pills` / `.month-card__pills` box.
    """
    pills = []
    for key, suffix, mod in (("High", "H", "high"), ("Medium", "M", "medium"),
                             ("Low", "L", "low"), ("Exclude", "X", "exclude")):
        n = counts.get(key, 0)
        if n:
            pills.append(f'<span class="pill pill--{mod}">{n}{suffix}</span>')
    return "".join(pills)


def _month_count_badge(day_counts_in_month: list[dict]) -> str:
    """V1/C1: month aggregate pills — sum each day's priority_counts, then
    reuse _day_count_badge so a month row reads identically to a day row.
    """
    agg: dict = {}
    for c in day_counts_in_month:
        for k in ("High", "Medium", "Low", "Exclude"):
            v = c.get(k, 0)
            if v:
                agg[k] = agg.get(k, 0) + v
    return _day_count_badge(agg)


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def _day_top_paper_data(papers: list[dict]) -> dict | None:
    """V3: extract the Tier 1+2 fields the day-card needs from a day's
    top paper, or None when there is none.

    Top paper = first High in bucket order; if no High, first Medium;
    if neither, None (Low/Exclude-only days stay as a bare head). zh
    summary fields fall back to their en counterparts; empty fields are
    returned empty so the renderer can skip them rather than print "None".
    """
    top = None
    for want in ("High", "Medium"):
        for p in papers:
            if p.get("llm", {}).get("priority") == want:
                top = p
                break
        if top is not None:
            break
    if top is None:
        return None

    llm = top.get("llm", {}) or {}
    zh = llm.get("summary_zh", {}) or {}
    en = llm.get("summary_en", {}) or {}

    def field(name: str) -> str:
        v = zh.get(name) or en.get(name) or ""
        return v.strip() if isinstance(v, str) else ""

    return {
        "title": _trunc(top.get("title") or "", 90),
        "is_high": llm.get("priority") == "High",
        "authors": [a for a in (top.get("authors") or []) if str(a).strip()],
        "direction": top.get("direction", ""),
        "direction_name": top.get("direction_name", ""),
        "venue": (top.get("venue") or "").strip()
        or (top.get("source") or "").strip(),
        "tags": [str(t).strip() for t in (llm.get("tags") or [])
                 if str(t).strip()][:3],
        "motivation": _trunc(field("motivation"), 80),
        "method": field("method"),
        "result": field("result"),
        "validation": field("validation"),
        "relevance_to_user": (llm.get("relevance_to_user") or "").strip(),
    }


def _render_day_card(date, counts, top_data, directions_cfg) -> str:
    """V2/V3: one `.day-card`. Low-quality days (no High/Medium) keep only
    the head (date + pills); otherwise the V3 enrichment block is added.
    """
    counts = counts or {}
    head = (
        '<div class="day-card__head">'
        f'<a class="day-card__date" href="{_esc(date)}.html">{_esc(date)}</a>'
        f'<div class="day-card__pills">{_day_count_badge(counts)}</div>'
        "</div>"
    )
    low_quality = (counts.get("High", 0) + counts.get("Medium", 0)) == 0
    if low_quality or not top_data:
        return f'<article class="day-card day-card--low-quality">{head}</article>'

    td = top_data
    star = "★ " if td["is_high"] else ""

    a = td["authors"]
    authors = (", ".join(_esc(x) for x in a[:2]) + " et al.") if len(a) > 2 \
        else ", ".join(_esc(x) for x in a)
    color = directions_cfg.get(td["direction"], {}).get("color", "#888")
    dpill = (f'<span class="direction-pill" '
             f'style="background:{color}20;color:{color}">'
             f'{_esc(td["direction_name"])}</span>') if td["direction_name"] else ""
    meta_bits = [b for b in (authors, dpill) if b]
    meta = (f'<div class="day-card__meta">{" · ".join(meta_bits)}</div>'
            if meta_bits else "")

    chips = ""
    if td["venue"]:
        chips += f'<span class="venue">{_esc(td["venue"])}</span>'
    chips += "".join(f'<span class="tag">#{_esc(t)}</span>' for t in td["tags"])
    tags = f'<div class="day-card__tags">{chips}</div>' if chips else ""

    motivation = (
        '<div class="day-card__motivation">'
        f'<span class="motivation-label">💡</span> {_esc(td["motivation"])}</div>'
    ) if td["motivation"] else ""

    rows = [f'<div><b>{lbl}</b>: {_esc(td[k])}</div>'
            for lbl, k in (("方法", "method"), ("结果", "result"),
                           ("验证", "validation"), ("相关性", "relevance_to_user"))
            if td[k]]
    expand = ('<details class="day-card__expand"><summary>Read more</summary>'
              + "".join(rows) + "</details>") if rows else ""

    top = (
        '<div class="day-card__top">'
        f'<div class="day-card__title">{star}{_esc(td["title"])}</div>'
        f'{meta}{tags}{motivation}{expand}</div>'
    )
    return f'<article class="day-card">{head}{top}</article>'


def _month_topbar(month_key: str, archive_months: list[str], n_days: int) -> str:
    """V2/C1: month-page header — back-to-calendar + prev/next month nav."""
    months = sorted(archive_months)
    try:
        idx = months.index(month_key)
    except ValueError:
        idx = len(months) - 1
    prev_m = months[idx - 1] if idx > 0 else None
    next_m = months[idx + 1] if idx < len(months) - 1 else None
    prev_btn = (f'<a class="month-topbar__nav" href="month-{prev_m}.html">← {prev_m}</a>'
                if prev_m else
                '<span class="month-topbar__nav month-topbar__nav--disabled">← oldest</span>')
    next_btn = (f'<a class="month-topbar__nav" href="month-{next_m}.html">{next_m} →</a>'
                if next_m else
                '<span class="month-topbar__nav month-topbar__nav--disabled">latest →</span>')
    return (
        '<div class="month-topbar">'
        '<a class="month-topbar__back" href="archive.html">← 返回归档</a>'
        f'{prev_btn}'
        f'<span class="month-topbar__title">{_esc(month_key)} · {n_days} day(s)</span>'
        f'{next_btn}</div>'
    )


def _render_month_page(month_key, day_dates, day_counts, day_papers_full,
                       archive_months, directions_cfg):
    """V2/V3 (was C1/A3): docs/month-YYYY-MM.html — a responsive grid of
    day-cards, newest first. `day_papers_full` maps a bucket date to its
    full v2 papers list so the card renderer pulls title/authors/tags/
    motivation/summary on its own (memory budget acknowledged in build()).
    """
    cards = []
    for d in sorted(day_dates, reverse=True):
        c = day_counts.get(d, {})
        top_data = _day_top_paper_data(day_papers_full.get(d, []))
        cards.append(_render_day_card(d, c, top_data, directions_cfg))
    grid = "".join(cards)
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — {_esc(month_key)}</title>
{ASSET_HEAD}</head><body>
{_site_nav("archive")}
<main id="main-content" class="container">
<div class="eyebrow">月份归档</div>
<h1>{_esc(month_key)}</h1>
<div class="subtitle">{len(day_dates)} 个发表日期 · 卡片展示当日最高等级论文</div>
{_month_topbar(month_key, archive_months, len(day_dates))}
<div class="day-grid">{grid}</div>
</main>
</body></html>"""


def _render_archive(months, month_counts: dict | None = None,
                    directions_cfg: dict | None = None,
                    current_month: str | None = None):
    """Publication-date archive grouped by year, with future dates separated."""
    month_counts = month_counts or {}
    n_directions = len(directions_cfg) if directions_cfg else 0

    def month_card(mk: str) -> str:
        per_day = month_counts.get(mk, [])
        hm = sum(c.get("High", 0) + c.get("Medium", 0) for c in per_day)
        cls = " month-card--low-quality" if hm == 0 else ""
        return (
            f'<a class="month-card{cls}" href="month-{mk}.html">'
            f'<div class="month-card__label">{_esc(mk)}</div>'
            f'<div class="month-card__pills">{_month_count_badge(per_day)}</div>'
            "</a>"
        )

    ordered = sorted(months, reverse=True)
    future = [m for m in ordered if current_month and m > current_month]
    regular = [m for m in ordered if m not in set(future)]
    by_year: dict[str, list[str]] = {}
    for month in regular:
        by_year.setdefault(month[:4], []).append(month)
    active_year = (current_month or (regular[0] if regular else ""))[:4]
    year_sections = []
    for year in sorted(by_year, reverse=True):
        opened = " open" if year == active_year else ""
        cards = "".join(month_card(month) for month in by_year[year])
        year_sections.append(
            f'<details class="archive-year"{opened}><summary>{year}</summary>'
            f'<div class="month-grid">{cards}</div></details>'
        )
    future_section = ""
    if future:
        future_section = (
            '<details class="archive-year archive-year--future">'
            '<summary>未来或低精度发表日期</summary>'
            '<p>这些月份来自出版源元数据，不代表 Radar 的发现时间。</p>'
            f'<div class="month-grid">{"".join(month_card(m) for m in future)}</div>'
            '</details>'
        )

    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — 归档</title>
{ASSET_HEAD}</head><body>
{_site_nav("archive")}
<main id="main-content" class="container">
<div class="eyebrow">Publication archive</div>
<h1>发表日期归档</h1>
<div class="subtitle">覆盖 {n_directions} 个研究方向 · 等级计数基于 canonical 唯一论文</div>
<p class="page-intro">选择年份和月份查看论文；灰色月份没有 High 或 Medium。</p>
{"".join(year_sections)}
{future_section}
</main>
</body></html>"""


def _recent_valid_runs(data_dir: pathlib.Path, limit: int = 7) -> list[tuple[str, dict]]:
    """Return newest successful/partial daily manifests."""
    manifests_dir = data_dir / "manifests"
    runs: list[tuple[str, dict]] = []
    if not manifests_dir.exists():
        return runs
    for path in sorted(manifests_dir.glob("20*.json"), reverse=True):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("run_status") not in {"success", "partial_success"}:
            continue
        runs.append((path.stem, manifest))
        if len(runs) == limit:
            break
    return runs


def _render_workbench(recent_runs: list[tuple[str, dict]],
                      buckets: dict[str, list[dict]], directions_cfg: dict,
                      corpus_stats: corpus_view.CorpusStats) -> str:
    """Root workbench: papers first seen in the seven latest valid runs."""
    run_dates = [date for date, _manifest in recent_runs]
    identity_by_object = {
        id(paper): _public_identity_key(paper, bucket_date, position)
        for bucket_date, papers in buckets.items()
        for position, paper in enumerate(papers)
    }
    papers_by_run: dict[str, list[tuple[str, dict]]] = {
        date: [] for date in run_dates
    }
    for bucket_date, papers in buckets.items():
        for paper in papers:
            first_seen = (paper.get("first_seen_at") or "")[:10]
            if first_seen in papers_by_run:
                papers_by_run[first_seen].append((bucket_date, paper))

    priority_order = {"High": 0, "Medium": 1, "Low": 2, "Exclude": 3}
    all_recent = [
        paper for dated in papers_by_run.values() for _bucket, paper in dated
    ]
    sections = []
    for run_date, manifest in recent_runs:
        dated = sorted(
            papers_by_run.get(run_date, []),
            key=lambda dp: (
                priority_order.get((dp[1].get("llm") or {}).get("priority"), 9),
                dp[0], dp[1].get("title", ""),
            ),
        )
        actionable = [dp for dp in dated
                      if (dp[1].get("llm") or {}).get("priority")
                      in {"High", "Medium"}]
        lower = [dp for dp in dated if dp not in actionable]

        def cards(items):
            output = []
            for bucket_date, paper in items:
                direction = paper.get("direction")
                color = directions_cfg.get(direction, {}).get("color", "#667085")
                output.append(_paper_card(
                    paper, color, daily_link_date=bucket_date,
                    identity_key=identity_by_object[id(paper)]
                ))
            return "".join(output)

        priority_counts = corpus_view.priority_counts(
            [paper for _bucket, paper in dated]
        )
        counts = _day_count_badge(priority_counts)
        status = manifest.get("run_status", "success")
        quality_flags = manifest.get("quality_flags") or []
        warning = ""
        if quality_flags:
            warning = (
                '<div class="run-warning"><b>运行提示：</b> '
                + "、".join(_esc(flag) for flag in quality_flags) + "</div>"
            )
        lower_html = ""
        if lower:
            lower_html = (
                '<details class="workbench-lower"><summary>查看 Low / Exclude '
                f'（{len(lower)} 篇）</summary>{cards(lower)}</details>'
            )
        empty = '<p class="empty-state">本次运行没有 High 或 Medium 论文。</p>' \
            if not actionable else ""
        sections.append(
            '<section class="run-section">'
            f'<div class="run-section__head"><div><div class="eyebrow">{_esc(status)}</div>'
            f'<h2>{_esc(run_date)} 新发现</h2></div>'
            f'<div class="run-section__counts">{counts}</div></div>'
            f'{warning}{empty}{cards(actionable)}{lower_html}</section>'
        )

    latest = recent_runs[0][1] if recent_runs else {}
    latest_date = recent_runs[0][0] if recent_runs else "暂无运行记录"
    latest_flags = latest.get("quality_flags") or []
    health_class = " health-summary--warning" if latest_flags else ""
    body = "".join(sections) or (
        '<div class="empty-state"><h2>尚无可展示的最新运行</h2>'
        '<p>工作台将在下一次成功日跑后自动填充。</p></div>'
    )
    stats = _stats_row(all_recent, directions_cfg)
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — 今日工作台</title>
{ASSET_HEAD}</head><body>
{_site_nav("today")}
<main id="main-content" class="container">
<div class="workbench-hero">
  <div><div class="eyebrow">Research triage</div>
  <h1>最近 7 次运行</h1>
  <p class="subtitle">按 Radar 首次发现时间汇总；默认展开 High 与 Medium 的完整中文摘要。</p></div>
  <a class="health-summary{health_class}" href="status.html">
    <span>最近运行</span><strong>{_esc(latest_date)}</strong>
    <small>{' · '.join(_esc(x) for x in latest_flags) if latest_flags else '运行正常'}</small>
  </a>
</div>
{stats}
<div class="corpus-note">全库 {_esc(corpus_stats.unique_total)} 篇唯一论文 · 抑制 {_esc(corpus_stats.duplicates_suppressed)} 条重复来源记录</div>
{body}
</main>
</body></html>"""


def _queue_record(bucket_date: str, paper: dict, position: int,
                  directions_cfg: dict) -> dict:
    llm = paper.get("llm") or {}
    direction = paper.get("direction") or ""
    identity = _public_identity_key(paper, bucket_date, position)
    return {
        "identity_key": identity,
        "anchor": _anchor_id(identity),
        "date": bucket_date,
        "title": paper.get("title") or "",
        "authors": (paper.get("authors") or [])[:5],
        "venue": paper.get("venue") or "",
        "source": paper.get("source") or "",
        "doi": paper.get("doi") or "",
        "url": paper.get("url") or "",
        "direction": direction,
        "direction_name": paper.get("direction_name") or
                          directions_cfg.get(direction, {}).get("display_name", direction),
        "direction_color": directions_cfg.get(direction, {}).get("color", "#667085"),
        "priority": llm.get("priority") or "",
        "relevance_level": llm.get("relevance_level") or "",
        "read_action": llm.get("read_action") or "",
        "validation_kind": llm.get("validation_kind") or "",
        "flags": llm.get("flags") or {},
        "relevance_to_user": llm.get("relevance_to_user") or "",
        "why_not_core": llm.get("why_not_core") or "",
        "summary_zh": llm.get("summary_zh") or {},
        "tags": llm.get("tags") or [],
        "first_seen_at": paper.get("first_seen_at") or "",
    }


def _corpus_generated_at(buckets: dict[str, list[dict]]) -> str:
    """Return a reproducible corpus cutoff for generated JSON manifests."""
    first_seen = [
        str(paper.get("first_seen_at") or "")
        for papers in buckets.values() for paper in papers
        if paper.get("first_seen_at")
    ]
    if first_seen:
        return max(first_seen)
    dates = [date for date, papers in buckets.items() if papers]
    return f"{max(dates)}T00:00:00Z" if dates else ""


def _build_queue_index(docs_dir: pathlib.Path,
                       buckets: dict[str, list[dict]], directions_cfg: dict,
                       corpus_stats: corpus_view.CorpusStats) -> dict:
    """Write priority/year queue shards for High and Medium papers."""
    grouped: dict[str, dict[str, list[dict]]] = {
        "High": {}, "Medium": {},
    }
    for bucket_date, papers in buckets.items():
        for position, paper in enumerate(papers):
            priority = (paper.get("llm") or {}).get("priority")
            if priority not in grouped:
                continue
            year = bucket_date[:4]
            grouped[priority].setdefault(year, []).append(
                _queue_record(bucket_date, paper, position, directions_cfg)
            )

    priorities = {}
    for priority, years_data in grouped.items():
        year_counts = {}
        for year, records in years_data.items():
            records.sort(key=lambda record: (
                record["date"], record["title"]
            ), reverse=True)
            filename = f"queue-{priority.lower()}-{year}.json"
            (docs_dir / filename).write_text(
                json.dumps(records, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            year_counts[year] = len(records)
        priorities[priority] = {
            "total": sum(year_counts.values()),
            "years": {year: year_counts[year]
                      for year in sorted(year_counts, reverse=True)},
        }

    manifest = {
        "schema_version": 1,
        "generated_at": _corpus_generated_at(buckets),
        **corpus_stats.as_dict(),
        "priorities": priorities,
        "directions": {
            key: {"name": value.get("display_name", key),
                  "color": value.get("color", "#667085")}
            for key, value in directions_cfg.items()
        },
    }
    (docs_dir / "queue-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest


def _render_queue_page() -> str:
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — 论文队列</title>
{ASSET_HEAD}<script src="radar-queue.js" defer></script></head><body>
{_site_nav("queue")}
<main id="main-content" class="container">
<div class="eyebrow">Canonical corpus queue</div>
<h1>论文队列</h1>
<p class="subtitle">High 与 Medium 共用一个队列；完整中文摘要按年份加载。</p>
<div class="queue-toolbar" aria-label="队列筛选">
  <div class="segmented" id="queue-priority">
    <button type="button" data-priority="High" class="is-active">High</button>
    <button type="button" data-priority="Medium">Medium</button>
  </div>
  <label>方向<select id="queue-direction"><option value="">全部方向</option></select></label>
  <label>年份<select id="queue-year"><option value="">全部年份</option></select></label>
  <label>相关性<select id="queue-relevance"><option value="">全部</option><option>Direct</option><option>Transferable</option><option>Peripheral</option></select></label>
</div>
<div class="queue-status" id="queue-status" aria-live="polite">正在加载队列…</div>
<div id="queue-results"></div>
<button type="button" class="rui-btn queue-more" id="queue-more" hidden>加载更多</button>
</main>
</body></html>"""


def _render_status_page(docs_dir, data_dir):
    """Generate docs/status.html showing recent run history from manifests."""
    import json

    manifests_dir = data_dir / "manifests"
    if not manifests_dir.exists():
        return

    # Collect all manifests, newest first
    manifests = sorted(manifests_dir.glob("20*.json"), reverse=True)[:14]  # last 14 days

    rows = []
    for m_path in manifests:
        try:
            m = json.loads(m_path.read_text())
        except Exception:
            continue
        date = m_path.stem
        counts = m.get("counts", {})
        zotero = m.get("zotero", {})
        run_status = m.get("run_status", "—")
        quality_flags = m.get("quality_flags", [])
        commit = (m.get("git_commit") or "")[:7]

        flags_html = "".join(
            f'<span class="qflag">{_esc(q)}</span>' for q in quality_flags
        ) or '<span class="ok">—</span>'

        rows.append(f"""
        <tr>
          <td><a href="{_esc(date)}.html">{_esc(date)}</a></td>
          <td><span class="run-status run-status--{_esc(run_status)}">{_esc(run_status)}</span></td>
          <td>{counts.get("fetched", "—")}</td>
          <td>{counts.get("after_dedup", "—")}</td>
          <td>{counts.get("after_routing", "—")}</td>
          <td>{counts.get("priority_counts", {}).get("High", "—")}/{counts.get("priority_counts", {}).get("Medium", "—")}</td>
          <td>{zotero.get("created", "—")}/{zotero.get("eligible", "—")}</td>
          <td>{flags_html}</td>
          <td><code>{_esc(commit)}</code></td>
        </tr>""")

    html = f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — 运行状态</title>
{ASSET_HEAD}</head><body>
{_site_nav("admin")}
<main id="main-content" class="container">
<div class="eyebrow">System health</div>
<h1>运行状态</h1>
<div class="subtitle">最近 14 次日跑 · 根据 manifest 自动生成</div>
<div class="table-scroll"><table class="status-table">
<thead>
<tr>
  <th>日期</th>
  <th>状态</th>
  <th>抓取</th>
  <th>去重后</th>
  <th>路由后</th>
  <th>High/Med</th>
  <th>Zotero ✓/eligible</th>
  <th>质量提示</th>
  <th>提交</th>
</tr>
</thead>
<tbody>
{''.join(rows) if rows else '<tr><td colspan="9">暂无 manifest。</td></tr>'}
</tbody>
</table></div>

<div class="legend">
<h2>状态说明</h2>
<ul>
<li><b>success</b>：正常运行并写入数据。</li>
<li><b>partial_success</b>：部分数据源或下游操作异常，但保留了有效结果。</li>
<li><b>suspicious_empty / failed</b>：质量闸门中止写入或运行失败。</li>
</ul>
</div>
</main>
</body></html>"""

    out = docs_dir / "status.html"
    out.write_text(html, encoding="utf-8")


def _build_search_index(docs_dir, data_dir, canonical_buckets=None,
                        corpus_stats=None):
    """Build lightweight metadata and opt-in deep-content yearly shards."""
    import json as _json

    daily_dir = data_dir / "daily"
    if not daily_dir.exists():
        return 0

    if canonical_buckets is None:
        raw_buckets = {}
        for jpath in sorted(daily_dir.glob("20*.json")):
            raw_buckets[jpath.stem], _meta = _load_papers_v2_or_v1(jpath)
        canonical_buckets, corpus_stats = corpus_view.canonicalize_buckets(
            raw_buckets
        )

    by_year: dict[str, list] = {}
    deep_by_year: dict[str, list] = {}
    for date, papers in sorted(canonical_buckets.items()):
        if not papers:
            continue
        for position, p in enumerate(papers):
            llm = p.get("llm", {}) or {}
            s_zh = llm.get("summary_zh", {}) or {}
            key_terms = llm.get("key_terms", []) or []
            term_texts = []
            for term in key_terms:
                if isinstance(term, dict):
                    text = " · ".join(
                        str(term.get(key) or "").strip()
                        for key in ("en", "zh") if term.get(key)
                    )
                else:
                    text = str(term).strip()
                if text:
                    term_texts.append(text)
            tags = llm.get("tags", []) or []
            authors = p.get("authors", []) or []
            deep_parts = [
                p.get("abstract", "")[:500],
                llm.get("relevance_to_user", ""),
                llm.get("why_not_core", ""),
                " ".join(s_zh.values()) if isinstance(s_zh, dict) else "",
                " ".join(term_texts),
            ]
            identity = _public_identity_key(p, date, position)
            record = {
                "identity_key": identity,
                "date": date,
                "title": p.get("title", "")[:200],
                "authors": ", ".join(authors[:3]) +
                           (" et al." if len(authors) > 3 else ""),
                "venue": p.get("venue", "")[:80],
                "direction": p.get("direction", ""),
                "direction_name": p.get("direction_name", ""),
                "priority": llm.get("priority", ""),
                "relevance_level": llm.get("relevance_level", ""),
                "tags": tags[:2],
                "term": term_texts[0] if term_texts else "",
            }
            year = ((p.get("date") or date) or "")[:4]
            by_year.setdefault(year, []).append(record)
            deep_by_year.setdefault(year, []).append({
                "identity_key": identity,
                "deep_blob": " ".join(part for part in deep_parts if part).lower(),
            })

    years = sorted(by_year.keys(), reverse=True)
    counts = {y: len(by_year[y]) for y in years}
    total = sum(counts.values())

    for y in years:
        (docs_dir / f"search-index-{y}.json").write_text(
            _json.dumps(by_year[y], ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8"
        )
        (docs_dir / f"search-deep-{y}.json").write_text(
            _json.dumps(deep_by_year[y], ensure_ascii=False,
                        separators=(",", ":")),
            encoding="utf-8"
        )

    manifest = {
        "schema_version": 2,
        "years": years,
        "counts": counts,
        "deep_counts": {year: len(deep_by_year[year]) for year in years},
        "total": total,
        "meta_pattern": "search-index-{year}.json",
        "deep_pattern": "search-deep-{year}.json",
        "generated_at": _corpus_generated_at(canonical_buckets),
    }
    if corpus_stats is not None:
        manifest.update(corpus_stats.as_dict())
    (docs_dir / "search-index-manifest.json").write_text(
        _json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    return total


def _render_search_page(docs_dir, directions_cfg: dict):
    """ADR-0027 metadata-first search with opt-in year-scoped deep search."""
    direction_options = "".join(
        f'<option value="{_esc(key)}">{_esc(cfg.get("display_name", key))}</option>'
        for key, cfg in directions_cfg.items()
    )
    html = f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — 搜索</title>
{ASSET_HEAD}<script src="radar-search.js" defer></script></head><body>
{_site_nav("search")}
<main id="main-content" class="container">
<div class="eyebrow">Metadata-first corpus search</div>
<h1>搜索 10 万篇论文</h1>
<p class="subtitle">默认搜索标题、作者、期刊、标签与首要术语；完整术语、摘要和中文总结按年份深搜。</p>
<label class="search-box">
  <span>关键词</span>
  <input id="search-query" type="search" autocomplete="off"
         placeholder="输入标题、作者、标签或术语…" autofocus>
</label>
<div class="search-toolbar" aria-label="搜索筛选">
  <label>方向<select id="search-direction"><option value="">全部方向</option>{direction_options}</select></label>
  <label>等级<select id="search-priority"><option value="">全部等级</option><option>High</option><option>Medium</option><option>Low</option><option>Exclude</option></select></label>
  <label>相关性<select id="search-relevance"><option value="">全部</option><option>Direct</option><option>Transferable</option><option>Peripheral</option></select></label>
  <label>发表年份<select id="search-year"><option value="">全部年份</option></select></label>
</div>
<div class="deep-search-control">
  <label><input id="search-deep-toggle" type="checkbox"> 搜索摘要、中文总结与相关性说明</label>
  <label>深搜年份<select id="search-deep-year"><option value="">请选择年份</option></select></label>
</div>
<div id="search-status" class="search-status" aria-live="polite">正在载入轻量索引…</div>
<div id="search-results" class="search-results"></div>
<button type="button" id="search-more" class="rui-btn search-more" hidden>加载更多结果</button>
</main>
</body></html>"""
    (docs_dir / "search.html").write_text(html, encoding="utf-8")


def _page_shell(title: str, subtitle: str, body: str,
                active: str = "") -> str:
    """Shared static page shell."""
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — {_esc(title)}</title>
{ASSET_HEAD}</head><body>
{_site_nav(active)}
<main id="main-content" class="container">
<h1>{_esc(title)}</h1>
<div class="subtitle">{_esc(subtitle)}</div>
{body}
</main>
</body></html>"""


def _render_cross_corpus_page(kind: str, dated_papers: list, directions_cfg: dict) -> str:
    """ADR-0016 D2: flat list of every `kind`-priority paper, newest first.

    `dated_papers` is a list of (bucket_date, paper); bucket_date is the
    daily-file stem so the per-card deep link lands on the right page.
    """
    dated_papers = sorted(dated_papers, key=lambda dp: dp[0], reverse=True)
    cards = []
    for bucket_date, p in dated_papers:
        d = p.get("direction")
        color = directions_cfg[d]["color"] if d in directions_cfg else "#888"
        cards.append(_paper_card(p, color, daily_link_date=bucket_date))
    body = (f'<p style="color:#666;font-size:13px">'
            f'{len(dated_papers)} {_esc(kind)}-priority papers across the '
            f'whole corpus, newest first.</p>'
            + ("".join(cards) if cards
               else f'<p style="color:#888">No {_esc(kind)}-priority papers.</p>'))
    return _page_shell(f"{kind}-priority", "All dates · all directions", body)


def _render_my_marks_page() -> str:
    """ADR-0016 D4: localStorage marks listing + export-to-JSON escape hatch."""
    body = """
<p style="color:#666;font-size:13px">Reading marks and notes are stored only in
this browser (ADR-0016 §2 D4 — no sync, no server). Use Export for a backup or
to hand them elsewhere.</p>
<p><button type="button" class="rui-btn" id="rui-export-marks">⬇ Export marks to JSON</button></p>
<div id="rui-marks-list"></div>"""
    return _page_shell("My marks", "localStorage-backed reading trail", body)


def _render_my_promotes_page() -> str:
    """ADR-0016 D5.A: the localStorage promote queue + copy-out (no git write)."""
    body = """
<p style="color:#666;font-size:13px">Papers you queued with "Send to
lit-system". This is the D5.A manual hand-off: copy the JSON and paste-import it
on the lit-system side. No automatic git write-back (D5.B is out of scope).</p>
<p>
  <button type="button" class="rui-btn" id="rui-copy-promotes">Copy all to clipboard as JSON</button>
  <button type="button" class="rui-btn rui-secondary" id="rui-clear-promotes">Clear queue</button>
</p>
<div id="rui-promote-list"></div>"""
    return _page_shell("Promote queue", "Pending lit-system hand-off", body)


def _render_library_page() -> str:
    body = """
<div class="library-grid">
  <section id="marks" class="library-panel">
    <div class="eyebrow">Local reading trail</div>
    <h2>我的标记与笔记</h2>
    <p>仅保存在当前浏览器。新标记会同时保存标题、日期和方向；旧记录保持兼容。</p>
    <button type="button" class="rui-btn" id="rui-export-marks">导出标记 JSON</button>
    <div id="rui-marks-list"></div>
  </section>
  <section id="promote" class="library-panel">
    <div class="eyebrow">lit-system hand-off</div>
    <h2>待导入队列</h2>
    <p>复制 JSON 后在 lit-system 侧手动导入；不会从浏览器直接写回 Git。</p>
    <button type="button" class="rui-btn" id="rui-copy-promotes">复制全部 JSON</button>
    <button type="button" class="rui-btn rui-secondary" id="rui-clear-promotes">清空队列</button>
    <div id="rui-promote-list"></div>
  </section>
</div>"""
    return _page_shell("资料库", "浏览器本地的阅读标记、笔记与交接队列",
                       body, active="library")


def _redirect_page(title: str, target: str) -> str:
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url={_esc(target)}">
<title>{_esc(title)}</title>{ASSET_HEAD}</head><body>
<main class="redirect-page"><p>页面已迁移：<a href="{_esc(target)}">继续前往</a></p></main>
</body></html>"""


def _copy_static_assets(docs_dir: pathlib.Path) -> None:
    """Copy the dependency-free browser bundles into docs/."""
    static_dir = pathlib.Path(__file__).resolve().parent / "static"
    for name in ("radar-ui.css", "radar-ui.js", "radar-queue.js",
                 "radar-search.js", "radar-search-worker.js"):
        src = static_dir / name
        if src.exists():
            (docs_dir / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )


def _priority_counts_for(papers: list, meta: dict) -> dict:
    """Return counts derived from the visible papers, never stale metadata."""
    return corpus_view.priority_counts(papers)


def build(docs_dir, directions_cfg, manifest=None, touched_dates=None,
          data_dir=None):
    """Render every per-publication-date HTML page from disk, refresh index.

    ADR-0015 §4.5: under v2 a single radar run touches many publication-date
    files. There is no single "today's page" anymore — we re-render every
    archive page from disk so navigation lists stay coherent. `touched_dates`
    is the set of bucket dates this run actually modified; pages for those
    dates get the run manifest footer attached.
    """
    docs_dir = pathlib.Path(docs_dir)
    data_dir = (pathlib.Path(data_dir) if data_dir is not None
                else docs_dir.parent / "data")
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_daily_dir = data_dir / "daily"
    archive = sorted(p.stem for p in data_daily_dir.glob("20*.json")) if data_daily_dir.exists() else []
    touched = set(touched_dates or ())

    # Load once, then create a strict identity-key canonical site view. Raw
    # bucket records remain untouched on disk; only public rendering suppresses
    # duplicate DOI/arXiv identities.
    raw_papers_by_date: dict[str, list] = {}
    meta_by_date: dict[str, dict] = {}
    for hist_date in archive:
        papers, meta = _load_papers_v2_or_v1(
            data_daily_dir / f"{hist_date}.json"
        )
        raw_papers_by_date[hist_date] = papers
        meta_by_date[hist_date] = meta

    day_papers_full, corpus_stats = corpus_view.canonicalize_buckets(
        raw_papers_by_date
    )
    if corpus_stats.duplicates_suppressed:
        print("  canonical corpus: "
              f"{corpus_stats.unique_total} unique / "
              f"{corpus_stats.raw_total} raw "
              f"({corpus_stats.duplicates_suppressed} duplicates suppressed)")

    # Accumulated during the archive render pass:
    #   day_counts  -> ADR-0016 D1 calendar badges
    #   high/medium -> ADR-0016 D2 cross-corpus pages
    day_counts: dict[str, dict] = {}
    # V3: date -> full v2 papers list, consumed by the month-page day-card
    # renderer. ~3554 small JSON files held simultaneously (<200MB RAM,
    # acceptable per the visual-refresh implementation note).
    for hist_date in archive:
        hist_json = data_daily_dir / f"{hist_date}.json"
        hist_html = docs_dir / f"{hist_date}.html"
        if not hist_json.exists():
            continue
        try:
            hist_papers = day_papers_full.get(hist_date, [])
            _meta = meta_by_date.get(hist_date, {})
            raw_counts = corpus_view.priority_counts(
                raw_papers_by_date.get(hist_date, [])
            )
            stored_counts = (_meta.get("counts") or {}).get("priority_counts")
            stored_normalized = {
                key: int((stored_counts or {}).get(key, 0))
                for key in corpus_view.PRIORITIES
            }
            if stored_counts is not None and stored_normalized != raw_counts:
                print(f"  stale priority_counts: {hist_json.name} "
                      f"stored={stored_counts} computed={raw_counts}")
            day_counts[hist_date] = _priority_counts_for(hist_papers, _meta)
            page_manifest = manifest if hist_date in touched else None
            hist_html.write_text(
                _clean_html(_render_daily(
                    hist_papers, hist_date, directions_cfg, archive,
                    page_manifest,
                )),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"  (skip re-render {hist_date}: {e})")

    # CHANGE C1: bucket archive dates by month, then render the month-list
    # index + one month-YYYY-MM.html page per month present in data/daily/.
    months: dict[str, list[str]] = {}
    for d in archive:
        months.setdefault(d[:7], []).append(d)
    month_counts: dict[str, list[dict]] = {
        mk: [day_counts.get(d, {}) for d in days] for mk, days in months.items()
    }
    archive_months = sorted(months)

    recent_runs = _recent_valid_runs(data_dir)
    current_month = recent_runs[0][0][:7] if recent_runs else None

    # ADR-0027: root = discovery-time workbench; publication archive moves to
    # a dedicated URL and keeps all existing month/day URLs stable.
    (docs_dir / "index.html").write_text(
        _clean_html(_render_workbench(
            recent_runs, day_papers_full, directions_cfg, corpus_stats,
        )),
        encoding="utf-8",
    )
    (docs_dir / "archive.html").write_text(
        _render_archive(archive_months, month_counts, directions_cfg,
                        current_month=current_month),
        encoding="utf-8",
    )
    for mk, days in months.items():
        (docs_dir / f"month-{mk}.html").write_text(
            _render_month_page(mk, days, day_counts, day_papers_full,
                                archive_months, directions_cfg),
            encoding="utf-8",
        )

    # ADR-0027: one lazy High/Medium queue replaces multi-megabyte flat HTML.
    _build_queue_index(docs_dir, day_papers_full, directions_cfg, corpus_stats)
    (docs_dir / "queue.html").write_text(
        _render_queue_page(), encoding="utf-8"
    )
    (docs_dir / "high-priority.html").write_text(
        _redirect_page("High-priority", "queue.html?priority=High"),
        encoding="utf-8",
    )
    (docs_dir / "medium-priority.html").write_text(
        _redirect_page("Medium-priority", "queue.html?priority=Medium"),
        encoding="utf-8",
    )

    # ADR-0016 D4/D5: one library page; old URLs stay as redirects.
    (docs_dir / "library.html").write_text(
        _render_library_page(), encoding="utf-8"
    )
    (docs_dir / "my-marks.html").write_text(
        _redirect_page("My marks", "library.html#marks"), encoding="utf-8")
    (docs_dir / "my-promotes.html").write_text(
        _redirect_page("Promote queue", "library.html#promote"),
        encoding="utf-8")
    _copy_static_assets(docs_dir)

    # W1.x: also render run status page from manifests
    if data_dir.exists():
        _render_status_page(docs_dir, data_dir)
        n_indexed = _build_search_index(
            docs_dir, data_dir, day_papers_full, corpus_stats
        )
        if n_indexed:
            _render_search_page(docs_dir, directions_cfg)
