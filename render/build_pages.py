"""Render daily HTML pages with top-bar navigation and version footer."""

from __future__ import annotations
import html
import json
import pathlib


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
    first_aff = p.get("first_author_affiliation", "")
    # Only keep corresponding entries that actually have an affiliation
    corresp_list = [c for c in (p.get("corresponding_authors") or []) if c.get("affiliation")]

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
    status_link = '<a class="navbtn" href="status.html">📊 Status</a>'
    search_link = '<a class="navbtn" href="search.html">🔍 Search</a>'

    return f'<div class="topbar">{prev_btn}{dropdown}{next_btn}{weekly_link}{status_link}{search_link}</div>'


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
.affiliations{font-size:12px;color:#666;margin-top:6px;padding-left:6px;border-left:2px solid #ddd}
.affiliations b{color:#444;font-weight:500}
.corresponding{font-size:12px;color:#555;margin-top:3px;padding-left:6px;border-left:2px solid #aac}
.corresponding b{color:#3F2E7E;font-weight:500}
.corresp-aff{color:#888}
.corresponding i{color:#888;font-size:11px}
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
    """Scan all daily JSONs and build a search index for client-side search."""
    import json as _json
    daily_dir = data_dir / "daily"
    if not daily_dir.exists():
        return

    index = []
    for jpath in sorted(daily_dir.glob("20*.json")):
        date = jpath.stem
        papers, _meta = _load_papers_v2_or_v1(jpath)
        if not papers:
            continue
        for p in papers:
            llm = p.get("llm", {}) or {}
            s_zh = llm.get("summary_zh", {}) or {}
            s_en = llm.get("summary_en", {}) or {}
            # build searchable text blob (lowercased for fast match)
            blob_parts = [
                p.get("title", ""),
                p.get("abstract", "")[:500],  # truncate to keep index small
                llm.get("relevance_to_user", ""),
                llm.get("why_not_core", ""),
                " ".join(s_zh.values()) if isinstance(s_zh, dict) else "",
                " ".join(s_en.values()) if isinstance(s_en, dict) else "",
                " ".join(llm.get("tags", []) or []),
                " ".join(t.get("en", "") + " " + t.get("zh", "") for t in (llm.get("key_terms", []) or [])),
                ", ".join(p.get("authors", [])[:5]),
                p.get("venue", ""),
                p.get("first_author_affiliation", "") or "",
            ]
            blob = " ".join(b for b in blob_parts if b).lower()
            index.append({
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
            })

    out = docs_dir / "search-index.json"
    out.write_text(_json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return len(index)


def _render_search_page(docs_dir):
    """Generate docs/search.html with client-side search UI."""
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
  <span class="filter" data-key="direction" data-val="ai_bioprinting">AI Bioprinting</span>
  <span class="filter" data-key="direction" data-val="hip_implant">Hip Implant</span>
  <span class="filter" data-key="direction" data-val="fea_surrogate">FEA Surrogate</span>
  <span class="filter" data-key="direction" data-val="am_biomedical">AM Biomedical</span>
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

fetch('search-index.json').then(r => r.json()).then(data => {
  INDEX = data;
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

    for hist_date in archive:
        hist_json = data_daily_dir / f"{hist_date}.json"
        hist_html = docs_dir / f"{hist_date}.html"
        if not hist_json.exists():
            continue
        try:
            hist_papers, _meta = _load_papers_v2_or_v1(hist_json)
            page_manifest = manifest if hist_date in touched else None
            hist_html.write_text(
                _render_daily(hist_papers, hist_date, directions_cfg, archive, page_manifest),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"  (skip re-render {hist_date}: {e})")

    (docs_dir / "index.html").write_text(
        _render_index(archive),
        encoding="utf-8",
    )

    # W1.x: also render run status page from manifests
    data_dir = docs_dir.parent / "data"
    if data_dir.exists():
        _render_status_page(docs_dir, data_dir)
        n_indexed = _build_search_index(docs_dir, data_dir)
        if n_indexed:
            _render_search_page(docs_dir)
