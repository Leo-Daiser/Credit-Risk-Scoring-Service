"""HTTP smoke test for a running demo or public-safe deployment."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: Any


class HttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult: ...


class UrllibHttpClient:
    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode()
                return HttpResult(response.status, _decode_body(raw))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            return HttpResult(exc.code, _decode_body(raw))


def _decode_body(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def sign_hmac_sha256(payload: dict[str, Any], secret: str) -> str:
    canonical = json.dumps(
        {key: value for key, value in payload.items() if value is not None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def band_only_profile() -> dict[str, Any]:
    return {
        "age_band": "31_45",
        "income_band": "100k_150k",
        "employment_type": "employee",
        "requested_amount_band": "100k_300k",
        "term_months": 24,
        "existing_monthly_payments_band": "lt_10k",
        "credit_history_band": "good",
        "loan_purpose": "cash",
        "consent_to_process": True,
    }


def _expect(result: HttpResult, expected: set[int], label: str) -> None:
    if result.status not in expected:
        raise RuntimeError(f"{label}: expected {sorted(expected)}, got {result.status}")


def run_smoke(
    client: HttpClient,
    *,
    base_url: str,
    frontend_url: str,
    mode: str,
    postback_secret: str | None = None,
) -> list[str]:
    base = base_url.rstrip("/")
    frontend = frontend_url.rstrip("/")
    checks: list[str] = []

    for path in ("/", "/assessment", "/credit-calculator", "/offers"):
        _expect(client.request("GET", frontend + path), {200}, f"frontend {path}")
        checks.append(f"frontend:{path}")
    _expect(client.request("GET", base + "/health"), {200}, "backend health")
    _expect(client.request("GET", base + "/ready"), {200}, "backend readiness")
    checks.extend(("backend:/health", "backend:/ready"))

    profile = band_only_profile()
    score = client.request("POST", base + "/v1/profile/score", payload=profile)
    _expect(score, {200}, "privacy-light profile")
    match = client.request(
        "POST",
        base + "/v1/offers/match",
        payload={"profile": profile, "limit": 3, "context": {"source": "smoke"}},
    )
    _expect(match, {200}, "offer matching")
    offers = match.body.get("offers", [])
    if not offers:
        raise RuntimeError("offer matching: no active smoke-test offer")
    click = client.request(
        "POST",
        base + f"/v1/offers/{offers[0]['offer_id']}/click",
        payload={"profile_id": match.body["profile_result"]["anonymous_profile_id"]},
    )
    _expect(click, {200}, "tracked click")
    checks.extend(("api:profile", "api:match", "api:click"))

    smoke_run_id = uuid4().hex
    postback = {
        "postback_id": f"smoke-postback-{smoke_run_id}",
        "partner_id": "demo",
        "click_id": click.body["click_id"],
        "status": "application_started",
    }
    if mode == "public":
        for url in (
            frontend + "/commercial",
            frontend + "/operator",
            frontend + "/api/backend/v1/analytics/commercial-summary",
            base + "/docs",
            base + "/openapi.json",
            base + "/metrics",
            base + "/v1/runtime/status",
        ):
            _expect(client.request("GET", url), {404}, f"public boundary {url}")
        _expect(
            client.request("POST", base + "/v1/partner/postback", payload=postback),
            {404},
            "public demo postback boundary",
        )
        checks.append("public-boundaries")
    else:
        if not postback_secret:
            raise RuntimeError("demo postback smoke requires --postback-secret or environment value")
        signature = sign_hmac_sha256(postback, postback_secret)
        valid = client.request(
            "POST",
            base + "/v1/partner/postback",
            payload=postback,
            headers={"X-Postback-Signature": signature},
        )
        _expect(valid, {200}, "valid demo postback")
        invalid = client.request(
            "POST",
            base + "/v1/partner/postback",
            payload={**postback, "postback_id": f"smoke-postback-invalid-{smoke_run_id}"},
            headers={"X-Postback-Signature": "invalid"},
        )
        _expect(invalid, {401, 429}, "invalid demo postback")
        checks.append("demo-postback-hmac")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--mode", choices=("demo", "public"), default=os.getenv("APP_ENV", "demo"))
    parser.add_argument(
        "--postback-secret",
        default=os.getenv("PARTNER_POSTBACK_SECRET"),
        help="Demo-only HMAC secret; never printed.",
    )
    args = parser.parse_args()
    checks = run_smoke(
        UrllibHttpClient(),
        base_url=args.base_url,
        frontend_url=args.frontend_url,
        mode=args.mode,
        postback_secret=args.postback_secret,
    )
    print(f"Public demo smoke passed ({len(checks)} checks).")


if __name__ == "__main__":
    main()
