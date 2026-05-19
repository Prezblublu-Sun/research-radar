"""scripts/verify_doi_list.py — DOI verification tool (ADR-0016 audit).

Reads a list of DOIs (with optional author-priority tiering), looks each
DOI up in radar's v2 corpus at ``data/daily/*.json``, and reports radar's
per-DOI verdict plus an aggregate quality summary.

Read-only by design: touches no producer/consumer/render code and writes
nothing into the corpus. Lives under ``scripts/`` rather than
``pipeline/`` because it is an auditor, not a pipeline stage.

Input formats accepted (the parser autodetects):
  - TSV with columns ``doi <TAB> author_priority <TAB> topic`` where
    ``author_priority`` ∈ {must_read, useful, peripheral}.
  - Bare DOI list (one DOI per line); ``author_priority`` and ``topic``
    become empty strings.
  - ``-`` reads from stdin in either of the above shapes.
Lines starting with ``#`` and blank lines are skipped.

CLI::

    .venv/bin/python -m scripts.verify_doi_list <tsv-path|->
        [--out report.tsv] [--out-html report.html]

``--corpus-root`` / ``--directions-yaml`` exist mainly for tests.

The verdict scheme mirrors the ADR-0016 tier semantics:

  must_read  -> radar should ideally rate High or Medium
  useful     -> radar should ideally rate Medium or Low
  peripheral -> radar Low or Exclude is acceptable
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import pathlib
import re
import sys
import urllib.parse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
GH_PAGES_BASE = "https://prezblublu-sun.github.io/research-radar/"
TIERS = ("must_read", "useful", "peripheral")
_OUT_OF_WINDOW_MAX = 2014  # backfill scope starts 2015-01


# ============================== normalisation ==============================

_TRAIL_PUNCT = ".,;)]>"


def normalize_doi(s: str) -> str:
    """Canonicalise a DOI string for case-insensitive matching.

    Strips URL/scheme prefixes, percent-decodes, drops trailing
    punctuation, and lowercases — the typical sources of false misses
    when DOIs are pasted from various places (ground-truth TSVs,
    publisher pages, BibTeX, etc.).
    """
    s = (s or "").strip()
    if not s:
        return ""
    low = s.lower()
    for pref in ("https://doi.org/", "http://doi.org/", "doi:"):
        if low.startswith(pref):
            s = s[len(pref):]
            low = s.lower()
            break
    s = urllib.parse.unquote(s)
    while s and s[-1] in _TRAIL_PUNCT:
        s = s[:-1]
    return s.lower()


def _anchor_for(doi_orig: str) -> str:
    """Mirror ``render.build_pages._anchor_id`` of ``doi:<doi>`` so the URL
    we build resolves to the right per-paper anchor on the daily page.
    """
    return re.sub(r"[^A-Za-z0-9_-]", "-", f"doi:{doi_orig}")


def _trunc(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


# ============================== input parsing ==============================

def load_input(path: str) -> list[dict]:
    """Parse the TSV/bare-DOI input into rows the classifier can consume."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    rows: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        doi_orig = parts[0].strip()
        if not doi_orig:
            continue
        author_priority = parts[1].strip() if len(parts) > 1 else ""
        topic = parts[2].strip() if len(parts) > 2 else ""
        rows.append({
            "doi": doi_orig,
            "doi_norm": normalize_doi(doi_orig),
            "author_priority": author_priority,
            "topic": topic,
        })
    return rows


# ============================== corpus index ===============================

