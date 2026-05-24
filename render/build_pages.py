"""Render daily HTML pages with top-bar navigation and version footer."""

from __future__ import annotations
import hashlib
import html
import json
import pathlib
import re


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


PRIORITY_COLOR = {
    "High":    ("#EAF3DE", "#27500A"),
    "Medium":  ("#FAEEDA", "#633806"),
    "Low":     ("#F1EFE8", "#5F5E5A"),
    "Exclude": ("#FCEBEB", "#791F1F"),
}


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _identity_key(p: dict) -> str:
    """ADR-0015 §4.4 dedup key: `doi:<doi>` or `arxiv:<arxiv_id>`.

    Mirrors `pipeline.v2_schema.identity_key` rather than importing it, by
    the same "duplicated, not imported" convention build_pages already uses
    for `_load_papers_v2_or_v1` (keeps the render layer stdlib-only and
    importable without the pipeline package). Papers with neither id get a
    deterministic `noid:` fallback so per-paper marks (ADR-0016 D4) still
    work for the rare id-less paper instead of all colliding on "".
    """
    doi = (p.get("doi") or "").strip()
    if doi:
        return f"doi:{doi}"
    arxiv = (p.get("arxiv_id") or "").strip()
    if arxiv:
        return f"arxiv:{arxiv}"
    seed = f"{p.get('title','')}|{p.get('date','')}".encode("utf-8")
    return "noid:" + hashlib.sha1(seed).hexdigest()[:12]


def _anchor_id(identity_key: str) -> str:
    """URL/HTML-fragment-safe form of an identity key for in-page anchors."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", identity_key)


def _card_tools(p: dict) -> str:
    """ADR-0016 D4 (mark + note) and D5 (promote) per-card controls.

    Rendered statically; all behaviour is wired client-side by
    render/static/radar-ui.js reading the card's `data-identity-key`.
    """
    idkey = _identity_key(p)
    name = f"rui-mark-{_anchor_id(idkey)}"
    states = [
        ("to-read", "to-read"), ("read", "read"),
        ("interesting", "interesting"), ("ignore", "ignore"),
    ]
    radios = "".join(
        f'<label class="m-{val}"><input type="radio" class="rui-mark-radio" '
        f'name="{_esc(name)}" value="{val}">{_esc(lbl)}</label>'
        for val, lbl in states
    )
    return f"""
  <div class="rui-card-tools">
    <span class="rui-mark-group"><b>Mark:</b> {radios}</span>
    <button type="button" class="rui-note-btn">Note</button>
    <button type="button" class="rui-promote-btn">Send to lit-system</button>
    <div class="rui-note-wrap">
      <textarea class="rui-note-ta" placeholder="Private note (saved on blur, this browser only)"></textarea>
    </div>
  </div>"""


def _paper_card(p: dict, dir_color: str, daily_link_date: str | None = None) -> str:
    llm = p.get("llm", {})
    priority = llm.get("priority", "Low")
    bg, fg = PRIORITY_COLOR.get(priority, PRIORITY_COLOR["Low"])
    s = llm.get("summary_zh", {})
    s_en = llm.get("summary_en", {})
    key_terms = llm.get("key_terms", [])
    flags = llm.get("flags", {})
    relevance_level = llm.get("relevance_level", "")
    read_action = llm.get("read_action", "")
    why_not_core = llm.get("why_not_core", "")
    validation_kind = llm.get("validation_kind", "")

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
    tags_html = " ".join(f'<span class="tag">{_esc(t)}</span>' for t in llm.get("tags", []))

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

    idkey = _identity_key(p)
    daily_link = ""
    if daily_link_date:
        daily_link = (f'<a class="rui-link-tool" '
                      f'href="{_esc(daily_link_date)}.html#{_anchor_id(idkey)}">'
                      f'→ {_esc(daily_link_date)} page</a>')

    return f"""
