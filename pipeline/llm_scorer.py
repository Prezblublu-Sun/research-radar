"""LLM scorer (v2): loads system prompt from versioned file under prompts/,
captures the actual model snapshot for manifest reproducibility.

Scoring-failure recovery (per ADR-0016):
- max_tokens is overridable via LLM_MAX_TOKENS env var (default 2000, up from 800)
- on failure, raw LLM response (when available) is persisted under
  data/llm_cache/failures/YYYY-MM-DD_<doi-slug>.json for offline debugging /
  later retry. No raw response is kept on the success path.
"""

from __future__ import annotations
import json
import os
import pathlib
from datetime import datetime, timezone
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.environ.get("MODEL_NAME", "deepseek-v4-flash")
TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

ACTIVE_PROMPT_FILE = os.environ.get("SCORER_PROMPT_FILE", "scorer_v3.txt")

_PROMPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "prompts"
_FAILURES_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "llm_cache" / "failures"


def _load_system_prompt() -> str:
    p = _PROMPTS_DIR / ACTIVE_PROMPT_FILE
    if not p.exists():
        raise FileNotFoundError(f"Scorer prompt not found: {p}")
    return p.read_text(encoding="utf-8")


def get_active_prompt_path() -> pathlib.Path:
    return _PROMPTS_DIR / ACTIVE_PROMPT_FILE


def _slug_for_filename(s: str) -> str:
    """DOI-safe filename fragment. Replaces '/' and '\\' since DOIs like
    10.3390/polym17070917 contain forward slashes."""
    if not s:
        return "noid"
    return s.replace("/", "_").replace("\\", "_").strip()[:120] or "noid"


def _log_scoring_failure(paper: dict, raw_response: str | None, exc: BaseException) -> pathlib.Path | None:
    """Persist a single failed scoring call to data/llm_cache/failures/.

    Filename: YYYY-MM-DD_<doi-slug>.json. If a file already exists for the
    same date+doi (same paper failing twice in one day), a counter suffix is
    appended so prior payloads are never overwritten.

    Best-effort: never raises. A failure here must not break score_batch.
    """
    try:
        _FAILURES_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        doi_or_id = paper.get("doi") or paper.get("arxiv_id") or paper.get("id") or "noid"
        slug = _slug_for_filename(doi_or_id)
        base_name = f"{date_str}_{slug}"
        path = _FAILURES_DIR / f"{base_name}.json"
        counter = 1
        while path.exists():
            path = _FAILURES_DIR / f"{base_name}_{counter}.json"
            counter += 1
        payload = {
            "timestamp_utc": now.isoformat(),
            "doi": paper.get("doi"),
            "arxiv_id": paper.get("arxiv_id"),
            "title": (paper.get("title") or "")[:300],
            "direction": paper.get("direction"),
            "direction_name": paper.get("direction_name"),
            "error_class": type(exc).__name__,
            "error_message": str(exc),
            "raw_response": raw_response,
            "raw_response_captured": raw_response is not None,
            "model": MODEL,
            "prompt_file": ACTIVE_PROMPT_FILE,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None  # best-effort logging; do not propagate


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
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2000")),
    )
    raw_content = resp.choices[0].message.content
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as e:
        # Attach raw text so score_batch's except block can log it without
        # needing access to `resp` (which is local to this function).
        e.raw_content = raw_content  # type: ignore[attr-defined]
        raise
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
            # Capture raw LLM text if score() attached it (JSON-decode case);
            # otherwise fall back to the exception string (network errors etc).
            raw_text = getattr(e, "raw_content", None)
            _log_scoring_failure(p, raw_text, e)
            p["llm"] = {"priority": "Low", "priority_reason": f"scoring failed: {e}"}
            raws.append({})
        out.append(p)
    return out, raws
