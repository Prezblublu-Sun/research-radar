"""Direction router: routes papers to one or more research directions based on
strong_keywords + must_pair_with rules. Applies universal exclusions."""

from __future__ import annotations
import re


def _text(paper: dict) -> str:
    return f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()


def _contains(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term.lower())}\b", text) is not None


def _is_excluded(text: str, exclusions: dict) -> bool:
    for term in exclusions.get("hard_exclude_if_only_about", []):
        if _contains(text, term):
            anchors = ["bioprinting", "biofabrication", "bioink", "femoral",
                       "hip implant", "stem", "implant", "biomechanics",
                       "biomedical", "bone", "osseointegration", "scaffold"]
            if not any(_contains(text, a) for a in anchors):
                return True
    return False


def _score_direction(text: str, cfg: dict) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []

    for kw in cfg.get("strong_keywords", []):
        if _contains(text, kw):
            score += 2.0
            matched.append(kw)

    for pair in cfg.get("must_pair_with", []):
        if all(_contains(text, term) for term in pair):
            score += 3.0
            matched.append(" + ".join(pair))

    return score, matched


def route(paper: dict, directions_cfg: dict, exclusions: dict,
          min_score: float = 2.0) -> dict:
    text = _text(paper)

    if _is_excluded(text, exclusions):
        paper["directions"] = []
        paper["direction"] = None
        paper["routing_reason"] = "excluded by hard rule"
        return paper

    scored: list[tuple[str, float, list[str]]] = []
    for dir_key, cfg in directions_cfg.items():
        s, m = _score_direction(text, cfg)
        if s >= min_score:
            scored.append((dir_key, s, m))

    scored.sort(key=lambda x: x[1], reverse=True)
    paper["directions"] = [s[0] for s in scored]
    paper["direction"] = scored[0][0] if scored else None
    paper["direction_name"] = (
        directions_cfg[paper["direction"]]["display_name"] if paper["direction"] else None
    )
    paper["routing_matches"] = {s[0]: s[2] for s in scored}
    return paper


def filter_routed(papers: list[dict]) -> list[dict]:
    return [p for p in papers if p.get("direction")]


def apply_crossover_boost(papers: list[dict]) -> int:
    """ADR-0021: papers routed into BOTH rl_world_model AND fea_surrogate
    get priority bumped one level. The only boost rule. Returns count of
    papers boosted. Idempotent."""
    BUMP = {"Low": "Medium", "Medium": "High"}
    boosted = 0
    for p in papers:
        dirs = set(p.get("directions") or [])
        if {"rl_world_model", "fea_surrogate"} <= dirs:
            llm = p.get("llm") or {}
            if llm.get("priority_boosted"):
                continue
            pri = llm.get("priority")
            if pri in BUMP:
                llm["priority_pre_boost"] = pri
                llm["priority"] = BUMP[pri]
                llm["priority_boosted"] = True
                llm["boost_reason"] = "RL × FEA/surrogate crossover (ADR-0021)"
                p["llm"] = llm
                boosted += 1
    return boosted
