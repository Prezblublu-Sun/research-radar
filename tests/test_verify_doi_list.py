"""Tests for scripts/verify_doi_list.py — the DOI verification audit tool.

The tool is read-only: it indexes a v2 corpus snapshot and reports radar's
verdict per input DOI. These tests build a tiny synthetic v2 corpus in
``tmp_path`` and exercise the CLI/library entry points end-to-end.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import verify_doi_list as vd  # noqa: E402


# Trim directions.yaml to just enough for the router keyword check; mirrors
# the shape pipeline.direction_router consumes.
DIRECTIONS_YAML = """
version: 1
directions:
  hip_implant:
    display_name: "Hip Implant"
    color: "#1D9E75"
    sources:
      openalex_keywords: ["femoral stem", "stress shielding"]
      pubmed_terms: ["femoral stem design"]
    strong_keywords:
      - "femoral stem"
      - "stress shielding"
      - "press-fit"
  fea_surrogate:
    display_name: "FEA & Surrogate"
    color: "#D85A30"
    sources:
      openalex_keywords: ["finite element", "surrogate model"]
      pubmed_terms: []
    strong_keywords:
      - "finite element analysis"
      - "neural operator"
"""


def _paper(doi: str, priority: str, title: str,
           direction: str = "hip_implant") -> dict:
    return {
        "source": "openalex",
        "doi": doi,
        "arxiv_id": "",
        "title": title,
        "authors": ["A. Author"],
        "venue": "Test Journal",
        "year": 2024,
        "date": "2024-05-10",
        "date_precision": "day",
        "direction": direction,
        "direction_name": "Hip Implant" if direction == "hip_implant"
        else "FEA & Surrogate",
        "scorer_version": "v3",
        "llm": {
            "priority": priority,
            "summary_zh": {"motivation": "动机内容,验证应力遮挡问题"},
            "summary_en": {"motivation": "Synthetic motivation"},
            "relevance_to_user": "Directly relevant to femoral-stem topic.",
            "tags": ["#stress_shielding"],
            "key_terms": [],
            "flags": {},
        },
    }


def _write_bucket(daily: pathlib.Path, date: str, papers: list[dict]) -> None:
    daily.mkdir(parents=True, exist_ok=True)
    (daily / f"{date}.json").write_text(
        json.dumps({
            "schema_version": "v2",
            "date": date,
            "date_precision": "day",
            "papers": papers,
            "counts": {"fetched_total": len(papers), "scored": len(papers)},
        }, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture()
def env(tmp_path: pathlib.Path):
    daily = tmp_path / "data" / "daily"
    _write_bucket(daily, "2024-05-10", [
        _paper("10.1/h1", "High", "Stress-shielding-aware femoral stem"),
        _paper("10.1/m1", "Medium", "Mid-relevance hip paper"),
        _paper("10.1/x1", "High", "Over-scored peripheral paper"),
    ])
    cfg = tmp_path / "directions.yaml"
    cfg.write_text(DIRECTIONS_YAML, encoding="utf-8")
    return tmp_path, daily, cfg


def _run(env, tsv_lines: list[str], extra: list[str] | None = None) -> dict:
    tmp_path, daily, cfg = env
    inp = tmp_path / "input.tsv"
    inp.write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")
    argv = [str(inp),
            "--corpus-root", str(daily),
            "--directions-yaml", str(cfg)] + (extra or [])
    return vd.run(argv)


# --------------------------------------------------------------------------

def test_in_corpus_doi_reports_priority_direction_url(env, capsys):
    res = _run(env, ["10.1/h1\tmust_read\tstress shielding"])
    r = res["records"][0]
    assert r["in_corpus"] is True
    assert r["radar_priority"] == "High"
    assert r["direction"] == "hip_implant"
    assert r["bucket_date"] == "2024-05-10"
    # The URL uses the same anchor scheme as render.build_pages._anchor_id
    # for an identity_key of "doi:<doi>": every non-[A-Za-z0-9_-] -> "-".
    assert r["daily_page_url"].endswith("2024-05-10.html#doi-10-1-h1")
    assert r["verdict"] == "correct_must_read"
    # stdout includes the aggregate header so the CLI output is non-empty
    out = capsys.readouterr().out
    assert "DOI verification report" in out


def test_missing_doi_reports_miss_reason(env, capsys):
    # 2008 embedded in DOI -> out_of_window (pre-2015 backfill scope)
    res = _run(env, ["10.1016/j.clinbiomech.2008.11.003\tmust_read\tinitial stability"])
    r = res["records"][0]
    assert r["in_corpus"] is False
    assert r["miss_reason"] == "out_of_window"
    assert r["verdict"] == "missing_must_read"

    # Modern missing DOI with topic that overlaps a direction keyword
    res = _run(env, ["10.9999/zzz\tperipheral\tfemoral stem ALA design"])
    r = res["records"][0]
    assert r["in_corpus"] is False
    assert r["miss_reason"] == "direction_match_possible"
    assert r["verdict"] == "missing_peripheral"

    # Modern missing DOI whose topic has no router-keyword overlap
    res = _run(env, ["10.9999/yyy\tuseful\tunrelated condensed-matter topic"])
    r = res["records"][0]
    assert r["miss_reason"] == "direction_mismatch_likely"
    assert r["verdict"] == "missing_useful"


def test_aggregate_summary_counts_across_tiers(env, capsys):
    res = _run(env, [
        "10.1/h1\tmust_read\t",                # in corpus, High -> correct_must_read
        "10.1/m1\tuseful\t",                   # in corpus, Medium -> correct_useful
        "10.1/x1\tperipheral\t",               # in corpus, High -> over_scored
        "10.9999/miss\tmust_read\tfemoral stem",  # missing must_read
    ])
    agg = res["aggregate"]
    assert agg["n"] == 4
    assert agg["n_in"] == 3 and agg["n_miss"] == 1

    pt = agg["per_tier"]
    assert pt["must_read"]["total"] == 2
    assert pt["must_read"]["H"] == 1
    assert pt["must_read"]["missing"] == 1
    assert pt["useful"]["total"] == 1 and pt["useful"]["M"] == 1
    assert pt["peripheral"]["total"] == 1 and pt["peripheral"]["H"] == 1

    verdicts = [r["verdict"] for r in res["records"]]
    assert "correct_must_read" in verdicts
    assert "correct_useful" in verdicts
    assert "over_scored" in verdicts
    assert "missing_must_read" in verdicts


def test_out_tsv_round_trips_through_csv_reader(env, tmp_path):
    out = tmp_path / "report.tsv"
    _run(env, ["10.1/h1\tmust_read\t", "10.1/m1\tuseful\t"],
         extra=["--out", str(out)])
    text = out.read_text(encoding="utf-8")
    reader = csv.reader(text.splitlines(), delimiter="\t")
    header = next(reader)
    rows = list(reader)
    for required in ("doi", "author_priority", "verdict",
                     "radar_priority", "daily_page_url"):
        assert required in header
    assert len(rows) == 2
    assert all(len(row) == len(header) for row in rows)
    # The first record is the High in-corpus DOI, verdict correct_must_read
    rec = dict(zip(header, rows[0]))
    assert rec["doi"] == "10.1/h1"
    assert rec["radar_priority"] == "High"
    assert rec["verdict"] == "correct_must_read"


def test_out_html_contains_pill_and_doi_count(env, tmp_path):
    out = tmp_path / "report.html"
    _run(env, [
        "10.1/h1\tmust_read\t",
        "10.1/m1\tuseful\t",
        "10.9999/miss\tmust_read\t",
    ], extra=["--out-html", str(out)])
    h = out.read_text(encoding="utf-8")
    assert "pill pill--high" in h
    assert "pill pill--medium" in h
    assert "pill pill--missing" in h  # the missing DOI gets the missing pill
    assert "3 DOIs" in h
    # Token scale is inlined so the HTML stays in radar's visual language
    assert "--c-priority-h" in h


def test_stdin_input_accepted(env, monkeypatch):
    _tmp, daily, cfg = env
    monkeypatch.setattr(sys, "stdin", io.StringIO("10.1/h1\tmust_read\t\n"))
    res = vd.run(["-",
                  "--corpus-root", str(daily),
                  "--directions-yaml", str(cfg)])
    assert res["records"][0]["radar_priority"] == "High"
    assert res["records"][0]["verdict"] == "correct_must_read"


def test_bare_doi_list_without_ground_truth(env):
    res = _run(env, ["10.1/h1", "10.1/m1"])
    for r in res["records"]:
        assert r["author_priority"] == "" and r["topic"] == ""
        assert r["verdict"] == "no_ground_truth"
