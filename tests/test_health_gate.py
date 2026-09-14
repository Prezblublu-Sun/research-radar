"""Health gate semantics after ADR-0030.

The gate blocks the workflow only when the day's data is missing or largely
unscored. A single failed source, a partial_success status, a truncated
OpenAlex window, or low counts are warnings: the data was committed and the
Pages deploy (gated on this workflow's conclusion) must still run.
"""

from pipeline.health_gate import evaluate, main, warnings


def test_success_is_healthy():
    assert evaluate({"run_status": "success", "quality_flags": []}) == []
    assert warnings({"run_status": "success", "quality_flags": []}) == []


def test_single_source_failure_is_a_warning_not_a_block():
    # 2026-09-13: arXiv 429, 782 OpenAlex papers saved, site left stale.
    manifest = {
        "run_status": "partial_success",
        "quality_flags": ["arxiv_failed"],
        "counts": {"scorer_failed": 0, "priority_counts": {"Medium": 13}},
    }
    assert evaluate(manifest) == []
    assert warnings(manifest) == ["run_status=partial_success", "arxiv_failed"]


def test_truncation_and_low_counts_are_warnings():
    manifest = {
        "run_status": "success",
        "quality_flags": ["low_fetch_count", "openalex_truncated",
                          "zero_high_medium"],
        "counts": {"scorer_failed": 0, "priority_counts": {"Low": 3}},
    }
    assert evaluate(manifest) == []
    assert warnings(manifest) == [
        "low_fetch_count", "openalex_truncated", "zero_high_medium"
    ]


def test_failed_status_and_fetched_zero_block():
    manifest = {"run_status": "failed", "quality_flags": ["fetched_zero"]}
    assert evaluate(manifest) == ["run_status=failed", "fetched_zero"]
    assert warnings(manifest) == []


def test_missing_status_blocks():
    assert evaluate({}) == ["run_status=missing"]


def test_one_scorer_failure_among_many_is_a_warning():
    manifest = {
        "run_status": "success",
        "quality_flags": ["scorer_failed"],
        "counts": {"scorer_failed": 1,
                   "priority_counts": {"High": 2, "Medium": 10, "Low": 30}},
    }
    assert evaluate(manifest) == []
    assert warnings(manifest) == ["scorer_failed"]


def test_scorer_failing_on_most_papers_blocks():
    manifest = {
        "run_status": "success",
        "quality_flags": ["scorer_failed"],
        "counts": {"scorer_failed": 40,
                   "priority_counts": {"High": 0, "Medium": 3, "Low": 5}},
    }
    assert evaluate(manifest) == ["scorer_failed"]


def test_scorer_failing_on_every_paper_blocks():
    manifest = {
        "run_status": "success",
        "quality_flags": ["scorer_failed"],
        "counts": {"scorer_failed": 7, "priority_counts": {}},
    }
    assert evaluate(manifest) == ["scorer_failed"]


def test_manifest_without_counts_treats_scorer_failed_as_warning():
    # Pre-ADR-0017 manifests carry no counts; keep the conservative reading.
    manifest = {"run_status": "success", "quality_flags": ["scorer_failed"]}
    assert evaluate(manifest) == []
    assert warnings(manifest) == ["scorer_failed"]


def test_main_exit_codes_and_annotations(tmp_path, capsys):
    import json

    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "2026-09-13.json").write_text(json.dumps({
        "run_status": "partial_success",
        "quality_flags": ["arxiv_failed"],
        "counts": {"scorer_failed": 0, "priority_counts": {"Medium": 13}},
    }), encoding="utf-8")
    (manifests / "2026-06-15.json").write_text(json.dumps({
        "run_status": "failed",
        "quality_flags": ["fetched_zero"],
    }), encoding="utf-8")

    assert main(["--date", "2026-09-13", "--manifests-dir", str(manifests)]) == 0
    out = capsys.readouterr().out
    assert "::warning::" in out and "arxiv_failed" in out
    assert "::error::" not in out

    assert main(["--date", "2026-06-15", "--manifests-dir", str(manifests)]) == 1
    out = capsys.readouterr().out
    assert "::error::" in out and "fetched_zero" in out

    assert main(["--date", "2026-09-12", "--manifests-dir", str(manifests)]) == 1
    assert "manifest is missing" in capsys.readouterr().out