def _papers_in_bucket(path: pathlib.Path) -> list[dict]:
    """Read one daily JSON and return its papers list (v2 or v1 fallback)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        papers = data.get("papers") or []
        return papers if isinstance(papers, list) else []
    return []


def build_corpus_index(daily_dir: pathlib.Path) -> dict[str, list[tuple[str, dict]]]:
    """Walk ``daily_dir`` once and index every paper by its lowercased DOI.

    A DOI may appear in more than one daily bucket if upstream spillover
    happened, so the value is a list. The classifier picks the earliest
    bucket deterministically (sorted by date).
    """
    index: dict[str, list[tuple[str, dict]]] = {}
    if not daily_dir.exists():
        return index
    for jpath in sorted(daily_dir.glob("20*.json")):
        bucket = jpath.stem
        for p in _papers_in_bucket(jpath):
            doi_n = normalize_doi(p.get("doi") or "")
            if not doi_n:
                continue
            index.setdefault(doi_n, []).append((bucket, p))
    return index


# ============================ router keyword index ==========================

def load_router_keywords(yaml_path: pathlib.Path) -> dict[str, set[str]]:
    """Per-direction lowercased keyword set used by the miss-reason heuristic.

    Pulls ``strong_keywords`` + ``sources.openalex_keywords`` +
    ``sources.pubmed_terms`` — the same surfaces ``pipeline.direction_router``
    consults when admitting a paper. We use them in reverse here, to ask
    "would the router likely have admitted this paper if we knew its topic?".
    """
    if not yaml_path.exists():
        return {}
    cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    out: dict[str, set[str]] = {}
    for dkey, dcfg in (cfg.get("directions") or {}).items():
        kws: set[str] = set()
        for kw in (dcfg.get("strong_keywords") or []):
            if kw:
                kws.add(str(kw).lower())
        src = dcfg.get("sources") or {}
        for field in ("openalex_keywords", "pubmed_terms"):
            for kw in (src.get(field) or []):
                if kw:
                    kws.add(str(kw).lower())
        out[dkey] = kws
    return out


# ============================== classification ==============================

# DOIs frequently embed a year segment (e.g. .../j.clinbiomech.2008.11.003).
# Limit the match to plausible years that aren't part of a longer number.
_YEAR_HINT = re.compile(r"(?<!\d)(19[5-9]\d|20[01]\d)(?!\d)")


def _doi_year_hint(doi_orig: str) -> int | None:
    years = [int(y) for y in _YEAR_HINT.findall(doi_orig)]
    return min(years) if years else None


def _verdict_present(author_priority: str, radar_priority: str) -> str:
    ap, rp = author_priority, radar_priority
    if not ap:
        return "no_ground_truth"
    if ap == "must_read":
        return "correct_must_read" if rp in ("High", "Medium") else "under_scored"
    if ap == "useful":
        if rp in ("Medium", "Low"):
            return "correct_useful"
        if rp == "Exclude":
            return "under_scored"
        return "over_scored"  # rp == "High": more relevant than ground truth claims
    if ap == "peripheral":
        return "correct_peripheral" if rp in ("Low", "Exclude") else "over_scored"
    return "no_ground_truth"


def _verdict_missing(author_priority: str) -> str:
    return {
        "must_read":  "missing_must_read",
        "useful":     "missing_useful",
        "peripheral": "missing_peripheral",
    }.get(author_priority, "missing")


def _miss_reason(doi_orig: str, topic: str, routers: dict[str, set[str]]) -> str:
    year = _doi_year_hint(doi_orig)
    if year is not None and year <= _OUT_OF_WINDOW_MAX:
        return "out_of_window"
    if topic and routers:
        t = topic.lower()
        for kws in routers.values():
            if any(kw in t for kw in kws):
                return "direction_match_possible"
        return "direction_mismatch_likely"
    return "unknown"


def classify(row: dict, corpus_index: dict, routers: dict[str, set[str]]) -> dict:
    """Resolve one input row into a verdict record (in_corpus or missing)."""
    doi_orig = row["doi"]
    doi_n = row["doi_norm"]
    ap = row["author_priority"]
    topic = row["topic"]

    rec = {
        "doi": doi_orig, "author_priority": ap, "topic": topic,
        "in_corpus": False,
        "radar_priority": "", "direction": "", "direction_name": "",
        "publication_date": "", "bucket_date": "", "scorer_version": "",
        "title": "", "relevance_to_user": "", "summary_motivation": "",
        "daily_page_url": "", "miss_reason": "", "verdict": "",
    }

    hits = corpus_index.get(doi_n) or []
    if not hits:
        rec["miss_reason"] = _miss_reason(doi_orig, topic, routers)
        rec["verdict"] = _verdict_missing(ap)
        return rec

    bucket, p = sorted(hits, key=lambda bp: bp[0])[0]
    llm = p.get("llm", {}) or {}
    zh = llm.get("summary_zh", {}) or {}
    rec.update({
        "in_corpus": True,
        "radar_priority": llm.get("priority", ""),
        "direction": p.get("direction", ""),
        "direction_name": p.get("direction_name", ""),
        "publication_date": (
            p.get("date") or (str(p.get("year")) if p.get("year") else "")
        ),
        "bucket_date": bucket,
        "scorer_version": p.get("scorer_version", ""),
        "title": p.get("title") or "",
        "relevance_to_user": _trunc(llm.get("relevance_to_user", ""), 120),
        "summary_motivation": _trunc(zh.get("motivation", ""), 120),
        "daily_page_url":
            f"{GH_PAGES_BASE}{bucket}.html#{_anchor_for(p.get('doi') or doi_orig)}",
    })
    rec["verdict"] = (
        _verdict_present(ap, rec["radar_priority"]) if ap else "no_ground_truth"
    )
    return rec


# ============================== aggregation ================================

def aggregate(records: list[dict]) -> dict:
    n = len(records)
    n_in = sum(1 for r in records if r["in_corpus"])
    per_tier: dict[str, dict] = {
        t: {"H": 0, "M": 0, "L": 0, "X": 0, "missing": 0, "total": 0}
        for t in TIERS
    }
    miss_reasons: dict[str, int] = {}
    under: list[dict] = []
    short = {"High": "H", "Medium": "M", "Low": "L", "Exclude": "X"}
    for r in records:
        ap = r["author_priority"]
        if ap in per_tier:
            per_tier[ap]["total"] += 1
            if not r["in_corpus"]:
                per_tier[ap]["missing"] += 1
            else:
                k = short.get(r["radar_priority"])
                if k:
                    per_tier[ap][k] += 1
        if not r["in_corpus"]:
            mr = r["miss_reason"] or "unknown"
            miss_reasons[mr] = miss_reasons.get(mr, 0) + 1
        if r["verdict"] == "under_scored":
            under.append(r)
    return {
        "n": n, "n_in": n_in, "n_miss": n - n_in,
        "per_tier": per_tier,
        "miss_reasons": miss_reasons,
        "under_scored": under,
    }


# ================================ rendering ================================

def render_stdout(records: list[dict], agg: dict) -> str:
    lines: list[str] = []
    lines.append("DOI verification report (radar v2 corpus)")
    lines.append("=" * 78)
    lines.append(
        f"{'DOI':<46} {'tier':<11} {'verdict':<22} {'rad':<7} direction"
    )
    lines.append("-" * 110)
    for r in records:
        lines.append(
            f"{r['doi'][:45]:<46} {r['author_priority'][:10]:<11} "
            f"{r['verdict'][:21]:<22} {r['radar_priority'][:6]:<7} "
            f"{r['direction']}"
        )
    lines.append("")
    lines.append("Aggregate")
    lines.append("-" * 78)
    lines.append(f"Total DOIs                       {agg['n']}")
    lines.append(
        f"In corpus                        {agg['n_in']} ({agg['n_in']}/{agg['n']})"
    )
    lines.append(
        f"Missed                           {agg['n_miss']} ({agg['n_miss']}/{agg['n']})"
    )
    for t in TIERS:
        pt = agg["per_tier"][t]
        if pt["total"] == 0:
            continue
        hm = pt["H"] + pt["M"]
        tail = ""
        if t == "must_read":
            recall = hm / pt["total"] * 100 if pt["total"] else 0.0
            tail = f"   -> recall = {hm}/{pt['total']} ({recall:.0f}%)"
        lines.append(
            f"Of the {t} papers ({pt['total']}): "
            f"H+M = {hm}, L = {pt['L']}, Exclude = {pt['X']}, "
            f"missing = {pt['missing']}{tail}"
        )
    lines.append("")
    lines.append("Miss reason breakdown:")
    for k in ("out_of_window", "direction_match_possible",
              "direction_mismatch_likely", "unknown"):
        lines.append(f"  {k:<28} {agg['miss_reasons'].get(k, 0)}")
    if agg["under_scored"]:
        lines.append("")
        lines.append("Under-scored DOIs (action items):")
        for r in agg["under_scored"]:
            lines.append(
                f"  [{r['radar_priority']}] {r['doi']}  {_trunc(r['title'], 70)}"
            )
            if r["relevance_to_user"]:
                lines.append(f"      relevance: {r['relevance_to_user']}")
    return "\n".join(lines) + "\n"


_TSV_FIELDS = (
    "doi", "author_priority", "topic", "in_corpus",
    "radar_priority", "direction", "direction_name",
    "publication_date", "bucket_date", "scorer_version",
    "title", "relevance_to_user", "summary_motivation",
    "daily_page_url", "miss_reason", "verdict",
)


def render_tsv(records: list[dict]) -> str:
    out: list[str] = ["\t".join(_TSV_FIELDS)]
    for r in records:
        cells: list[str] = []
        for f in _TSV_FIELDS:
            v = r.get(f, "")
            if isinstance(v, bool):
                v = "true" if v else "false"
            cells.append(str(v).replace("\t", " ").replace("\n", " "))
        out.append("\t".join(cells))
    return "\n".join(out) + "\n"


# Tokens mirror radar-ui.css (V1 design system) so the HTML report sits in
# the same visual language as the rest of the site, without re-importing
# the whole stylesheet.
_HTML_CSS = """
:root{--c-brand:#1B4D7E;--c-bg:#FAFAF7;--c-card-bg:#FFFFFF;--c-card-border:#ECEAE3;
--c-text-primary:#1F2937;--c-text-secondary:#4B5563;--c-text-meta:#8B8980;--c-text-muted:#B5B3AA;
--c-priority-h:#C8362A;--c-priority-m:#E89C3A;--c-priority-l:#A0A0A0;--c-priority-x:#D5D5D5}
*{box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:var(--c-bg);
  color:var(--c-text-primary);max-width:1200px;margin:2rem auto;padding:0 1rem;line-height:1.5}
h1{font-size:24px;font-weight:600;margin:0 0 .5rem;color:var(--c-brand)}
h2{font-size:14px;font-weight:600;color:var(--c-brand);margin:.75rem 0 .25rem}
.summary{background:var(--c-card-bg);border:1px solid var(--c-card-border);
  border-radius:12px;padding:14px 18px;font-size:13px;margin:1rem 0}
.summary table{border-collapse:collapse;font-size:13px;margin-top:6px}
.summary td{padding:3px 18px 3px 0;vertical-align:top}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600;
  display:inline-flex;align-items:center;gap:4px}
