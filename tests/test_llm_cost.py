"""ADR-0030 §12: scorer cost controls — thinking off by default, token usage
captured per call and summarised into the manifest, daily cron in DeepSeek's
off-peak window.

Run with:
    pytest tests/test_llm_cost.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import llm_scorer  # noqa: E402  (conftest sets OPENAI_API_KEY)
from pipeline import manifest as mf  # noqa: E402

_GOOD = json.dumps({"priority": "High", "relevance_to_user": "yes", "tags": ["t"],
                    "summary_zh": {"motivation": "动机"}})
_DIRECTIONS = {"hip_implant": {"llm_prompt_focus": "focus"}}


def _paper(doi="10.1/x"):
    return {"doi": doi, "title": "T", "abstract": "A", "direction": "hip_implant",
            "direction_name": "Hip", "venue": "V", "year": 2026, "cited_by_count": 0}


def _resp(content, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        model="deepseek-flash", usage=usage,
    )


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    llm_scorer.reset_budget_state()
    monkeypatch.setattr(llm_scorer, "_log_scoring_failure", lambda *a, **k: None)
    monkeypatch.setattr(llm_scorer, "_LLM_CONCURRENCY", 1)


def _install(monkeypatch, responses):
    calls = []
    it = iter(responses)

    def fake_create(**kwargs):
        calls.append(kwargs)
        item = next(it)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(llm_scorer.client.chat.completions, "create", fake_create)
    return calls


# ---------------------------------------------------------------------------
# thinking off
# ---------------------------------------------------------------------------

def test_scorer_disables_thinking_by_default(monkeypatch):
    calls = _install(monkeypatch, [_resp(_GOOD)])
    llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert llm_scorer.THINKING == "disabled"


def test_thinking_can_be_enabled_for_experiments(monkeypatch):
    monkeypatch.setattr(llm_scorer, "THINKING", "enabled")
    calls = _install(monkeypatch, [_resp(_GOOD)])
    llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


# ---------------------------------------------------------------------------
# usage accounting
# ---------------------------------------------------------------------------

def test_usage_is_captured_per_call_and_summed(monkeypatch):
    usage_a = SimpleNamespace(prompt_tokens=2500, completion_tokens=700,
                              prompt_cache_hit_tokens=2100, prompt_cache_miss_tokens=400,
                              completion_tokens_details=SimpleNamespace(reasoning_tokens=0))
    usage_b = {"prompt_tokens": 2400, "completion_tokens": 3200,
               "prompt_cache_hit_tokens": 2100, "prompt_cache_miss_tokens": 300,
               "completion_tokens_details": {"reasoning_tokens": 2500}}
    _install(monkeypatch, [_resp(_GOOD, usage_a), _resp(_GOOD, usage_b)])

    out, raws = llm_scorer.score_batch([_paper("10.1/a"), _paper("10.1/b")], _DIRECTIONS)

    assert "_usage" not in out[0]["llm"] and "_raw_model" not in out[0]["llm"]
    assert raws[0]["_usage"]["completion_tokens"] == 700
    assert raws[1]["_usage"]["reasoning_tokens"] == 2500
    total = llm_scorer.summarize_usage(raws)
    assert total == {"calls": 2, "prompt_tokens": 4900, "cache_hit_tokens": 4200,
                     "cache_miss_tokens": 700, "completion_tokens": 3900,
                     "reasoning_tokens": 2500}


def test_missing_usage_is_tolerated(monkeypatch):
    _install(monkeypatch, [_resp(_GOOD)])  # usage=None
    _out, raws = llm_scorer.score_batch([_paper()], _DIRECTIONS)
    assert raws[0]["_usage"] == {}
    assert llm_scorer.summarize_usage(raws)["calls"] == 0
    assert llm_scorer.summarize_usage(None)["completion_tokens"] == 0


# ---------------------------------------------------------------------------
# manifest estimate
# ---------------------------------------------------------------------------

def test_manifest_reports_usage_and_list_price_estimate(tmp_path):
    raws = [{"_raw_model": "deepseek-flash",
             "_usage": {"calls": 1, "prompt_tokens": 2500, "cache_hit_tokens": 2100,
                        "cache_miss_tokens": 400, "completion_tokens": 700,
                        "reasoning_tokens": 0}}] * 100
    off_peak = dt.datetime(2026, 9, 19, 12, 0, tzinfo=dt.timezone.utc)  # Saturday
    est = mf.summarize_llm_usage(raws, now=off_peak)
    assert est["usage"]["calls"] == 100
    assert est["price_window"] == "off_peak"
    # 100 calls x (2100*0.003 + 400*0.15 + 700*0.60)/1e6 USD = 0.04863
    assert est["estimated_usd"] == pytest.approx(0.0486, abs=0.001)
    assert est["estimated_usd_per_call"] == pytest.approx(0.000486, abs=0.00002)

    peak = dt.datetime(2026, 9, 17, 8, 30, tzinfo=dt.timezone.utc)  # Thursday 08:30
    assert mf.price_window(peak) == "peak"
    assert mf.summarize_llm_usage(raws, now=peak)["estimated_usd"] == pytest.approx(0.0973, abs=0.001)

    prompt = tmp_path / "scorer_v3.txt"
    prompt.write_text("p", encoding="utf-8")
    config = tmp_path / "directions.yaml"
    config.write_text("directions: {}", encoding="utf-8")
    manifest = mf.build_manifest(config_path=config, prompt_path=prompt,
                                 sources_used={}, counts={}, llm_responses=raws)
    assert manifest["llm"]["thinking"] == "disabled"
    assert manifest["llm"]["usage"]["completion_tokens"] == 70000
    assert manifest["llm"]["estimated_usd"] > 0
    assert manifest["llm"]["model_snapshot_observed"] == "deepseek-flash"


def test_price_window_boundaries():
    mon = lambda h, m=0: dt.datetime(2026, 9, 21, h, m, tzinfo=dt.timezone.utc)  # Monday
    assert mf.price_window(mon(0, 59)) == "off_peak"
    assert mf.price_window(mon(1, 0)) == "peak"
    assert mf.price_window(mon(3, 59)) == "peak"
    assert mf.price_window(mon(4, 0)) == "off_peak"
    assert mf.price_window(mon(6, 0)) == "peak"
    assert mf.price_window(mon(9, 59)) == "peak"
    assert mf.price_window(mon(10, 0)) == "off_peak"
    assert mf.price_window(dt.datetime(2026, 9, 19, 8, 0, tzinfo=dt.timezone.utc)) == "off_peak"  # Saturday


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------

def test_daily_cron_stays_off_peak_even_with_github_delay():
    daily = yaml.safe_load((REPO_ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    minute, hour = daily[True]["schedule"][0]["cron"].split()[:2]
    assert minute.isdigit() and int(minute) != 0
    # Off-peak runs 10:00 UTC -> 01:00 UTC; a start between 10:00 and 20:00
    # keeps a run (plus up to 5 h of scheduler delay) inside that window.
    assert 10 <= int(hour) <= 20
