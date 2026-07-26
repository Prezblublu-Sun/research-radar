from pipeline.health_gate import evaluate


def test_success_is_healthy():
    assert evaluate({"run_status": "success", "quality_flags": []}) == []


def test_partial_and_controlled_failures_are_unhealthy():
    reasons = evaluate({
        "run_status": "partial_success",
        "quality_flags": ["low_fetch_count", "openalex_failed",
                          "scorer_failed"],
    })
    assert reasons == [
        "run_status=partial_success", "openalex_failed", "scorer_failed"
    ]