.pill::before{content:'';width:6px;height:6px;border-radius:50%;display:inline-block}
.pill--high{color:var(--c-priority-h);background:#FCE7E4}
.pill--high::before{background:var(--c-priority-h)}
.pill--medium{color:var(--c-priority-m);background:#FDF1DE}
.pill--medium::before{background:var(--c-priority-m)}
.pill--low{color:var(--c-text-meta);background:#F0EFE9}
.pill--low::before{background:var(--c-priority-l)}
.pill--exclude{color:var(--c-text-muted);background:#F5F4EF}
.pill--exclude::before{background:var(--c-priority-x)}
.pill--missing{color:#7C2A2A;background:#F7DEDB}
.pill--missing::before{background:#7C2A2A}
table.records{width:100%;border-collapse:collapse;font-size:12px;background:var(--c-card-bg);
  border:1px solid var(--c-card-border);border-radius:12px;overflow:hidden}
table.records th{text-align:left;padding:8px 10px;background:var(--c-bg);font-weight:600;
  color:var(--c-text-secondary);border-bottom:1px solid var(--c-card-border);font-size:11px}
table.records td{padding:6px 10px;border-bottom:1px solid var(--c-card-border);vertical-align:top}
table.records tr:last-child td{border-bottom:none}
table.records a{color:var(--c-brand);text-decoration:none}
table.records a:hover{text-decoration:underline}
.verdict-correct_must_read,.verdict-correct_useful,.verdict-correct_peripheral{color:#27500A}
.verdict-under_scored,.verdict-missing_must_read{color:var(--c-priority-h);font-weight:600}
.verdict-over_scored{color:#9A6D14}
.verdict-no_ground_truth{color:var(--c-text-meta)}
.verdict-missing_useful,.verdict-missing_peripheral,.verdict-missing{color:var(--c-text-meta)}
"""


def _pill_for_priority(p: str) -> str:
    mod = {"High": "high", "Medium": "medium",
           "Low": "low", "Exclude": "exclude"}.get(p, "")
    if not mod:
        return '<span class="pill pill--missing">missing</span>'
    return f'<span class="pill pill--{mod}">{html_mod.escape(p)}</span>'


def render_html(records: list[dict], agg: dict) -> str:
    rows: list[str] = []
    for r in records:
        pill = (_pill_for_priority(r["radar_priority"]) if r["in_corpus"]
                else '<span class="pill pill--missing">missing</span>')
        doi_html = html_mod.escape(r["doi"])
        doi_cell = (
            f'<a href="{html_mod.escape(r["daily_page_url"])}">{doi_html}</a>'
            if r["in_corpus"] else doi_html
        )
        rows.append(
            "<tr>"
            f"<td>{doi_cell}</td>"
            f"<td>{html_mod.escape(r['author_priority'])}</td>"
            f"<td>{pill}</td>"
            f"<td class='verdict-{html_mod.escape(r['verdict'])}'>"
            f"{html_mod.escape(r['verdict'])}</td>"
            f"<td>{html_mod.escape(r['direction_name'] or r['direction'])}</td>"
            f"<td>{html_mod.escape(_trunc(r['title'], 90))}</td>"
            f"<td>{html_mod.escape(r['miss_reason'])}</td>"
            "</tr>"
        )

    pt_rows: list[str] = []
    for t in TIERS:
        pt = agg["per_tier"][t]
        if pt["total"] == 0:
            continue
        hm = pt["H"] + pt["M"]
        pt_rows.append(
            f"<tr><td><b>{t}</b> ({pt['total']})</td>"
            f"<td>H+M={hm} · L={pt['L']} · X={pt['X']} "
            f"· missing={pt['missing']}</td></tr>"
        )
    miss_rows = "".join(
        f"<tr><td>{html_mod.escape(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(agg["miss_reasons"].items())
    )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>Radar DOI verification</title>"
        f"<style>{_HTML_CSS}</style></head><body>"
        "<h1>Radar DOI verification</h1>"
        "<div class='summary'>"
        f"<b>{agg['n']} DOIs</b> · in corpus {agg['n_in']} "
        f"· missed {agg['n_miss']}"
        "<h2>Per-tier breakdown</h2>"
        f"<table>{''.join(pt_rows) or '<tr><td>(no tiered rows)</td></tr>'}</table>"
        "<h2>Miss reasons</h2>"
        f"<table>{miss_rows or '<tr><td>(none)</td></tr>'}</table>"
        "</div>"
        "<table class='records'><thead><tr>"
        "<th>DOI</th><th>author_priority</th><th>radar</th>"
        "<th>verdict</th><th>direction</th><th>title</th><th>miss_reason</th>"
        "</tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
        "</body></html>"
    )


# ================================== entry ==================================

def run(argv: list[str] | None = None) -> dict:
    """Parse args, classify every input row, render outputs.

    Returns a dict with the classified records and the aggregate summary,
    chiefly for tests; the CLI also writes the stdout/TSV/HTML artefacts
    as side effects.
    """
    p = argparse.ArgumentParser(
        prog="verify_doi_list",
        description="Verify a DOI list against radar's v2 scoring corpus.",
    )
    p.add_argument("input",
                   help="Path to a TSV/DOI-list file, or '-' for stdin.")
    p.add_argument("--out", type=pathlib.Path, default=None,
                   help="Write a TSV report to this file.")
    p.add_argument("--out-html", dest="out_html", type=pathlib.Path, default=None,
                   help="Write a tokenised HTML report to this file.")
    p.add_argument("--corpus-root", dest="corpus_root", type=pathlib.Path,
                   default=None,
                   help="Override the data/daily/ root (mainly for tests).")
    p.add_argument("--directions-yaml", dest="directions_yaml",
                   type=pathlib.Path, default=None,
                   help="Override config/directions.yaml path (for tests).")
    args = p.parse_args(argv)

    corpus_root = args.corpus_root or (ROOT / "data" / "daily")
    yaml_path = args.directions_yaml or (ROOT / "config" / "directions.yaml")

    rows = load_input(args.input)
    index = build_corpus_index(corpus_root)
    routers = load_router_keywords(yaml_path)
    records = [classify(row, index, routers) for row in rows]
    agg = aggregate(records)

    sys.stdout.write(render_stdout(records, agg))
    if args.out:
        args.out.write_text(render_tsv(records), encoding="utf-8")
    if args.out_html:
        args.out_html.write_text(render_html(records, agg), encoding="utf-8")
    return {"records": records, "aggregate": agg}


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
