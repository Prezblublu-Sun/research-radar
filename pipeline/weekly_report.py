"""Weekly report generator. Aggregates the last 7 days of daily JSONs into
a Top-N picks page. Trend analysis and LLM meta-summary are TODO (Phase 2).

Output: docs/weekly/YYYY-WW.html and docs/weekly/index.html
ISO week number is used (Monday=start of week).
"""

from __future__ import annotations
import datetime as dt
import json
import pathlib
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
WEEKLY_DIR = DOCS_DIR / "weekly"
CONFIG = ROOT / "config" / "directions.yaml"


def _load_papers_v2_or_v1(path: pathlib.Path) -> tuple[list[dict], dict]:
    """Return (papers, file_meta) for a daily JSON, v2-dict or stray v1-list.

    v2 (ADR-0015 §4.5): {schema_version, date, date_precision, papers, counts}
    v1 (pre-migration): top-level list of paper dicts.
    Anything unparseable / unexpected returns ([], {}).

    Duplicated from render/build_pages.py rather than imported: weekly_report
    is part of the pipeline package and we keep it free of a render-layer
    import dependency (same rationale as export_candidates.py).
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


def _paper_in_window(p: dict, monday: dt.date, sunday: dt.date) -> bool:
    """True iff the paper's publication `date` falls in [monday, sunday].

    ADR-0015 §4.5 / decision D9: "weekly" means *published this week*, keyed
    on paper["date"] (publication date), NOT paper["first_seen_at"] (the
    radar-run/backfill date). No date_precision filtering here -- a
    month/year-precision paper still carries a full ISO date pinned to the
    1st, so it lands in whatever ISO week that 1st belongs to and is kept.
    """
    raw = p.get("date") or ""
    try:
        d = dt.date.fromisoformat(str(raw)[:10])
    except (ValueError, TypeError):
        return False
    return monday <= d <= sunday


def _iso_week_id(d: dt.date) -> str:
    """Returns 'YYYY-Www' format, e.g. '2026-W20'."""
    yr, wk, _ = d.isocalendar()
    return f"{yr}-W{wk:02d}"


def _week_dates(end_date: dt.date) -> tuple[dt.date, dt.date]:
    """Given any date in a week, return that week's Monday and Sunday."""
    weekday = end_date.weekday()  # Mon=0
    monday = end_date - dt.timedelta(days=weekday)
    sunday = monday + dt.timedelta(days=6)
    return monday, sunday


def collect_week_papers(end_date: dt.date) -> tuple[list[dict], dict]:
    """Load all daily JSONs in the ISO week containing end_date.
    Returns (papers, stats_dict)."""
    monday, sunday = _week_dates(end_date)
    all_papers = []
    days_with_data = 0
    daily_counts = {}

    cur = monday
    while cur <= sunday:
        path = DATA_DIR / "daily" / f"{cur.isoformat()}.json"
        if path.exists():
            try:
                raw_ps, _meta = _load_papers_v2_or_v1(path)
                # D9: keep only papers actually published in this ISO week.
                # Under v2 the bucket filename usually already aligns with
                # publication date, but month/year-precision papers can land
                # a bucket off, so we filter on paper["date"] explicitly.
                ps = [p for p in raw_ps if _paper_in_window(p, monday, sunday)]
                if ps:
                    all_papers.extend(ps)
                    days_with_data += 1
                    daily_counts[cur.isoformat()] = {
                        "total": len(ps),
                        "High":    sum(1 for p in ps if p.get("llm", {}).get("priority") == "High"),
                        "Medium":  sum(1 for p in ps if p.get("llm", {}).get("priority") == "Medium"),
                        "Low":     sum(1 for p in ps if p.get("llm", {}).get("priority") == "Low"),
                        "Exclude": sum(1 for p in ps if p.get("llm", {}).get("priority") == "Exclude"),
                    }
            except Exception as e:
                print(f"  ! skipping {path.name}: {e}")
        cur += dt.timedelta(days=1)

    stats = {
        "week_id": _iso_week_id(end_date),
        "monday": monday.isoformat(),
        "sunday": sunday.isoformat(),
        "days_with_data": days_with_data,
        "total_papers": len(all_papers),
        "daily_counts": daily_counts,
        "priority_totals": {
            "High":    sum(d["High"]    for d in daily_counts.values()),
            "Medium":  sum(d["Medium"]  for d in daily_counts.values()),
            "Low":     sum(d["Low"]     for d in daily_counts.values()),
            "Exclude": sum(d["Exclude"] for d in daily_counts.values()),
        },
    }
    return all_papers, stats


def filter_top_picks(papers: list[dict]) -> dict:
    """Group papers by direction, keep only High + Medium."""
    by_dir = {}
    for p in papers:
        prio = p.get("llm", {}).get("priority", "Low")
        if prio not in ("High", "Medium"):
            continue
        d = p.get("direction", "unknown")
        by_dir.setdefault(d, []).append(p)

    # Sort each direction: High first, then by routing score / cited_by
    order = {"High": 0, "Medium": 1}
    for d in by_dir:
        by_dir[d].sort(key=lambda p: (
            order.get(p.get("llm", {}).get("priority"), 9),
            -p.get("cited_by_count", 0),
        ))
    return by_dir


