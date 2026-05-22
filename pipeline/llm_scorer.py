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
    # ADR-0017 follow-up: hard timeout + SDK-level retries so a hung
    # DeepSeek connection cannot stall the whole backfill. Observed a
    # 38-minute hang on api.deepseek.com (3.173.21.63:443) with no
    # timeout set — the SDK default left the socket blocking indefinitely.
    timeout=float(os.environ.get("LLM_TIMEOUT", "60")),
    max_retries=int(os.environ.get("LLM_MAX_RETRIES", "3")),
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


# ADR-0017 §Decision 1: bounded retry for transient scoring failures.
# Attempts 2 and 3 prepend this nudge to the system prompt to combat the
# top observed failure modes (empty response, markdown-fenced JSON,
# unterminated string, unescaped quote inside Chinese fields).
_STRICT_JSON_NUDGE = (
    "CRITICAL: Output ONLY valid JSON. No markdown fences. "
    "No commentary. No prose before or after."
)
_MAX_SCORE_ATTEMPTS = 3


def score(paper: dict, direction_focus: str,
          system_prompt_prefix: str = "") -> dict:
    """Score one paper. `system_prompt_prefix` is prepended to the system
    prompt (ADR-0017 §Decision 1, retry attempts 2 and 3 pass the
    strict-JSON nudge; empty string for the first attempt keeps the
    historical prompt path bit-identical).
    """
    system_prompt = _load_system_prompt()
    if system_prompt_prefix:
        system_prompt = system_prompt_prefix + "\n\n" + system_prompt

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


_LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "8"))


def _score_one_paper(p: dict, direction_configs: dict) -> tuple[dict, dict]:
    """Score a single paper with ADR-0017 3-attempt retry. Returns
    (paper_with_llm_set, raw_dict). Mutates p["llm"] in place and also
    returns p so the caller can keep input ordering. This is the unit of
    work dispatched to the thread pool by :func:`score_batch`.
    """
    direction = p.get("direction")
    focus = direction_configs.get(direction, {}).get("llm_prompt_focus", "")
    result: dict | None = None
    last_exc: BaseException | None = None
    for attempt in range(1, _MAX_SCORE_ATTEMPTS + 1):
        prefix = "" if attempt == 1 else _STRICT_JSON_NUDGE
        try:
            result = score(p, focus, system_prompt_prefix=prefix)
            break
        except Exception as e:
            last_exc = e
            raw_text = getattr(e, "raw_content", None)
            _log_scoring_failure(p, raw_text, e)
    if result is not None:
        raw = {"_raw_model": result.pop("_raw_model", "")}
        p["llm"] = result
    else:
        # ADR-0017 §Decision 1: null + flag, never the silent "Low".
        p["llm"] = {
            "priority": None,
            "scorer_failed": True,
            "scorer_failed_reason": str(last_exc),
            "scorer_failed_attempts": _MAX_SCORE_ATTEMPTS,
        }
        raw = {}
    return p, raw


def score_batch(papers: list[dict], direction_configs: dict) -> tuple[list[dict], list[dict]]:
    """Score every paper with ADR-0017 §Decision 1 retry semantics,
    dispatched concurrently across a thread pool.

    Each paper is given up to 3 attempts (see :func:`_score_one_paper`):
    attempt 1 uses the historical prompt verbatim; attempts 2 and 3
    prepend the strict-JSON nudge. On success the paper's ``llm`` dict
    carries the parsed scorer output. When all 3 attempts fail, ``llm``
    becomes ``{"priority": None, "scorer_failed": True, ...}`` — Python
    ``None`` (JSON ``null``), NOT ``"Low"``.

    Concurrency: papers are scored in parallel via a ThreadPoolExecutor
    with ``LLM_CONCURRENCY`` workers (default 8). DeepSeek tolerates this
    (verified 10-way concurrent with zero 429s). The OpenAI SDK client is
    thread-safe. Output ordering matches input ordering regardless of
    completion order, so downstream bucket-writing is deterministic.
    Per-paper retry/failure logging is unchanged — each worker runs the
    same 3-attempt loop independently.
    """
    if not papers:
        return [], []

    # Single-worker fast path keeps behaviour identical when concurrency
    # is disabled (LLM_CONCURRENCY=1), useful for debugging / tests.
    workers = max(1, min(_LLM_CONCURRENCY, len(papers)))
    if workers == 1:
        out: list[dict] = []
        raws: list[dict] = []
        for p in papers:
            sp, raw = _score_one_paper(p, direction_configs)
            out.append(sp)
            raws.append(raw)
        return out, raws

    import concurrent.futures as _cf
    # Preserve input order: map each future to its index, fill a sized list.
    out_slots: list[dict | None] = [None] * len(papers)
    raw_slots: list[dict | None] = [None] * len(papers)
    with _cf.ThreadPoolExecutor(max_workers=workers) as ex:
        fut_to_idx = {
            ex.submit(_score_one_paper, p, direction_configs): i
            for i, p in enumerate(papers)
        }
        for fut in _cf.as_completed(fut_to_idx):
            i = fut_to_idx[fut]
            sp, raw = fut.result()
            out_slots[i] = sp
            raw_slots[i] = raw
    return [p for p in out_slots if p is not None], [r if r is not None else {} for r in raw_slots]