<article class="paper" id="{_anchor_id(idkey)}" data-direction="{_esc(p.get('direction',''))}" data-priority="{_esc(priority)}" data-identity-key="{_esc(idkey)}" data-title="{_esc(p.get('title',''))}" data-date="{_esc(p.get('date',''))}">
  <div class="paper-head">
    <span class="priority" style="background:{bg};color:{fg}">{_esc(priority)}</span>
    <span class="direction-pill" style="background:{dir_color}20;color:{dir_color}">{_esc(p.get('direction_name',''))}</span>
    <span class="source">{_esc(p.get('source',''))}</span>
    {f'<span class="relevance-level lvl-{relevance_level.lower()}">{_esc(relevance_level)}</span>' if relevance_level else ''}
    {f'<span class="read-action act-{read_action.lower().replace(" ", "-")}">{_esc(read_action)}</span>' if read_action else ''}
    {f'<span class="validation-kind">{_esc(validation_kind)}</span>' if validation_kind else ''}
    {flag_html}
  </div>
  <h3 class="paper-title">{_esc(p.get('title',''))}</h3>
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
    <summary>English summary &amp; terms</summary>
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
  {_card_tools(p)}
</article>"""


def _stats_row(papers: list[dict], directions_cfg: dict) -> str:
    total = {"High": 0, "Medium": 0, "Low": 0, "Exclude": 0}
    for p in papers:
        prio = p.get("llm", {}).get("priority", "Low")
        total[prio] = total.get(prio, 0) + 1
    cards = [f'<div class="stat"><div class="stat-label">Total scored</div><div class="stat-val">{sum(total.values())}</div></div>']
    for prio, color in [("High", "#27500A"), ("Medium", "#633806"), ("Low", "#5F5E5A")]:
        cards.append(f'<div class="stat"><div class="stat-label">{prio}</div><div class="stat-val" style="color:{color}">{total[prio]}</div></div>')
    return '<div class="stats">' + "".join(cards) + "</div>"


def _direction_tabs(directions_cfg: dict) -> str:
    tabs = ['<button class="tab active" data-filter="all">All</button>']
    for dkey, dcfg in directions_cfg.items():
        tabs.append(f'<button class="tab" data-filter="{_esc(dkey)}">{_esc(dcfg["display_name"])}</button>')
    return '<div class="tabs">' + "".join(tabs) + "</div>"


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
            '<b>Priority:</b> ' + " ".join(boxes) + "</div>")


def _marks_filter_bar() -> str:
    """ADR-0016 D4: client-side "filter to my marks" checkboxes."""
    opts = [
        ("to-read", "to-read"), ("read", "read"),
        ("interesting", "interesting"), ("ignore", "ignore"),
        ("none", "(no mark)"),
    ]
    boxes = "".join(
        f'<label><input type="checkbox" class="rui-mf-cb" '
        f'value="{val}" checked>{_esc(lbl)}</label>'
        for val, lbl in opts
    )
    return ('<div class="rui-filter-bar" id="rui-marks-filter">'
            '<b>My marks:</b> ' + boxes + "</div>")


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
                if prev_date else '<span class="navbtn disabled">← oldest</span>')
    next_btn = (f'<a class="navbtn" href="{next_date}.html">{next_date} →</a>'
                if next_date else '<span class="navbtn disabled">latest →</span>')

    options = "".join(
        f'<option value="{d}.html"{" selected" if d == date else ""}>{d}</option>'
        for d in reversed(sorted_dates)
    )
    dropdown = f'<select class="archive-select" onchange="if(this.value)window.location.href=this.value">{options}</select>'

    calendar_link = '<a class="navbtn" href="index.html">☀️ Calendar</a>'
    weekly_link = '<a class="navbtn" href="weekly/index.html">📅 Weekly</a>'
    status_link = '<a class="navbtn" href="status.html">📊 Status</a>'
    search_link = '<a class="navbtn" href="search.html">🔍 Search</a>'
    # ADR-0016 D2/D4/D5 entry points, also reachable while browsing a day
    hi_link = '<a class="navbtn" href="high-priority.html">⭐ High</a>'
    marks_link = '<a class="navbtn" href="my-marks.html">🔖 Marks</a>'
    promo_link = '<a class="navbtn" href="my-promotes.html">➜ Promote</a>'

    return (f'<div class="topbar">{prev_btn}{dropdown}{next_btn}'
            f'{calendar_link}{weekly_link}{status_link}{search_link}'
            f'{hi_link}{marks_link}{promo_link}</div>')


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
    papers_sorted = sorted(
        papers,
        key=lambda p: (order.get(p.get("llm", {}).get("priority", "Low"), 9),
                       p.get("direction", "zzz")),
    )
    cards = []
    for p in papers_sorted:
        d = p.get("direction")
        color = directions_cfg[d]["color"] if d in directions_cfg else "#888"
        cards.append(_paper_card(p, color))

    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — {_esc(date)}</title>
<style>{CSS}</style>{ASSET_HEAD}</head><body>
<h1>Research Radar</h1>
<div class="subtitle">{_esc(date)} · AI Bioprinting / Hip Implant / FEA Surrogate / AM Biomedical</div>
{_topbar(date, archive_dates)}
{_stats_row(papers, directions_cfg)}
{_direction_tabs(directions_cfg)}
{_priority_filter_bar()}
{_marks_filter_bar()}
{''.join(cards) if cards else '<p style="color:#888">No papers today.</p>'}
{_version_footer(manifest)}
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
        '<a class="month-topbar__back" href="index.html">← Back to calendar</a>'
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
<style>{CSS}</style>{ASSET_HEAD}</head><body>
<div class="container">
<h1>Research Radar</h1>
<div class="subtitle">{_esc(month_key)} · {len(day_dates)} day(s) · cards show the day's top paper; greyed days have no High or Medium papers</div>
{_month_topbar(month_key, archive_months, len(day_dates))}
<div class="day-grid">{grid}</div>
</div>
</body></html>"""