# ---------------- Rendering ----------------

CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#222;line-height:1.5}
h1{font-size:24px;font-weight:500;margin:0 0 .25rem}
h2{font-size:18px;font-weight:500;margin-top:2rem;margin-bottom:.5rem}
.subtitle{color:#666;font-size:14px;margin-bottom:1.5rem}
.topbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 0;margin-bottom:1.25rem;border-bottom:.5px solid #e2e0d8}
.navbtn{font-size:13px;background:#f5f4ef;color:#444;padding:6px 12px;border-radius:8px;text-decoration:none}
.navbtn:hover{background:#e9e7df}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:1.5rem}
.stat{background:#f5f4ef;border-radius:8px;padding:.75rem 1rem}
.stat-label{font-size:12px;color:#666}
.stat-val{font-size:22px;font-weight:500;margin-top:2px}
.daily-counts{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:1.25rem;font-size:12px;color:#888}
.daily-counts span{background:#fafaf6;padding:3px 8px;border-radius:6px;border:.5px solid #e2e0d8}
.paper{background:#fff;border:.5px solid #e2e0d8;border-radius:12px;padding:1rem 1.25rem;margin-bottom:12px}
.paper-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
.priority{font-size:12px;font-weight:500;padding:3px 10px;border-radius:999px}
.priority.High{background:#EAF3DE;color:#27500A}
.priority.Medium{background:#FAEEDA;color:#633806}
.source{font-size:11px;color:#999;text-transform:uppercase}
.paper-title{font-size:15px;font-weight:500;line-height:1.4;margin:4px 0}
.meta{font-size:12px;color:#666;margin-bottom:10px}
.meta>span{margin-right:12px}
.relevance{font-size:13px;background:#fafaf6;padding:6px 10px;border-radius:6px;margin-bottom:8px}
.summary{font-size:13px;line-height:1.65}
.summary>div{margin-bottom:4px}
.dir-section{margin-bottom:2rem}
.dir-pill{display:inline-block;padding:4px 12px;border-radius:8px;color:#fff;font-weight:500;font-size:13px;margin-bottom:.5rem}
.coming-soon{background:#FFF7E6;border:1px dashed #D4A052;padding:.75rem 1rem;border-radius:8px;color:#7B5817;font-size:13px;margin-bottom:1.5rem}
"""


def _esc(s):
    import html as _html
    return _html.escape(str(s) if s is not None else "")


def _topbar(week_id, all_week_ids):
    sorted_w = sorted(all_week_ids)
    try:
        idx = sorted_w.index(week_id)
    except ValueError:
        idx = len(sorted_w) - 1
    prev_w = sorted_w[idx - 1] if idx > 0 else None
    next_w = sorted_w[idx + 1] if idx < len(sorted_w) - 1 else None
    prev_btn = f'<a class="navbtn" href="{prev_w}.html">← {prev_w}</a>' if prev_w else '<span class="navbtn disabled">← oldest</span>'
    next_btn = f'<a class="navbtn" href="{next_w}.html">{next_w} →</a>' if next_w else '<span class="navbtn disabled">latest →</span>'
    return f'<div class="topbar">{prev_btn}{next_btn}<a class="navbtn" href="../index.html">📰 Back to daily</a></div>'


def _stats_row(stats):
    pt = stats["priority_totals"]
    cards = [
        f'<div class="stat"><div class="stat-label">Total scored</div><div class="stat-val">{sum(pt.values())}</div></div>',
        f'<div class="stat"><div class="stat-label">High</div><div class="stat-val" style="color:#27500A">{pt["High"]}</div></div>',
        f'<div class="stat"><div class="stat-label">Medium</div><div class="stat-val" style="color:#633806">{pt["Medium"]}</div></div>',
        f'<div class="stat"><div class="stat-label">Days w/ data</div><div class="stat-val">{stats["days_with_data"]}/7</div></div>',
        f'<div class="stat"><div class="stat-label">Total fetched</div><div class="stat-val">{stats["total_papers"]}</div></div>',
    ]
    return '<div class="stats">' + "".join(cards) + "</div>"


def _daily_strip(stats):
    items = []
    for date, c in sorted(stats["daily_counts"].items()):
        items.append(f'<span>{date}: H{c["High"]} M{c["Medium"]}</span>')
    if not items:
        return '<div class="daily-counts"><span>No daily data this week.</span></div>'
    return '<div class="daily-counts">' + "".join(items) + "</div>"


def _paper_card(p, dir_color):
    llm = p.get("llm", {})
    priority = llm.get("priority", "Low")
    s = llm.get("summary_zh", {})
    authors = ", ".join(p.get("authors", [])[:5])
    if len(p.get("authors", [])) > 5:
        authors += " et al."
    doi_link = ""
    if p.get("doi"):
        doi_link = f'<a href="https://doi.org/{_esc(p["doi"])}" target="_blank">{_esc(p["doi"])}</a>'
    elif p.get("url"):
        doi_link = f'<a href="{_esc(p["url"])}" target="_blank">link</a>'

    return f"""
<article class="paper">
  <div class="paper-head">
    <span class="priority {_esc(priority)}">{_esc(priority)}</span>
    <span class="source">{_esc(p.get('source',''))}</span>
  </div>
  <h3 class="paper-title">{_esc(p.get('title',''))}</h3>
  <div class="meta">
    <span>{_esc(authors)}</span><span>{_esc(p.get('venue',''))}</span>
    <span>{_esc(p.get('date',''))}</span><span>{doi_link}</span>
  </div>
  <div class="relevance"><b>相关性:</b> {_esc(llm.get('relevance_to_user',''))}</div>
  <div class="summary">
    <div><b>动机·</b> {_esc(s.get('motivation',''))}</div>
    <div><b>方法·</b> {_esc(s.get('method',''))}</div>
    <div><b>结果·</b> {_esc(s.get('result',''))}</div>
    <div><b>验证·</b> {_esc(s.get('validation',''))}</div>
  </div>
</article>"""


def _render_weekly(stats, by_dir, directions_cfg, all_week_ids):
    sections = []
    for d_key, d_cfg in directions_cfg.items():
        ps = by_dir.get(d_key, [])
        if not ps:
            sections.append(
                f'<div class="dir-section"><span class="dir-pill" style="background:{d_cfg["color"]}">'
                f'{_esc(d_cfg["display_name"])}</span><p style="color:#888;font-size:13px">No High/Medium picks this week.</p></div>'
            )
            continue
        cards = "".join(_paper_card(p, d_cfg["color"]) for p in ps)
        sections.append(
            f'<div class="dir-section">'
            f'<span class="dir-pill" style="background:{d_cfg["color"]}">{_esc(d_cfg["display_name"])} ({len(ps)})</span>'
            f'{cards}</div>'
        )

    coming_soon = ('<div class="coming-soon">'
                   '📊 Trend analysis and 📝 LLM weekly summary coming soon. '
                   '(Phase 2 — will compare keyword frequency week-over-week, '
                   'and add an AI-generated narrative overview.)'
                   '</div>')

    return f"""<!doctype html><html lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar Weekly — {_esc(stats['week_id'])}</title>
<style>{CSS}</style></head><body>
<h1>Research Radar Weekly</h1>
<div class="subtitle">{_esc(stats['week_id'])} · {_esc(stats['monday'])} ~ {_esc(stats['sunday'])}</div>
{_topbar(stats['week_id'], all_week_ids)}
{_stats_row(stats)}
{_daily_strip(stats)}
{coming_soon}
<h2>Top picks by direction (Priority ≥ Medium)</h2>
{"".join(sections)}
</body></html>"""


def _render_index(all_week_ids):
    latest = all_week_ids[-1] if all_week_ids else None
    redirect = f'<meta http-equiv="refresh" content="0; url={latest}.html">' if latest else ""
    links = "".join(f'<li><a href="{w}.html">{w}</a></li>' for w in reversed(all_week_ids))
    return f"""<!doctype html><html><head>
<meta charset="utf-8">{redirect}
<title>Research Radar Weekly</title>
<style>{CSS}</style></head><body>
<h1>Research Radar Weekly</h1>
<p>If you are not redirected, choose a week:</p>
<ul>{links}</ul>
<p><a href="../index.html">← Back to daily</a></p>
</body></html>"""


def build_weekly(end_date: dt.date | None = None) -> dict:
    if end_date is None:
        # Report on the most recently completed ISO week (last Mon-Sun).
        # If today is Monday, we still want LAST week, not this week.
        today = dt.date.today()
        # Go back to last Sunday (the day before the most recent Monday).
        # weekday(): Mon=0..Sun=6
        days_to_last_sunday = today.weekday() + 1  # Mon=1, Tue=2, ..., Sun=7
        end_date = today - dt.timedelta(days=days_to_last_sunday)
    cfg = yaml.safe_load(CONFIG.read_text())
    directions_cfg = cfg["directions"]

    papers, stats = collect_week_papers(end_date)
    by_dir = filter_top_picks(papers)

    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    all_week_ids = sorted(p.stem for p in WEEKLY_DIR.glob("20*.html"))
    if stats["week_id"] not in all_week_ids:
        all_week_ids.append(stats["week_id"])
        all_week_ids.sort()

    (WEEKLY_DIR / f"{stats['week_id']}.html").write_text(
        _render_weekly(stats, by_dir, directions_cfg, all_week_ids),
        encoding="utf-8",
    )
    (WEEKLY_DIR / "index.html").write_text(
        _render_index(all_week_ids),
        encoding="utf-8",
    )

    return {
        "week_id": stats["week_id"],
        "monday": stats["monday"],
        "sunday": stats["sunday"],
        "days_with_data": stats["days_with_data"],
        "high_count": stats["priority_totals"]["High"],
        "medium_count": stats["priority_totals"]["Medium"],
        "directions_with_picks": list(by_dir.keys()),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        end = dt.date.fromisoformat(sys.argv[1])
    else:
        end = dt.date.today()
    report = build_weekly(end_date=end)
    print(json.dumps(report, indent=2, ensure_ascii=False))
