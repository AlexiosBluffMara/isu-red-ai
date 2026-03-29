"""ISU ReD AI — Rate limiting and caching middleware.

Provides in-process rate limiting (token bucket) and response caching
for the FastAPI app. Designed for single-instance Cloud Run deployments.
"""

import hashlib
import time
from collections import defaultdict
from functools import wraps
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


# ── Token Bucket Rate Limiter ─────────────────────────────────────────

class TokenBucket:
    """Per-IP token bucket for rate limiting."""

    __slots__ = ("capacity", "refill_rate", "_buckets")

    def __init__(self, capacity: int = 30, refill_per_second: float = 2.0):
        self.capacity = capacity
        self.refill_rate = refill_per_second
        self._buckets: dict[str, list[float]] = {}  # ip → [tokens, last_refill]

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def allow(self, request: Request) -> bool:
        ip = self._get_client_ip(request)
        now = time.monotonic()

        if ip not in self._buckets:
            self._buckets[ip] = [self.capacity - 1, now]
            return True

        tokens, last_refill = self._buckets[ip]
        elapsed = now - last_refill
        tokens = min(self.capacity, tokens + elapsed * self.refill_rate)
        self._buckets[ip] = [tokens - 1, now]

        if tokens < 1:
            return False

        # Periodic cleanup (every ~100 checks, evict stale entries)
        if len(self._buckets) > 1000:
            cutoff = now - 300
            self._buckets = {
                k: v for k, v in self._buckets.items() if v[1] > cutoff
            }

        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate-limit API endpoints using a token bucket."""

    def __init__(self, app, requests_per_second: float = 2.0, burst: int = 30):
        super().__init__(app)
        self.bucket = TokenBucket(capacity=burst, refill_per_second=requests_per_second)

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit API endpoints (not static, health, or pages)
        if request.url.path.startswith("/api/"):
            if not self.bucket.allow(request):
                return JSONResponse(
                    {"error": "Rate limit exceeded. Please slow down."},
                    status_code=429,
                    headers={"Retry-After": "5"},
                )
        return await call_next(request)


# ── Response Cache ────────────────────────────────────────────────────

class ResponseCache:
    """Simple in-memory TTL cache for API responses."""

    def __init__(self, default_ttl: int = 300):
        self.default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def _make_key(self, path: str, query: str) -> str:
        raw = f"{path}?{query}" if query else path
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, path: str, query: str = "") -> Any | None:
        key = self._make_key(path, query)
        if key in self._store:
            expires, data = self._store[key]
            if time.monotonic() < expires:
                return data
            del self._store[key]
        return None

    def set(self, path: str, query: str, data: Any, ttl: int | None = None):
        key = self._make_key(path, query)
        self._store[key] = (time.monotonic() + (ttl or self.default_ttl), data)
        # Evict expired entries periodically
        if len(self._store) > 500:
            now = time.monotonic()
            self._store = {k: v for k, v in self._store.items() if v[0] > now}

    def invalidate(self, path: str = "", query: str = ""):
        if path:
            key = self._make_key(path, query)
            self._store.pop(key, None)
        else:
            self._store.clear()


# Singleton cache instance
cache = ResponseCache(default_ttl=300)
