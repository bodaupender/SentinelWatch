"""Bounded, process-local API rate limiting.

For deployments with multiple API workers or replicas, enforce equivalent limits
at a shared gateway because each worker owns an independent bucket table.
"""

from collections import OrderedDict
from dataclasses import dataclass
import math
import threading
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketRateLimiter:
    """Thread-safe token buckets with bounded key storage."""

    def __init__(self, max_keys: int = 20_000):
        self.max_keys = max(1, max_keys)
        self._buckets: OrderedDict[tuple[str, str], _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def consume(
        self,
        category: str,
        client_key: str,
        limit_per_minute: int,
        burst: int,
        now: Optional[float] = None,
    ) -> tuple[bool, int]:
        """Consume a request token; return allowed and retry-after seconds."""
        rate = max(1, int(limit_per_minute)) / 60.0
        capacity = max(1, int(burst))
        timestamp = time.monotonic() if now is None else now
        key = (category, client_key)

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(capacity), updated_at=timestamp)
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, timestamp - bucket.updated_at)
                bucket.tokens = min(float(capacity), bucket.tokens + elapsed * rate)
                bucket.updated_at = timestamp
                self._buckets.move_to_end(key)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                retry_after = 0
                allowed = True
            else:
                retry_after = max(1, math.ceil((1.0 - bucket.tokens) / rate))
                allowed = False

            while len(self._buckets) > self.max_keys:
                self._buckets.popitem(last=False)
            return allowed, retry_after


def _rate_limit_for_path(path: str, config):
    if not path.startswith("/api/"):
        return None
    if path.startswith("/api/v1/agent/v1/register"):
        return "register", config.register_limit, config.register_burst
    if path.startswith("/api/v1/auth/"):
        return "auth", config.auth_limit, config.auth_burst
    if path.startswith("/api/v1/agent/v1/"):
        return "agent", config.agent_limit, config.agent_burst
    return "default", config.default_limit, config.default_burst


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config, limiter: Optional[TokenBucketRateLimiter] = None):
        super().__init__(app)
        self.config = config
        self.limiter = limiter or TokenBucketRateLimiter()

    async def dispatch(self, request: Request, call_next):
        limits = _rate_limit_for_path(request.url.path, self.config)
        if not self.config.enabled or limits is None or request.method == "OPTIONS":
            return await call_next(request)

        category, limit, burst = limits
        client_key = request.client.host if request.client else "unknown"
        allowed, retry_after = self.limiter.consume(category, client_key, limit, burst)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry later."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
