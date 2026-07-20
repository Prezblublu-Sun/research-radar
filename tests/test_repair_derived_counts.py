from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import v2_schema as v2
from scripts import repair_derived_counts as repair


def _write_bucket(path: pathlib.Path) -> dict:
    data = {
        "schema_version": "v2",
        "date": path.stem,
        "date_precision": "day",
        "custom_meta": {"keep": True},
        "papers": [
            {"doi": "10.1/high", "source": "openalex",
             "direction": "fea_surrogate", "llm": {"priority": "High"}},
            {"doi": "10.1/medium", "source": "pubmed",
             "direction": "hip_implant", "llm": {"priority": "Medium"}},
        ],
        "counts": {"fetched_total": 2, "scored": 2,
                   "priority_counts": {"Low": 2}},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return data


def test_dry_run_reports_mismatch_without_writing(tmp_path):
    target = tmp_path / "daily" / "2024-01-02.json"
    _write_bucket(target)
    before = target.read_bytes()

    stats = repair.audit_counts(target.parent)

    assert stats == {"scanned": 1, "mismatched": 1,
                     "repaired": 0, "skipped": 0}
    assert target.read_bytes() == before


def test_apply_repairs_counts_preserves_payload_and_is_idempotent(tmp_path):
    target = tmp_path / "daily" / "2024-01-02.json"
    original = _write_bucket(target)

    first = repair.audit_counts(target.parent, apply=True)
    repaired = json.loads(target.read_text(encoding="utf-8"))

    assert first["repaired"] == 1
    assert repaired["counts"] == v2.build_v2_counts(repaired["papers"])
    assert repaired["papers"] == original["papers"]
    assert repaired["custom_meta"] == {"keep": True}

    after_first = target.read_bytes()
    second = repair.audit_counts(target.parent, apply=True)
    assert second["mismatched"] == 0
    assert second["repaired"] == 0
    assert target.read_bytes() == after_first
