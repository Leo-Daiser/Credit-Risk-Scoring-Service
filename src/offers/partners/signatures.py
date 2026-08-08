from __future__ import annotations

import hashlib
import hmac
import json
from secrets import compare_digest
from typing import Any


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        {key: value for key, value in payload.items() if value is not None},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def sign_hmac_sha256(payload: dict[str, Any], secret: str) -> str:
    return hmac.new(secret.encode(), canonical_payload_bytes(payload), hashlib.sha256).hexdigest()


def verify_hmac_sha256(payload: dict[str, Any], signature: str, secret: str | None) -> bool:
    if not secret or not signature:
        return False
    return compare_digest(sign_hmac_sha256(payload, secret), signature)
