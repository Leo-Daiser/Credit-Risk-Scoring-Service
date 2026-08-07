import pytest

from scripts.load_smoke import (
    RequestResult,
    percentile,
    summarize_results,
    validate_payload_contract,
)


def test_load_smoke_summary_uses_nearest_rank_percentiles():
    results = [RequestResult(float(value), 200, None) for value in range(1, 101)]
    results.append(RequestResult(150.0, 503, "HTTP 503"))

    report = summarize_results(results, elapsed_seconds=10.0, model_version="model-v1")

    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert report["requests"] == 101
    assert report["successful_requests"] == 100
    assert report["failed_requests"] == 1
    assert report["status_counts"] == {"200": 100, "503": 1}
    assert report["latency_ms"]["p95"] == 96.0
    assert report["throughput_requests_per_second"] == pytest.approx(10.1)


def test_load_smoke_payload_must_match_live_contract():
    schema = {
        "feature_count": 100,
        "required_features": ["AGE", "INCOME"],
        "min_feature_coverage": 0.03,
    }

    with pytest.raises(ValueError, match="missing required features"):
        validate_payload_contract({"AGE": 30, "OTHER": 1, "THIRD": 2}, schema)
    with pytest.raises(ValueError, match="coverage"):
        validate_payload_contract({"AGE": 30, "INCOME": None, "THIRD": 2}, schema)

    validate_payload_contract({"AGE": 30, "INCOME": 100_000, "THIRD": 2}, schema)
