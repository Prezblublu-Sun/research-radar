"""One-off corpus quality audit for Radar's scored daily buckets.

Reads `data/daily/*.json` (v2 schema), draws a stratified random sample
across years, and reports four quality dimensions per sampled paper:

    1. field completeness + silent/scorer_failed (objective)
    2. priority vs reasoning consistency (heuristic judgment)
    3. Chinese summary substance                 (heuristic judgment)
    4. routing accuracy vs direction strong_keywords (heuristic judgment)

Writes a TSV (one row per sampled paper) and an HTML report. Strictly
read-only on data/. Offline — no LLM calls.

The judgment dimensions (2/3/4) are deterministic keyword/length
heuristics, NOT semantic analysis. Their limitations are surfaced in the
HTML disclaimer so the user can spot-check.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import html
import json
import pathlib
import random
import re
import sys
from typing import Any

import yaml


ROOT = pathlib.Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "daily"
DIRECTIONS_YAML = ROOT / "config" / "directions.yaml"

# ---- field-completeness contract ---------------------------------------------

EXPECTED_FIELDS = [
    "relevance_to_user",
    "why_not_core",
    "summary_zh.motivation",
    "summary_zh.method",
    "summary_zh.result",
    "summary_zh.validation",
    "summary_en",
    "tags",
    "key_terms",
]

# ---- judgment heuristics (documented; deliberately simple) -------------------

# Dim 2 — phrases that suggest the paper is peripheral/unrelated. If a
# High/Medium-priority paper's reasoning text contains any of these, that's a
# mismatch signal. Kept short and high-precision; false negatives are OK.
NEG_CUES_ZH = [
    "未涉及", "未直接涉及", "未直接", "无关", "不相关", "外围", "背景",
    "并非", "并未", "并不直接", "不属于", "未直接相关", "未直接关联",
    "并不针对", "并未针对", "不直接", "未触及",
]
NEG_CUES_EN = [
    "not directly relevant", "not relevant", "peripheral", "tangential",
    "background only", "unrelated", "does not address", "not focused on",
    "out of scope", "not aligned",
]

# Phrases that suggest the paper is highly relevant. If a Low/Exclude paper's
# reasoning text contains any of these, that's a mismatch signal.
POS_CUES_ZH = [
    "高度相关", "高度契合", "直接相关", "完全相关", "核心", "关键贡献",
    "强相关", "非常契合",
]
POS_CUES_EN = [
    "highly relevant", "directly relevant", "core contribution",
    "strongly aligned", "central to", "key contribution",
]

# Dim 3 — Chinese summary sub-field is "weak" if empty OR shorter than this
# many characters (Chinese is dense; <10 chars rarely says anything paper-
# specific) OR matches a generic-boilerplate regex (template fillers that the
# scorer occasionally produces when it has nothing to say).
ZH_MIN_CHARS = 10
ZH_BOILERPLATE_PATTERNS = [
    re.compile(r"^(本文|本研究|本工作|本论文)(研究|介绍|提出|讨论|探讨)了?[一相某]?(?:种|个)?方法[。.]?$"),
    re.compile(r"^(无|N/?A|none|无相关信息)[。.]?$", re.IGNORECASE),
    re.compile(r"^未提及[。.]?$"),
]

# Dim 4 — routing: count case-insensitive occurrences of each direction's
# strong_keywords in (title + abstract). Compare assigned vs best alternative.
# A small ratio cushion avoids flipping on a single off-by-one hit difference.
ROUTING_OK_RATIO = 0.5   # if assigned >= best_other * 0.5 (and assigned > 0) -> appropriate
ROUTING_QUESTIONABLE = "questionable"
ROUTING_LIKELY_WRONG = "likely_wrong"


# ---- loading ------------------------------------------------------------------

def load_directions() -> dict[str, dict]:
    raw = yaml.safe_load(DIRECTIONS_YAML.read_text(encoding="utf-8"))
    return raw.get("directions", {})


def iter_daily_files() -> list[pathlib.Path]:
    return sorted(DAILY_DIR.glob("*.json"))


def paper_year(paper: dict, fallback_date: str) -> str:
    d = paper.get("date") or fallback_date or ""
    return d[:4] if len(d) >= 4 else "unknown"


def gather_by_year() -> dict[str, list[tuple[str, int, dict]]]:
    """Returns {year: [(filename, paper_index, paper_dict), ...]}.

    Only papers with an `llm` dict are eligible. We hold the paper dicts in
    memory because the corpus is ~100k papers — small enough, and avoids a
    second pass after sampling.
    """
    by_year: dict[str, list[tuple[str, int, dict]]] = collections.defaultdict(list)
    for f in iter_daily_files():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            papers = data.get("papers") or []
            fallback_date = data.get("date", "")
        elif isinstance(data, list):
            papers = data
            fallback_date = f.stem
        else:
            continue
        for i, p in enumerate(papers):
            if not isinstance(p, dict):
                continue
            if not isinstance(p.get("llm"), dict):
                continue
            by_year[paper_year(p, fallback_date)].append((f.name, i, p))
    return by_year


# ---- sampling ----------------------------------------------------------------

def stratified_sample(
    by_year: dict[str, list[tuple[str, int, dict]]],
    n_target: int,
    seed: int,
) -> list[tuple[str, str, int, dict]]:
    """Return list of (year, filename, paper_index, paper_dict).

    Algorithm: floor(2) per year that has any eligible papers; then allocate
    the remainder proportional to year paper-count using a largest-remainder
    method. Final per-year draw is uniform random with seed.
    """
    rng = random.Random(seed)
    years = sorted(by_year.keys())
    n_per_year: dict[str, int] = {y: 0 for y in years}

    # baseline: 2 per year (or all, if a year has <2 papers)
    for y in years:
        n_per_year[y] = min(2, len(by_year[y]))

    used = sum(n_per_year.values())
    remaining = max(0, n_target - used)

    # proportional remainder — largest-remainder method
    if remaining > 0:
        # weights = remaining capacity per year (count minus baseline already taken)
        capacity = {y: max(0, len(by_year[y]) - n_per_year[y]) for y in years}
        total_cap_papers = sum(len(by_year[y]) for y in years if capacity[y] > 0)
        if total_cap_papers > 0:
            quotas = {}
            for y in years:
                if capacity[y] == 0:
                    quotas[y] = 0.0
                    continue
                quotas[y] = remaining * (len(by_year[y]) / total_cap_papers)
            floors = {y: int(q) for y, q in quotas.items()}
            # cap by capacity
            floors = {y: min(floors[y], capacity[y]) for y in years}
            assigned = sum(floors.values())
            leftover = remaining - assigned
            # distribute leftover by fractional remainder, capped by capacity
            remainders = sorted(
                ((y, quotas[y] - floors[y]) for y in years if capacity[y] > floors[y]),
                key=lambda t: -t[1],
            )
            for y, _ in remainders:
                if leftover == 0:
                    break
                if floors[y] < capacity[y]:
                    floors[y] += 1
                    leftover -= 1
            for y in years:
                n_per_year[y] += floors[y]

    sampled: list[tuple[str, str, int, dict]] = []
    for y in years:
        k = n_per_year[y]
        if k == 0:
            continue
        chosen = rng.sample(by_year[y], k)
        for fname, idx, paper in chosen:
            sampled.append((y, fname, idx, paper))
    return sampled


# ---- dim 1: completeness (objective) -----------------------------------------

def _nonempty(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def assess_completeness(llm: dict) -> dict:
    sz = llm.get("summary_zh") if isinstance(llm.get("summary_zh"), dict) else {}
    se = llm.get("summary_en") if isinstance(llm.get("summary_en"), dict) else {}
    field_state: dict[str, bool] = {
        "relevance_to_user": _nonempty(llm.get("relevance_to_user")),
        "why_not_core": _nonempty(llm.get("why_not_core")),
        "summary_zh.motivation": _nonempty(sz.get("motivation")),
        "summary_zh.method": _nonempty(sz.get("method")),
        "summary_zh.result": _nonempty(sz.get("result")),
        "summary_zh.validation": _nonempty(sz.get("validation")),
        # summary_en is a dict; treat populated if any subfield non-empty
        "summary_en": any(_nonempty(se.get(k)) for k in ("motivation", "method", "result", "validation")),
        "tags": _nonempty(llm.get("tags")),
        "key_terms": _nonempty(llm.get("key_terms")),
    }
    missing = [f for f, ok in field_state.items() if not ok]
    pct = 100.0 * (1 - len(missing) / len(EXPECTED_FIELDS))
    return {
        "missing": missing,
        "completeness_pct": round(pct, 1),
        "field_state": field_state,
    }


def is_silent(llm: dict) -> bool:
    """ADR-0017 silent-Low pattern: priority set but the body is empty."""
    pri = (llm.get("priority") or "").strip()
    if not pri:
        return False
    rel = (llm.get("relevance_to_user") or "").strip()
    sz = llm.get("summary_zh") if isinstance(llm.get("summary_zh"), dict) else {}
    motiv = (sz.get("motivation") or "").strip()
    tags = llm.get("tags") or []
    return (not rel) and (not motiv) and (not tags)


# ---- dim 2: consistency (heuristic judgment) ---------------------------------

def _contains_any(text: str, cues: list[str]) -> list[str]:
    t = text or ""
    tl = t.lower()
    hits = []
    for c in cues:
        if c.lower() in tl:
            hits.append(c)
    return hits


def assess_consistency(llm: dict) -> dict:
    """Heuristic: map priority -> expected sentiment, scan reasoning for
    contradicting cues. Returns {verdict, note}. Verdicts:
      consistent / mild_mismatch / clear_mismatch / unknown
    """
    pri = (llm.get("priority") or "").strip()
    rel = llm.get("relevance_to_user") or ""
    wnc = llm.get("why_not_core") or ""
    combined = f"{rel}\n{wnc}"

    if not pri:
        return {"verdict": "unknown", "note": "priority empty"}

    neg = _contains_any(combined, NEG_CUES_ZH + NEG_CUES_EN)
    pos = _contains_any(combined, POS_CUES_ZH + POS_CUES_EN)

    high_priority = pri in ("High", "Medium")
    low_priority = pri in ("Low", "Exclude")

    if high_priority and neg and not pos:
        # e.g. "High" but reasoning literally says 未涉及 / not relevant
        return {
            "verdict": "clear_mismatch",
            "note": f"priority={pri} but reasoning contains: {', '.join(neg[:3])}",
        }
    if low_priority and pos and not neg:
        return {
            "verdict": "clear_mismatch",
            "note": f"priority={pri} but reasoning contains: {', '.join(pos[:3])}",
        }
    if high_priority and neg and pos:
        return {
            "verdict": "mild_mismatch",
            "note": f"priority={pri} reasoning mixes positive+negative cues",
        }
    if not rel.strip() and not wnc.strip():
        return {"verdict": "unknown", "note": "no reasoning text to check"}
    return {"verdict": "consistent", "note": ""}


# ---- dim 3: zh summary substance (heuristic judgment) ------------------------

def _zh_subfield_weak(text: str | None) -> bool:
    if not text or not text.strip():
        return True
    t = text.strip()
    if len(t) < ZH_MIN_CHARS:
        return True
    for rx in ZH_BOILERPLATE_PATTERNS:
        if rx.match(t):
            return True
    return False


def assess_zh_substance(llm: dict) -> dict:
    sz = llm.get("summary_zh") if isinstance(llm.get("summary_zh"), dict) else {}
    subs = ["motivation", "method", "result", "validation"]
    weak = [s for s in subs if _zh_subfield_weak(sz.get(s))]
    if len(weak) == 0:
        verdict = "substantive"
    elif len(weak) == 4:
        verdict = "vague_or_empty"
    elif len(weak) >= 3:
        verdict = "vague_or_empty"
    else:
        verdict = "partly_vague"
    return {"verdict": verdict, "weak_fields": weak}


# ---- dim 4: routing (heuristic judgment) -------------------------------------

def _count_kw_hits(text: str, kws: list[str]) -> int:
    """Case-insensitive substring count (each keyword counted once if present)."""
    tl = (text or "").lower()
    n = 0
    for k in kws:
        if k.lower() in tl:
            n += 1
    return n


def assess_routing(paper: dict, directions: dict[str, dict]) -> dict:
    assigned = paper.get("direction") or ""
    title = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    haystack = f"{title}\n{abstract}"

    scores: dict[str, int] = {}
    for d_key, d_cfg in directions.items():
        kws = d_cfg.get("strong_keywords") or []
        scores[d_key] = _count_kw_hits(haystack, kws)

    assigned_score = scores.get(assigned, 0)
    other_scores = {k: v for k, v in scores.items() if k != assigned}
    best_other = max(other_scores.values(), default=0)
    best_other_dir = max(other_scores, key=other_scores.get, default="") if other_scores else ""

    if assigned == "" or assigned not in directions:
        return {
            "verdict": ROUTING_QUESTIONABLE,
            "note": f"unrecognized direction '{assigned}'",
            "suggested": best_other_dir if best_other > 0 else "",
            "scores": scores,
        }

    if assigned_score == 0 and best_other == 0:
        return {
            "verdict": ROUTING_QUESTIONABLE,
            "note": "no strong_keyword hits in assigned or any other direction",
            "suggested": "",
            "scores": scores,
        }
    if assigned_score >= best_other:
        return {
            "verdict": "appropriate",
            "note": f"assigned={assigned_score} >= best_other={best_other}",
            "suggested": "",
            "scores": scores,
        }
    if assigned_score == 0 and best_other > 0:
        return {
            "verdict": ROUTING_LIKELY_WRONG,
            "note": f"0 hits in assigned vs {best_other} in {best_other_dir}",
            "suggested": best_other_dir,
            "scores": scores,
        }
    if best_other > 0 and assigned_score >= best_other * ROUTING_OK_RATIO:
        return {
            "verdict": "appropriate",
            "note": f"assigned={assigned_score} close to best_other={best_other} ({best_other_dir})",
            "suggested": "",
            "scores": scores,
        }
    if best_other > assigned_score > 0:
        return {
            "verdict": ROUTING_QUESTIONABLE,
            "note": f"assigned={assigned_score} < best_other={best_other} ({best_other_dir})",
            "suggested": best_other_dir,
            "scores": scores,
        }
    # both zero, or some edge case
    return {
        "verdict": ROUTING_QUESTIONABLE,
        "note": f"no strong_keyword hits in any direction",
        "suggested": "",
        "scores": scores,
    }


# ---- per-paper row ------------------------------------------------------------

def build_row(
    year: str,
    fname: str,
    idx: int,
    paper: dict,
    directions: dict[str, dict],
) -> dict:
    llm = paper.get("llm") or {}
    comp = assess_completeness(llm)
    cons = assess_consistency(llm)
    zh = assess_zh_substance(llm)
    rt = assess_routing(paper, directions)
    return {
        "year": year,
        "file": fname,
        "doi": paper.get("doi", ""),
        "title": paper.get("title", "") or "",
        "direction": paper.get("direction", ""),
        "priority": (llm.get("priority") or "") or "None",
        "scorer_failed": bool(llm.get("scorer_failed")),
        "scorer_failed_reason": llm.get("scorer_failed_reason", ""),
        "silent": is_silent(llm),
        "completeness_pct": comp["completeness_pct"],
        "missing_fields": comp["missing"],
        "consistency_verdict": cons["verdict"],
        "consistency_note": cons["note"],
        "zh_substance_verdict": zh["verdict"],
        "zh_weak_fields": zh["weak_fields"],
        "routing_verdict": rt["verdict"],
        "routing_note": rt["note"],
        "routing_suggested": rt["suggested"],
        "routing_scores": rt["scores"],
    }


# ---- aggregation --------------------------------------------------------------

def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    by_year = collections.Counter(r["year"] for r in rows)
    silent_n = sum(1 for r in rows if r["silent"])
    failed_n = sum(1 for r in rows if r["scorer_failed"])
    mean_comp = round(sum(r["completeness_pct"] for r in rows) / n, 1) if n else 0
    pri = collections.Counter(r["priority"] for r in rows)
    by_dir = collections.Counter(r["direction"] for r in rows)
    cons = collections.Counter(r["consistency_verdict"] for r in rows)
    zh = collections.Counter(r["zh_substance_verdict"] for r in rows)
    rt = collections.Counter(r["routing_verdict"] for r in rows)
    return {
        "n": n,
        "by_year": dict(sorted(by_year.items())),
        "silent_n": silent_n,
        "failed_n": failed_n,
        "mean_completeness_pct": mean_comp,
        "priority_dist": dict(pri),
        "direction_dist": dict(by_dir),
        "consistency_dist": dict(cons),
        "zh_substance_dist": dict(zh),
        "routing_dist": dict(rt),
    }


# ---- writers ------------------------------------------------------------------

TSV_COLUMNS = [
    "year", "file", "doi", "title", "direction", "priority",
    "scorer_failed", "silent", "completeness_pct", "missing_fields",
    "consistency_verdict", "consistency_note",
    "zh_substance_verdict", "zh_weak_fields",
    "routing_verdict", "routing_note",
]


def _trunc(s: str, n: int = 100) -> str:
    s = (s or "").replace("\n", " ").replace("\t", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def write_tsv(rows: list[dict], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(TSV_COLUMNS)]
    for r in rows:
        cells = [
            r["year"],
            r["file"],
            r["doi"],
            _trunc(r["title"], 120),
            r["direction"],
            r["priority"],
            "1" if r["scorer_failed"] else "0",
            "1" if r["silent"] else "0",
            f"{r['completeness_pct']:.1f}",
            ",".join(r["missing_fields"]),
            r["consistency_verdict"],
            _trunc(r["consistency_note"], 200),
            r["zh_substance_verdict"],
            ",".join(r["zh_weak_fields"]),
            r["routing_verdict"],
            _trunc(r["routing_note"], 200),
        ]
        # tabs/newlines already stripped in _trunc; replace residual tabs in raw strs
        cells = [c.replace("\t", " ").replace("\n", " ") for c in cells]
        lines.append("\t".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


HTML_CSS = """
:root{--c-brand:#1B4D7E;--c-bg:#FAFAF7;--c-card-bg:#FFFFFF;--c-card-border:#ECEAE3;
--c-text-primary:#1F2937;--c-text-secondary:#4B5563;--c-text-meta:#8B8980;--c-text-muted:#B5B3AA;
--c-bad:#C8362A;--c-warn:#E89C3A;--c-ok:#27500A;--c-fact:#185FA5}
*{box-sizing:border-box}
body{font-family:-apple-system,'PingFang SC',sans-serif;background:var(--c-bg);
  color:var(--c-text-primary);max-width:1400px;margin:2rem auto;padding:0 1rem;line-height:1.45}
h1{font-size:24px;font-weight:600;margin:0 0 .25rem;color:var(--c-brand)}
h2{font-size:15px;font-weight:600;color:var(--c-brand);margin:1.25rem 0 .5rem}
h3{font-size:13px;font-weight:600;color:var(--c-text-secondary);margin:.75rem 0 .25rem}
.meta{font-size:12px;color:var(--c-text-meta);margin-bottom:1rem}
.card{background:var(--c-card-bg);border:1px solid var(--c-card-border);
  border-radius:12px;padding:14px 18px;font-size:13px;margin:.75rem 0}
.card.fact{border-left:4px solid var(--c-fact)}
.card.opinion{border-left:4px solid var(--c-warn)}
.card.opinion .label{color:var(--c-warn);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.card.fact .label{color:var(--c-fact);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 18px;font-size:13px;margin-top:6px}
.kv dt{color:var(--c-text-secondary)}
.kv dd{margin:0}
.disclaimer{font-size:12px;color:var(--c-text-secondary);background:#FFF6E6;border:1px solid #F0D58A;
  border-radius:8px;padding:10px 14px;margin:.75rem 0}
table.records{width:100%;border-collapse:collapse;font-size:12px;background:var(--c-card-bg);
  border:1px solid var(--c-card-border);border-radius:12px;overflow:hidden;margin-top:.5rem}
table.records th{text-align:left;padding:8px 10px;background:var(--c-bg);font-weight:600;
  color:var(--c-text-secondary);border-bottom:1px solid var(--c-card-border);font-size:11px;
  position:sticky;top:0}
table.records td{padding:6px 10px;border-bottom:1px solid var(--c-card-border);vertical-align:top}
table.records tr:last-child td{border-bottom:none}
table.records tr.flagged{background:#FFF6F4}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600;display:inline-block}
.pill--high{color:#C8362A;background:#FCE7E4}
.pill--medium{color:#E89C3A;background:#FDF1DE}
.pill--low{color:#8B8980;background:#F0EFE9}
.pill--exclude{color:#B5B3AA;background:#F5F4EF}
.v-good{color:var(--c-ok)}
.v-warn{color:var(--c-warn);font-weight:600}
.v-bad{color:var(--c-bad);font-weight:700}
.muted{color:var(--c-text-meta)}
"""


def _verdict_css(verdict: str) -> str:
    bad = {"clear_mismatch", "vague_or_empty", "likely_wrong"}
    warn = {"mild_mismatch", "partly_vague", "questionable"}
    if verdict in bad:
        return "v-bad"
    if verdict in warn:
        return "v-warn"
    if verdict in {"consistent", "substantive", "appropriate"}:
        return "v-good"
    return "muted"


def _priority_css(pri: str) -> str:
    return {
        "High": "pill pill--high",
        "Medium": "pill pill--medium",
        "Low": "pill pill--low",
        "Exclude": "pill pill--exclude",
    }.get(pri, "pill pill--exclude")


def _esc(s: Any) -> str:
    return html.escape(str(s) if s is not None else "")


def write_html(
    rows: list[dict],
    agg: dict,
    path: pathlib.Path,
    n_target: int,
    seed: int,
    generated_at: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    by_year_html = " · ".join(f"{y}:{c}" for y, c in agg["by_year"].items())
    pri_html = " · ".join(f"{k}:{v}" for k, v in agg["priority_dist"].items())
    dir_html = " · ".join(f"{k}:{v}" for k, v in agg["direction_dist"].items())
    cons_html = " · ".join(f"{k}:{v}" for k, v in agg["consistency_dist"].items())
    zh_html = " · ".join(f"{k}:{v}" for k, v in agg["zh_substance_dist"].items())
    rt_html = " · ".join(f"{k}:{v}" for k, v in agg["routing_dist"].items())

    parts: list[str] = []
    parts.append(f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<title>Radar corpus quality audit · {generated_at}</title><style>{HTML_CSS}</style></head><body>
<h1>Radar corpus quality audit</h1>
<div class='meta'>generated {_esc(generated_at)} · sample target n={n_target} · seed={seed} · sampled n={agg['n']}</div>

<div class='card fact'><span class='label'>Aggregate objective metrics (hard facts)</span>
<dl class='kv'>
<dt>N sampled</dt><dd>{agg['n']}</dd>
<dt>By year</dt><dd>{_esc(by_year_html)}</dd>
<dt>Silent (priority set but body empty)</dt><dd>{agg['silent_n']} / {agg['n']}</dd>
<dt>scorer_failed=True</dt><dd>{agg['failed_n']} / {agg['n']}</dd>
<dt>Mean completeness</dt><dd>{agg['mean_completeness_pct']}%</dd>
<dt>Priority distribution</dt><dd>{_esc(pri_html)}</dd>
<dt>Direction distribution</dt><dd>{_esc(dir_html)}</dd>
</dl></div>

<div class='card opinion'><span class='label'>Judgment summary (heuristic — Claude Code's opinion)</span>
<dl class='kv'>
<dt>Consistency (priority vs reasoning)</dt><dd>{_esc(cons_html)}</dd>
<dt>Chinese summary substance</dt><dd>{_esc(zh_html)}</dd>
<dt>Routing accuracy</dt><dd>{_esc(rt_html)}</dd>
</dl>
<div class='disclaimer'><b>How to read this section.</b> Dimensions 2/3/4 are
<i>deterministic keyword/length heuristics</i>, not semantic analysis. They
flag candidates for the user to spot-check, not ground truth.
<ul>
<li><b>Consistency</b>: flags cases where the reasoning text contains
strong "peripheral" cues (未涉及, peripheral, not relevant…) but the
priority is High/Medium, or vice versa. Subtle mismatches are invisible
to this heuristic.</li>
<li><b>ZH substance</b>: a Chinese sub-field is "weak" if empty, &lt;{ZH_MIN_CHARS}
characters, or matches a generic-boilerplate regex. Real substance is
not measured — long ≠ substantive, but short ≈ vague is a reasonable
prior for Chinese scientific summaries.</li>
<li><b>Routing</b>: counts strong_keyword overlap from
<code>config/directions.yaml</code> against title+abstract. If another
direction has more hits than the assigned one, this flags it. Real
papers can straddle multiple directions, so a flag means "look at it",
not "wrong".</li>
</ul>
</div></div>

<h2>Per-paper detail ({agg['n']} rows)</h2>
<table class='records'><thead><tr>
<th>year</th><th>direction</th><th>priority</th><th>flags</th>
<th>completeness</th>
<th>consistency</th><th>zh substance</th><th>routing</th>
<th>title / DOI</th>
</tr></thead><tbody>
""")

    bad_verdicts = {"clear_mismatch", "vague_or_empty", "likely_wrong"}
    for r in rows:
        flagged = (
            r["consistency_verdict"] in bad_verdicts
            or r["zh_substance_verdict"] in bad_verdicts
            or r["routing_verdict"] in bad_verdicts
            or r["silent"]
            or r["scorer_failed"]
        )
        flag_cells = []
        if r["scorer_failed"]:
            flag_cells.append("<span class='v-bad'>scorer_failed</span>")
        if r["silent"]:
            flag_cells.append("<span class='v-bad'>silent</span>")
        flag_html = " ".join(flag_cells) or "<span class='muted'>—</span>"

        cv = r["consistency_verdict"]
        zv = r["zh_substance_verdict"]
        rv = r["routing_verdict"]
        cv_html = f"<span class='{_verdict_css(cv)}'>{_esc(cv)}</span>"
        if r["consistency_note"]:
            cv_html += f"<br><span class='muted'>{_esc(_trunc(r['consistency_note'], 120))}</span>"
        zv_html = f"<span class='{_verdict_css(zv)}'>{_esc(zv)}</span>"
        if r["zh_weak_fields"]:
            zv_html += f"<br><span class='muted'>weak: {_esc(','.join(r['zh_weak_fields']))}</span>"
        rv_html = f"<span class='{_verdict_css(rv)}'>{_esc(rv)}</span>"
        if r["routing_note"]:
            rv_html += f"<br><span class='muted'>{_esc(_trunc(r['routing_note'], 120))}</span>"
        if r["routing_suggested"] and r["routing_suggested"] != r["direction"]:
            rv_html += f"<br><span class='muted'>suggest: {_esc(r['routing_suggested'])}</span>"

        comp_html = f"{r['completeness_pct']:.0f}%"
        if r["missing_fields"]:
            comp_html += f"<br><span class='muted'>missing: {_esc(','.join(r['missing_fields']))}</span>"

        doi = r["doi"]
        doi_link = f"<a href='https://doi.org/{_esc(doi)}'>{_esc(doi)}</a>" if doi else "<span class='muted'>(no DOI)</span>"
        title_html = f"{_esc(_trunc(r['title'], 140))}<br><span class='muted'>{doi_link} · {_esc(r['file'])}#{r.get('idx','')}</span>"

        cls = "flagged" if flagged else ""
        parts.append(
            f"<tr class='{cls}'><td>{_esc(r['year'])}</td>"
            f"<td>{_esc(r['direction'])}</td>"
            f"<td><span class='{_priority_css(r['priority'])}'>{_esc(r['priority'])}</span></td>"
            f"<td>{flag_html}</td>"
            f"<td>{comp_html}</td>"
            f"<td>{cv_html}</td>"
            f"<td>{zv_html}</td>"
            f"<td>{rv_html}</td>"
            f"<td>{title_html}</td></tr>"
        )

    parts.append("</tbody></table></body></html>")
    path.write_text("".join(parts), encoding="utf-8")


# ---- stdout summary -----------------------------------------------------------

def print_summary(agg: dict, tsv_path: pathlib.Path, html_path: pathlib.Path) -> None:
    print("=" * 72)
    print("AGGREGATE OBJECTIVE METRICS (hard facts)")
    print("=" * 72)
    print(f"N sampled                  : {agg['n']}")
    print(f"By year                    : {agg['by_year']}")
    print(f"Silent (priority set, body empty): {agg['silent_n']} / {agg['n']}")
    print(f"scorer_failed=True         : {agg['failed_n']} / {agg['n']}")
    print(f"Mean completeness          : {agg['mean_completeness_pct']}%")
    print(f"Priority distribution      : {agg['priority_dist']}")
    print(f"Direction distribution     : {agg['direction_dist']}")
    print()
    print("=" * 72)
    print("JUDGMENT SUMMARY (heuristic — Claude Code's opinion, may be wrong)")
    print("=" * 72)
    print(f"Consistency (pri vs reason): {agg['consistency_dist']}")
    print(f"ZH summary substance       : {agg['zh_substance_dist']}")
    print(f"Routing accuracy           : {agg['routing_dist']}")
    print()
    print(f"TSV  -> {tsv_path}")
    print(f"HTML -> {html_path}")


# ---- main --------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    today = dt.date.today().isoformat()
    default_tsv = ROOT / "scripts" / "verification" / f"corpus_quality_audit_{today}.tsv"
    default_html = ROOT / "scripts" / "verification" / f"corpus_quality_audit_{today}.html"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=50, help="target sample size (default 50)")
    ap.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    ap.add_argument("--out-tsv", type=pathlib.Path, default=default_tsv)
    ap.add_argument("--out-html", type=pathlib.Path, default=default_html)
    args = ap.parse_args(argv)

    directions = load_directions()
    by_year = gather_by_year()
    sampled = stratified_sample(by_year, args.n, args.seed)

    rows: list[dict] = []
    for year, fname, idx, paper in sampled:
        row = build_row(year, fname, idx, paper, directions)
        row["idx"] = idx
        rows.append(row)

    # stable sort: year asc, then direction
    rows.sort(key=lambda r: (r["year"], r["direction"], r["doi"]))

    agg = aggregate(rows)
    write_tsv(rows, args.out_tsv)
    write_html(
        rows, agg, args.out_html,
        n_target=args.n, seed=args.seed,
        generated_at=dt.datetime.now().isoformat(timespec="seconds"),
    )
    print_summary(agg, args.out_tsv, args.out_html)
    return 0


if __name__ == "__main__":
    sys.exit(main())
