from __future__ import annotations

import hashlib
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from src.core.config import settings


class InMemoryRateLimiter:
    """Single-process sliding-window limiter; replaceable by a Redis adapter later."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, bucket: str, key: str, limit: int, window_seconds: int) -> int:
        now = self._clock()
        cutoff = now - window_seconds
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {bucket}. Retry later.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
            return max(0, limit - len(hits))

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = InMemoryRateLimiter()


def _client_key(request: Request) -> str:
    session_key = request.headers.get("X-Anonymous-Session-ID", "").strip()
    source = session_key or (request.client.host if request.client else "unknown")
    return hashlib.sha256(source.encode()).hexdigest()


def _limit_for(bucket: str) -> int:
    return {
        "profile_score": settings.rate_limit_profile_score,
        "offer_match": settings.rate_limit_offer_match,
        "offer_click": settings.rate_limit_offer_click,
        "public_event": settings.rate_limit_public_event,
        "partner_postback": settings.rate_limit_partner_postback,
        "invalid_postback": settings.rate_limit_invalid_postback,
    }[bucket]


def rate_limit(bucket: str):
    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        limiter.check(
            bucket,
            _client_key(request),
            _limit_for(bucket),
            settings.rate_limit_window_seconds,
        )

    return dependency


def record_invalid_postback(request: Request) -> None:
    if not settings.rate_limit_enabled:
        return
    limiter.check(
        "invalid_postback",
        _client_key(request),
        settings.rate_limit_invalid_postback,
        settings.rate_limit_window_seconds,
    )
