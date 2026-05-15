"""LLM scorer (v2): loads system prompt from versioned file under prompts/,
captures the actual model snapshot for manifest reproducibility."""

from __future__ import annotations
import json
import os
import pathlib
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.environ.get("MODEL_NAME", "deepseek-v4-flash")
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

ACTIVE_PROMPT_FILE = os.environ.get("SCORER_PROMPT_FILE", "scorer_v3.txt")

_PROMPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "prompts"


def _load_system_prompt() -> str:
    p = _PROMPTS_DIR / ACTIVE_PROMPT_FILE
    if not p.exists():
        raise FileNotFoundError(f"Scorer prompt not found: {p}")
    return p.read_text(encoding="utf-8")


def get_active_prompt_path() -> pathlib.Path:
    return _PROMPTS_DIR / ACTIVE_PROMPT_FILE


def score(paper: dict, direction_focus: str) -> dict:
    system_prompt = _load_system_prompt()

    user_msg = f"""Direction this paper was routed to: {paper.get('direction_name', 'unknown')}

Direction-specific evaluation focus:
{direction_focus}

Paper:
Title: {paper['title']}
Venue: {paper.get('venue', 'unknown')}
Year: {paper.get('year', 'unknown')}
Citations: {paper.get('cited_by_count', 0)}
Abstract: {paper['abstract'][:3000]}

Output JSON only."""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=TEMPERATURE,
        max_tokens=800,
    )
    parsed = json.loads(resp.choices[0].message.content)
    parsed["_raw_model"] = getattr(resp, "model", "")
    return parsed


def score_batch(papers: list[dict], direction_configs: dict) -> tuple[list[dict], list[dict]]:
    out: list[dict] = []
    raws: list[dict] = []
    for p in papers:
        direction = p.get("direction")
        focus = direction_configs.get(direction, {}).get("llm_prompt_focus", "")
        try:
            result = score(p, focus)
            raws.append({"_raw_model": result.pop("_raw_model", "")})
            p["llm"] = result
        except Exception as e:
            p["llm"] = {"priority": "Low", "priority_reason": f"scoring failed: {e}"}
            raws.append({})
        out.append(p)
    return out, raws
