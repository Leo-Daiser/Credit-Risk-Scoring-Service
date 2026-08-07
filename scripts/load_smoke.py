"""Dependency-free concurrent smoke test for the running scoring API."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

DEFAULT_FEATURES: dict[str, Any] = {
    "AMT_INCOME_TOTAL": 180_000,
    "AMT_CREDIT": 450_000,
    "AMT_ANNUITY": 24_000,
    "AGE_YEARS": 37,
    "NAME_CONTRACT_TYPE": "Cash loans",
    "EXT_SOURCE_2": 0.61,
    "EXT_SOURCE_3": 0.48,
}


@dataclass(frozen=True)
class RequestResult:
    latency_ms: float
    status_code: int | None
    error: str | None


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return float(ordered[index])


def summarize_results(
    results: list[RequestResult],
    elapsed_seconds: float,
    model_version: str,
) -> dict[str, Any]:
    latencies = [result.latency_ms for result in results]
    failures = [result for result in results if result.error is not None]
    status_counts: dict[str, int] = {}
    for result in results:
        key = str(result.status_code) if result.status_code is not None else "transport_error"
        status_counts[key] = status_counts.get(key, 0) + 1
    total = len(results)
    return {
        "model_version": model_version,
        "requests": total,
        "successful_requests": total - len(failures),
        "failed_requests": len(failures),
        "error_rate": len(failures) / total if total else 0.0,
        "elapsed_seconds": elapsed_seconds,
        "throughput_requests_per_second": total / elapsed_seconds if elapsed_seconds else 0.0,
        "latency_ms": {
            "min": min(latencies, default=0.0),
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies, default=0.0),
        },
        "status_counts": status_counts,
        "failure_samples": [result.error for result in failures[:5]],
    }


def fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310 - operator URL
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected a JSON object from {url}.")
    return payload


def load_features(path: str | None) -> dict[str, Any]:
    if path is None:
        return dict(DEFAULT_FEATURES)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("features"), dict):
        payload = payload["features"]
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Load-smoke payload must be a non-empty JSON feature object.")
    return payload


def validate_payload_contract(features: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required_features")
    if not isinstance(required, list):
        raise ValueError("Feature schema response has no required_features list.")
    missing = sorted(feature for feature in required if feature not in features)
    if missing:
        raise ValueError(f"Load-smoke payload is missing required features: {missing}.")
    feature_count = int(schema.get("feature_count", 0))
    if feature_count <= 0:
        raise ValueError("Feature schema response has an invalid feature_count.")
    non_null_count = sum(value is not None for value in features.values())
    coverage = non_null_count / feature_count
    minimum_coverage = float(schema.get("min_feature_coverage", 0.0))
    if coverage < minimum_coverage:
        raise ValueError(
            f"Load-smoke payload coverage {coverage:.4f} is below {minimum_coverage:.4f}."
        )


def score_once(
    score_url: str,
    features: dict[str, Any],
    run_id: str,
    request_number: int,
    timeout_seconds: float,
    api_key: str | None,
    expected_model_version: str,
    require_persisted_log: bool,
) -> RequestResult:
    request_id = f"load-smoke-{run_id}-{request_number}"
    body = json.dumps({"request_id": request_id, "features": features}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-ID": request_id,
    }
    if api_key:
        headers["X-API-Key"] = api_key
    request = Request(score_url, data=body, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - operator URL
            response_payload = json.loads(response.read().decode("utf-8"))
            status_code = int(response.status)
        if status_code != 200:
            error = f"Unexpected HTTP {status_code}"
        elif not isinstance(response_payload, dict):
            error = "Scoring response is not a JSON object"
        elif response_payload.get("model_version") != expected_model_version:
            error = (
                "Scoring response model version changed during the run: "
                f"{response_payload.get('model_version')!r} != {expected_model_version!r}"
            )
        elif require_persisted_log and response_payload.get("logging_status") != "persisted":
            error = (
                "Scoring audit log was not persisted: "
                f"{response_payload.get('logging_status')!r}"
            )
        else:
            error = None
    except HTTPError as exc:
        status_code = int(exc.code)
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        error = f"HTTP {status_code}: {detail}"
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        status_code = None
        error = f"Invalid scoring response: {exc}"
    except (TimeoutError, URLError, OSError) as exc:
        status_code = None
        error = f"{type(exc).__name__}: {exc}"
    return RequestResult(
        latency_ms=(time.perf_counter() - started) * 1000.0,
        status_code=status_code,
        error=error,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--warmup-requests", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-p95-ms", type=float, default=1_500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument(
        "--allow-unpersisted",
        action="store_true",
        help="Do not require logging_status=persisted in successful responses.",
    )
    parser.add_argument("--payload", help="Optional JSON feature object or score payload.")
    parser.add_argument(
        "--output",
        default="artifacts/reports/load_smoke_report.json",
        help="Gitignored JSON report path; pass an empty value to disable writing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.requests <= 0 or args.concurrency <= 0 or args.warmup_requests < 0:
        raise ValueError("requests/concurrency must be positive and warmup must be non-negative.")
    if args.timeout_seconds <= 0 or args.max_p95_ms <= 0:
        raise ValueError("timeout-seconds and max-p95-ms must be positive.")
    if not 0.0 <= args.max_error_rate <= 1.0:
        raise ValueError("max-error-rate must be within [0, 1].")

    base_url = args.base_url.rstrip("/")
    ready = fetch_json(f"{base_url}/ready", args.timeout_seconds)
    if ready.get("status") != "ready":
        raise RuntimeError(f"Service is not ready: {ready}.")
    schema = fetch_json(f"{base_url}/feature_schema", args.timeout_seconds)
    features = load_features(args.payload)
    validate_payload_contract(features, schema)
    model_version = str(ready.get("model_version", "unknown"))
    api_key = os.environ.get("API_KEY") or None
    run_id = uuid4().hex[:12]
    score_url = f"{base_url}/score"

    for index in range(args.warmup_requests):
        result = score_once(
            score_url,
            features,
            run_id,
            -index - 1,
            args.timeout_seconds,
            api_key,
            model_version,
            not args.allow_unpersisted,
        )
        if result.error:
            raise RuntimeError(f"Warmup request failed: {result.error}")

    started = time.perf_counter()
    results: list[RequestResult] = []
    with ThreadPoolExecutor(max_workers=min(args.concurrency, args.requests)) as executor:
        futures = [
            executor.submit(
                score_once,
                score_url,
                features,
                run_id,
                index,
                args.timeout_seconds,
                api_key,
                model_version,
                not args.allow_unpersisted,
            )
            for index in range(args.requests)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed_seconds = time.perf_counter() - started
    report = summarize_results(results, elapsed_seconds, model_version)
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["base_url"] = base_url
    report["concurrency"] = min(args.concurrency, args.requests)
    report["objectives"] = {
        "max_p95_ms": args.max_p95_ms,
        "max_error_rate": args.max_error_rate,
    }
    report["passed"] = (
        report["latency_ms"]["p95"] <= args.max_p95_ms
        and report["error_rate"] <= args.max_error_rate
    )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
