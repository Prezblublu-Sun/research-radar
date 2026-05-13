"""Render daily HTML pages with top-bar navigation and version footer."""

from __future__ import annotations
import html
import pathlib


PRIORITY_COLOR = {
    "High":    ("#EAF3DE", "#27500A"),
    "Medium":  ("#FAEEDA", "#633806"),
    "Low":     ("#F1EFE8", "#5F5E5A"),
    "Exclude": ("#FCEBEB", "#791F1F"),
}


def _esc(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _paper_card(p: dict, dir_color: str) -> str:
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

    doi_link = ""
    if p.get("doi"):
        doi_link = f'<a href="https://doi.org/{_esc(p["doi"])}" target="_blank">{_esc(p["doi"])}</a>'
    elif p.get("url"):
        doi_link = f'<a href="{_esc(p["url"])}" target="_blank">link</a>'

    return f"""
<article class="paper" data-direction="{_esc(p.get('direction',''))}" data-priority="{_esc(priority)}">
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


def _priority_filter() -> str:
    return ('<div class="prio-filter">'
            '<button class="pf active" data-prio="HighMedium">High+Medium</button>'
            '<button class="pf" data-prio="High">High only</button>'
            '<button class="pf" data-prio="all">Show all</button>'
            '</div>')


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

    weekly_link = '<a class="navbtn" href="weekly/index.html">📅 Weekly</a>'

    return f'<div class="topbar">{prev_btn}{dropdown}{next_btn}{weekly_link}</div>'


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


CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.5}
h1{font-size:24px;font-weight:500;margin:0 0 .25rem}
.subtitle{color:#666;font-size:14px;margin-bottom:1.5rem}
.topbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 0;margin-bottom:1.25rem;border-bottom:.5px solid #e2e0d8}
.navbtn{font-size:13px;background:#f5f4ef;color:#444;padding:6px 12px;border-radius:8px;text-decoration:none}
.navbtn:hover{background:#e9e7df}
.navbtn.disabled{color:#bbb;background:#fafaf6;cursor:default}
.archive-select{font-size:13px;padding:6px 10px;border:.5px solid #ccc;border-radius:8px;background:#fff;color:#444;cursor:pointer}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.5rem}
.stat{background:#f5f4ef;border-radius:8px;padding:.75rem 1rem}
.stat-label{font-size:12px;color:#666}
.stat-val{font-size:22px;font-weight:500;margin-top:2px}
.tabs,.prio-filter{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:.75rem}
.tab,.pf{background:transparent;border:.5px solid #ccc;border-radius:8px;padding:6px 14px;font-size:13px;cursor:pointer;color:#444}
.tab.active,.pf.active{background:#222;color:#fff;border-color:#222}
.paper{background:#fff;border:.5px solid #e2e0d8;border-radius:12px;padding:1rem 1.25rem;margin-bottom:12px}
.paper-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.priority{font-size:12px;font-weight:500;padding:3px 10px;border-radius:999px}
.direction-pill{font-size:11px;padding:3px 8px;border-radius:8px}
.source{font-size:11px;color:#999;text-transform:uppercase}
.flag{font-size:11px;background:#eef;color:#335;padding:2px 7px;border-radius:6px}
.paper-title{font-size:15px;font-weight:500;line-height:1.4;margin:4px 0}
.meta{font-size:12px;color:#666;margin-bottom:10px}
.meta>span{margin-right:12px}
.relevance{font-size:13px;background:#fafaf6;padding:6px 10px;border-radius:6px;margin-bottom:8px}
.summary{font-size:13px;line-height:1.65}
.summary>div{margin-bottom:4px}
.tags-row{margin-top:8px}
.tag{font-size:10px;background:#f1efe8;color:#555;padding:2px 7px;border-radius:6px;margin-right:4px}
.paper[data-hidden="1"]{display:none}
footer.run-info{margin-top:3rem;padding-top:1rem;border-top:.5px solid #e2e0d8;font-size:12px;color:#666}
footer.run-info summary{cursor:pointer;color:#444}
footer.run-info table{margin-top:8px;font-family:ui-monospace,monospace;font-size:11px}
footer.run-info td{padding:2px 12px 2px 0;vertical-align:top}
footer.run-info td:first-child{color:#888;width:140px}
details.summary-en{margin-top:8px;background:#f8f8f3;border-radius:8px;padding:6px 12px;border:.5px solid #e2e0d8}
details.summary-en summary{cursor:pointer;font-size:12px;color:#555;font-weight:500}
details.summary-en[open] summary{margin-bottom:8px}
.summary.en{font-size:13px;color:#333;line-height:1.55}
.summary.en>div{margin-bottom:3px}
.key-terms{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
.term{font-size:11px;background:#fff;border:.5px solid #ddd;padding:3px 8px;border-radius:6px;color:#444}
.term b{color:#222;font-weight:500}
.relevance-level{font-size:11px;padding:3px 8px;border-radius:8px;font-weight:500}
.lvl-direct{background:#D4EBC4;color:#2D5A14}
.lvl-transferable{background:#E0DDF4;color:#3F2E7E}
.lvl-peripheral{background:#F1EFE8;color:#666}
.read-action{font-size:11px;padding:3px 8px;border-radius:8px;font-weight:500;font-style:italic}
.act-read-now{background:#FFE8D6;color:#7D4515}
.act-save-for-project{background:#E6E1F5;color:#3A2C7A}
.act-skim-only{background:#F0F0E8;color:#5C5C50}
.act-background-only{background:#F5F5F0;color:#777}
.act-ignore{background:#F5E8E8;color:#7A3A3A}
.validation-kind{font-size:10px;background:#EDF4FA;color:#1F4A6B;padding:2px 7px;border-radius:6px}
.why-not-core{font-size:12px;background:#FCF5E8;border-left:3px solid #D8A045;padding:5px 10px;margin-top:4px;color:#5A4318;border-radius:0 6px 6px 0}
"""


JS = """
const tabs = document.querySelectorAll('.tab');
const pfs = document.querySelectorAll('.pf');
let dirFilter = 'all';
let prioFilter = 'HighMedium';
function applyFilters(){
  document.querySelectorAll('.paper').forEach(p=>{
    const d = p.dataset.direction;
    const pr = p.dataset.priority;
    const dirOk = dirFilter==='all' || dirFilter===d;
    const prOk = prioFilter==='all'
                  || (prioFilter==='High' && pr==='High')
                  || (prioFilter==='HighMedium' && (pr==='High'||pr==='Medium'));
    p.dataset.hidden = (dirOk && prOk) ? '0' : '1';
  });
}
tabs.forEach(t=>t.onclick=()=>{tabs.forEach(x=>x.classList.remove('active'));t.classList.add('active');dirFilter=t.dataset.filter;applyFilters();});
pfs.forEach(t=>t.onclick=()=>{pfs.forEach(x=>x.classList.remove('active'));t.classList.add('active');prioFilter=t.dataset.prio;applyFilters();});
applyFilters();
"""


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
<style>{CSS}</style></head><body>
<h1>Research Radar</h1>
<div class="subtitle">{_esc(date)} · AI Bioprinting / Hip Implant / FEA Surrogate / AM Biomedical</div>
{_topbar(date, archive_dates)}
{_stats_row(papers, directions_cfg)}
{_direction_tabs(directions_cfg)}
{_priority_filter()}
{''.join(cards) if cards else '<p style="color:#888">No papers today.</p>'}
{_version_footer(manifest)}
<script>{JS}</script>
</body></html>"""


def _render_index(archive_dates):
    latest = archive_dates[-1] if archive_dates else ""
    links = "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in reversed(archive_dates))
    redirect = f'<meta http-equiv="refresh" content="0; url={latest}.html">' if latest else ""
    return f"""<!doctype html><html><head>
<meta charset="utf-8">{redirect}
<title>Research Radar</title>
<style>{CSS}</style></head><body>
<h1>Research Radar</h1>
<div class="subtitle">Daily paper digest across 4 research directions</div>
<p>If you are not redirected, choose a day:</p>
<ul>{links}</ul>
</body></html>"""


def build(papers, date, docs_dir, directions_cfg, manifest=None):
    docs_dir.mkdir(parents=True, exist_ok=True)
    archive = sorted(p.stem for p in docs_dir.glob("20*.html"))
    if date not in archive:
        archive.append(date)
        archive.sort()

    (docs_dir / f"{date}.html").write_text(
        _render_daily(papers, date, directions_cfg, archive, manifest),
        encoding="utf-8",
    )
    (docs_dir / "index.html").write_text(
        _render_index(archive),
        encoding="utf-8",
    )