def _render_index(months, month_counts: dict | None = None, directions_cfg: dict | None = None):
    """C1 + V1: index.html is a flat month grid (newest first), each month
    a clickable `.month-card` with the new `.pill` count badges. Two-step
    nav: calendar → month → day. Year-section grouping is deferred.
    """
    month_counts = month_counts or {}
    n_directions = len(directions_cfg) if directions_cfg else 0
    cards = []
    for mk in sorted(months, reverse=True):
        per_day = month_counts.get(mk, [])
        hm = sum(c.get("High", 0) + c.get("Medium", 0) for c in per_day)
        cls = " month-card--low-quality" if hm == 0 else ""
        cards.append(
            f'<a class="month-card{cls}" href="month-{mk}.html">'
            f'<div class="month-card__label">{_esc(mk)}</div>'
            f'<div class="month-card__pills">{_month_count_badge(per_day)}</div>'
            "</a>"
        )
    grid = "".join(cards)
    # ADR-0016 D1: index serves as the calendar; the prior auto-redirect to
    # the latest daily was removed (user choice 2026-05-19).
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar</title>
<style>{CSS}</style>{ASSET_HEAD}</head><body>
<div class="container">
<h1>Research Radar</h1>
<div class="subtitle">Daily paper digest across {n_directions} research directions · pick a month, then a day · pills show High/Medium/Low(/Exclude) counts</div>
{_nav_row()}
<p style="color:var(--c-text-meta);font-size:var(--text-sm)">Click a month to see its days. Pills show that month's total priority counts; greyed months have no High or Medium papers.</p>
<div class="month-grid">{grid}</div>
</div>
</body></html>"""


def _render_status_page(docs_dir, data_dir):
    """Generate docs/status.html showing recent run history from manifests."""
    import json
    import datetime as _dt

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

        status_color = {
            "success": "#27500A",
            "partial_success": "#A07000",
            "suspicious_empty": "#A03A1A",
            "failed": "#791F1F",
            "—": "#888",
        }.get(run_status, "#888")

        flags_html = "".join(
            f'<span class="qflag">{_esc(q)}</span>' for q in quality_flags
        ) or '<span class="ok">—</span>'

        rows.append(f"""
        <tr>
          <td><a href="{_esc(date)}.html">{_esc(date)}</a></td>
          <td><span style="color:{status_color};font-weight:500">{_esc(run_status)}</span></td>
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
<title>Research Radar — Run status</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.5}}
h1{{font-size:24px;font-weight:500;margin:0 0 .25rem}}
.subtitle{{color:#666;font-size:14px;margin-bottom:1.5rem}}
.navbtn{{font-size:13px;background:#f5f4ef;color:#444;padding:6px 12px;border-radius:8px;text-decoration:none;display:inline-block;margin-bottom:1rem}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;padding:8px 10px;background:#f5f4ef;border-bottom:1px solid #ccc;font-weight:500;color:#555;font-size:12px}}
td{{padding:8px 10px;border-bottom:.5px solid #eee}}
td a{{color:#1F4A6B;text-decoration:none}}
td a:hover{{text-decoration:underline}}
.ok{{color:#999;font-size:11px}}
.qflag{{display:inline-block;background:#FCEBEB;color:#791F1F;font-size:10px;padding:2px 6px;border-radius:5px;margin-right:3px}}
code{{font-family:ui-monospace,monospace;font-size:11px;color:#888;background:#fafaf6;padding:1px 4px;border-radius:3px}}
.legend{{margin-top:2rem;padding:1rem;background:#fafaf6;border-radius:8px;font-size:12px;color:#555}}
.legend h3{{margin:0 0 8px;font-size:13px;color:#222}}
</style></head><body>
<h1>Research Radar — Run status</h1>
<div class="subtitle">Daily run health, last 14 days. Auto-generated from manifests.</div>
<a class="navbtn" href="index.html">← Back to daily</a>

<table>
<thead>
<tr>
  <th>Date</th>
  <th>Status</th>
  <th>Fetched</th>
  <th>After dedup</th>
  <th>Routed</th>
  <th>High/Med</th>
  <th>Zotero ✓/eligible</th>
  <th>Quality flags</th>
  <th>Commit</th>
</tr>
</thead>
<tbody>
{''.join(rows) if rows else '<tr><td colspan="9" style="color:#888">No manifests yet.</td></tr>'}
</tbody>
</table>

<div class="legend">
<h3>Status meanings</h3>
<ul style="margin:0;padding-left:20px">
<li><b>success</b>: normal run, data written</li>
<li><b>suspicious_empty</b>: would have overwritten existing data with empty result, run aborted (W1.1 guard)</li>
<li><b>failed</b>: fetcher or downstream error</li>
<li>Quality flags signal anomalies even when status=success:
  fetched_zero / zero_routed / low_fetch_count / zero_high_medium</li>
</ul>
</div>

</body></html>"""

    out = docs_dir / "status.html"
    out.write_text(html, encoding="utf-8")


def _build_search_index(docs_dir, data_dir):
    """Scan all daily JSONs and build a per-year search index for client-side search.

    ADR-0022: splits the index into docs/search-index-YYYY.json files plus a
    docs/search-index-manifest.json, and slims the per-record blob by dropping
    summary_en (abstract[:500] already supplies English text for matching).
    """
    import json as _json
    from datetime import datetime, timezone

    daily_dir = data_dir / "daily"
    if not daily_dir.exists():
        return 0

    by_year: dict[str, list] = {}
    for jpath in sorted(daily_dir.glob("20*.json")):
        date = jpath.stem
        papers, _meta = _load_papers_v2_or_v1(jpath)
        if not papers:
            continue
        for p in papers:
            llm = p.get("llm", {}) or {}
            s_zh = llm.get("summary_zh", {}) or {}
            # build searchable text blob (lowercased for fast match);
            # summary_en intentionally omitted per ADR-0022.
            blob_parts = [
                p.get("title", ""),
                p.get("abstract", "")[:500],  # truncate to keep index small
                llm.get("relevance_to_user", ""),
                llm.get("why_not_core", ""),
                " ".join(s_zh.values()) if isinstance(s_zh, dict) else "",
                " ".join(llm.get("tags", []) or []),
                " ".join(t.get("en", "") + " " + t.get("zh", "") for t in (llm.get("key_terms", []) or [])),
                ", ".join(p.get("authors", [])[:5]),
                p.get("venue", ""),
                p.get("first_author_affiliation", "") or "",
            ]
            blob = " ".join(b for b in blob_parts if b).lower()
            record = {
                "date": date,
                "title": p.get("title", "")[:200],
                "authors": ", ".join(p.get("authors", [])[:3]) + (" et al." if len(p.get("authors", [])) > 3 else ""),
                "venue": p.get("venue", "")[:80],
                "direction": p.get("direction", ""),
                "direction_name": p.get("direction_name", ""),
                "priority": llm.get("priority", ""),
                "relevance_level": llm.get("relevance_level", ""),
                "read_action": llm.get("read_action", ""),
                "source": p.get("source", ""),
                "doi": p.get("doi", ""),
                "date_precision": p.get("date_precision", "day"),
                "scorer_version": p.get("scorer_version", ""),
                "blob": blob,
            }
            year = ((p.get("date") or jpath.stem) or "")[:4]
            by_year.setdefault(year, []).append(record)

    years = sorted(by_year.keys())
    counts = {y: len(by_year[y]) for y in years}
    total = sum(counts.values())

    for y in years:
        (docs_dir / f"search-index-{y}.json").write_text(
            _json.dumps(by_year[y], ensure_ascii=False), encoding="utf-8"
        )

    manifest = {
        "years": years,
        "counts": counts,
        "total": total,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (docs_dir / "search-index-manifest.json").write_text(
        _json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    return total


def _render_search_page(docs_dir, directions_cfg: dict):
    """Generate docs/search.html with client-side search UI."""
    direction_chips = "\n".join(
        f'  <span class="filter" data-key="direction" data-val="{_esc(dkey)}">{_esc(dcfg["display_name"])}</span>'
        for dkey, dcfg in directions_cfg.items()
    )
    html = """<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — Search</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.5}
h1{font-size:24px;font-weight:500;margin:0 0 .25rem}
.subtitle{color:#666;font-size:14px;margin-bottom:1.5rem}
.navbtn{font-size:13px;background:#f5f4ef;color:#444;padding:6px 12px;border-radius:8px;text-decoration:none;display:inline-block;margin-bottom:1rem;margin-right:8px}
#q{width:100%;font-size:16px;padding:10px 14px;border:1px solid #ccc;border-radius:8px;box-sizing:border-box}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0;font-size:13px}
.filter{background:#f5f4ef;padding:6px 12px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.filter.active{background:#222;color:#fff}
.count{color:#666;font-size:13px;margin:14px 0}
.result{padding:10px 0;border-bottom:.5px solid #eee}
.result a{color:#1F4A6B;text-decoration:none;font-weight:500;font-size:15px}
.result a:hover{text-decoration:underline}
.result .meta{font-size:12px;color:#666;margin-top:3px}
.result .chips{margin-top:5px}
.chip{display:inline-block;font-size:11px;padding:2px 7px;border-radius:6px;margin-right:4px}
.c-high{background:#E0DCC2;color:#3A3514}
.c-medium{background:#F3E1C2;color:#633806}
.c-low{background:#F1EFE8;color:#5F5E5A}
.c-direct{background:#D4EBC4;color:#2D5A14}
.c-transferable{background:#E0DDF4;color:#3F2E7E}
.c-peripheral{background:#F1EFE8;color:#666}
.date{color:#888;font-size:12px}
</style></head><body>
<h1>Research Radar — Search</h1>
<div class="subtitle">Client-side search across all dates. Type to filter.</div>
<a class="navbtn" href="index.html">← Latest daily</a>
<a class="navbtn" href="status.html">📊 Status</a>

<input id="q" placeholder="Search title, abstract, summary, authors, affiliation, tags..." autofocus>

<div class="filters">
  <span class="filter active" data-key="direction" data-val="">All directions</span>
""" + direction_chips + """
</div>
<div class="filters">
  <span class="filter active" data-key="priority" data-val="">Any priority</span>
  <span class="filter" data-key="priority" data-val="High">High only</span>
  <span class="filter" data-key="priority" data-val="High,Medium">High+Medium</span>
</div>
<div class="filters">
  <span class="filter active" data-key="relevance_level" data-val="">Any relevance</span>
  <span class="filter" data-key="relevance_level" data-val="Direct">Direct only ⭐</span>
  <span class="filter" data-key="relevance_level" data-val="Direct,Transferable">Direct+Transferable</span>
</div>

<div class="count" id="count">Loading…</div>
<div id="results"></div>

<script>
let INDEX = [];
const filters = { direction: '', priority: '', relevance_level: '' };

fetch('search-index-manifest.json')
  .then(r => r.json())
  .then(m => Promise.all(
    m.years.map(y => fetch('search-index-' + y + '.json').then(r => r.json()))
  ))
  .then(chunks => {
    INDEX = chunks.flat();
    render();
  });

function applyFilters(items) {
  return items.filter(p => {
    for (const [k, v] of Object.entries(filters)) {
      if (!v) continue;
      const allowed = v.split(',');
      if (!allowed.includes(p[k])) return false;
    }
    return true;
  });
}

function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  let items = INDEX;
  if (q) {
    items = items.filter(p => p.blob.indexOf(q) >= 0);
  }
  items = applyFilters(items);
  // Sort by date desc, then priority
  const prioRank = { High: 3, Medium: 2, Low: 1, Exclude: 0, '': 0 };
  items.sort((a, b) => (b.date.localeCompare(a.date)) || (prioRank[b.priority] - prioRank[a.priority]));

  document.getElementById('count').textContent = `${items.length} results`;
  const html = items.slice(0, 200).map(p => {
    const chips = [
      p.priority ? `<span class=\"chip c-${p.priority.toLowerCase()}\">${p.priority}</span>` : '',
      p.relevance_level ? `<span class=\"chip c-${p.relevance_level.toLowerCase()}\">${p.relevance_level}</span>` : '',
    ].join('');
    return `<div class=\"result\">
      <a href=\"${p.date}.html\">${p.title}</a>
      <div class=\"meta\"><span class=\"date\">${p.date}</span> · ${p.direction_name || p.direction} · ${p.source} · ${p.venue}</div>
      <div class=\"chips\">${chips}</div>
    </div>`;
  }).join('');
  document.getElementById('results').innerHTML = html + (items.length > 200 ? '<p style=\"color:#888;font-size:13px\">(showing first 200; refine search to see more)</p>' : '');
}

document.getElementById('q').addEventListener('input', render);

document.querySelectorAll('.filter').forEach(el => {
  el.addEventListener('click', () => {
    const key = el.dataset.key, val = el.dataset.val;
    filters[key] = val;
    document.querySelectorAll(`.filter[data-key="${key}"]`).forEach(s => s.classList.remove('active'));
    el.classList.add('active');
    render();
  });
});
</script>
</body></html>"""
    (docs_dir / "search.html").write_text(html, encoding="utf-8")


def _page_shell(title: str, subtitle: str, body: str) -> str:
    """Minimal standalone page reusing the base CSS + the radar-ui bundle."""
    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar — {_esc(title)}</title>
<style>{CSS}</style>{ASSET_HEAD}</head><body>
<h1>Research Radar — {_esc(title)}</h1>
<div class="subtitle">{_esc(subtitle)}</div>
<a class="rui-page-back" href="index.html">← Back to calendar</a>
{body}
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


def _copy_static_assets(docs_dir: pathlib.Path) -> None:
    """Copy render/static/radar-ui.{css,js} into docs/ at render time."""
    static_dir = pathlib.Path(__file__).resolve().parent / "static"
    for name in ("radar-ui.css", "radar-ui.js"):
        src = static_dir / name
        if src.exists():
            (docs_dir / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )


def _priority_counts_for(papers: list, meta: dict) -> dict:
    """Prefer the v2 bucket's precomputed counts; recompute only as fallback.

    ADR-0016 D1 says use counts.priority_counts directly. v1 stray files and
    empty buckets have no such block, so a defensive recompute keeps the
    badge correct rather than blank.
    """
    pc = (meta or {}).get("counts", {}).get("priority_counts")
    if isinstance(pc, dict) and pc:
        return pc
    out: dict = {}
    for p in papers:
        prio = p.get("llm", {}).get("priority")
        if prio:
            out[prio] = out.get(prio, 0) + 1
    return out


def build(docs_dir, directions_cfg, manifest=None, touched_dates=None):
    """Render every per-publication-date HTML page from disk, refresh index.

    ADR-0015 §4.5: under v2 a single radar run touches many publication-date
    files. There is no single "today's page" anymore — we re-render every
    archive page from disk so navigation lists stay coherent. `touched_dates`
    is the set of bucket dates this run actually modified; pages for those
    dates get the run manifest footer attached.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)
    data_daily_dir = docs_dir.parent / "data" / "daily"
    archive = sorted(p.stem for p in data_daily_dir.glob("20*.json")) if data_daily_dir.exists() else []
    touched = set(touched_dates or ())

    # Accumulated during the single archive pass (avoids a second full scan):
    #   day_counts  -> ADR-0016 D1 calendar badges
    #   high/medium -> ADR-0016 D2 cross-corpus pages
    day_counts: dict[str, dict] = {}
    # V3: date -> full v2 papers list, consumed by the month-page day-card
    # renderer. ~3554 small JSON files held simultaneously (<200MB RAM,
    # acceptable per the visual-refresh implementation note).
    day_papers_full: dict[str, list] = {}
    high_papers: list = []
    medium_papers: list = []

    for hist_date in archive:
        hist_json = data_daily_dir / f"{hist_date}.json"
        hist_html = docs_dir / f"{hist_date}.html"
        if not hist_json.exists():
            continue
        try:
            hist_papers, _meta = _load_papers_v2_or_v1(hist_json)
            day_counts[hist_date] = _priority_counts_for(hist_papers, _meta)
            day_papers_full[hist_date] = hist_papers
            for p in hist_papers:
                prio = p.get("llm", {}).get("priority")
                if prio == "High":
                    high_papers.append((hist_date, p))
                elif prio == "Medium":
                    medium_papers.append((hist_date, p))
            page_manifest = manifest if hist_date in touched else None
            hist_html.write_text(
                _render_daily(hist_papers, hist_date, directions_cfg, archive, page_manifest),
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

    (docs_dir / "index.html").write_text(
        _render_index(archive_months, month_counts, directions_cfg),
        encoding="utf-8",
    )
    for mk, days in months.items():
        (docs_dir / f"month-{mk}.html").write_text(
            _render_month_page(mk, days, day_counts, day_papers_full,
                                archive_months, directions_cfg),
            encoding="utf-8",
        )

    # ADR-0016 D2: cross-corpus high/medium pages
    (docs_dir / "high-priority.html").write_text(
        _render_cross_corpus_page("High", high_papers, directions_cfg),
        encoding="utf-8",
    )
    (docs_dir / "medium-priority.html").write_text(
        _render_cross_corpus_page("Medium", medium_papers, directions_cfg),
        encoding="utf-8",
    )

    # ADR-0016 D4/D5: client-side curation pages + the JS/CSS bundle
    (docs_dir / "my-marks.html").write_text(
        _render_my_marks_page(), encoding="utf-8")
    (docs_dir / "my-promotes.html").write_text(
        _render_my_promotes_page(), encoding="utf-8")
    _copy_static_assets(docs_dir)

    # W1.x: also render run status page from manifests
    data_dir = docs_dir.parent / "data"
    if data_dir.exists():
        _render_status_page(docs_dir, data_dir)
        n_indexed = _build_search_index(docs_dir, data_dir)
        if n_indexed:
            _render_search_page(docs_dir, directions_cfg)
