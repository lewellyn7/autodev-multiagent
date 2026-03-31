"""
Rate Limiting Middleware for AI Gateway
Implements sliding window rate limiting per API key.
"""

import asyncio
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


# =============================================================================
# In-Memory Rate Limiter (per key)
# =============================================================================
class RateLimiter:
    """
    Sliding window rate limiter.
    Tracks requests per client key within a time window.
    """

    def __init__(self, requests: int = 60, window: int = 60):
        """
        Args:
            requests: Max requests allowed per window
            window: Window size in seconds
        """
        self.requests = requests
        self.window = window
        self._store: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> tuple[bool, dict]:
        """Returns (allowed, info_dict)"""
        now = time.time()
        window_start = now - self.window

        async with self._lock:
            # Clean old entries
            self._store[key] = [t for t in self._store[key] if t > window_start]

            if len(self._store[key]) >= self.requests:
                # Rate limit exceeded
                retry_after = int(self._store[key][0] + self.window - now) + 1
                return False, {
                    "remaining": 0,
                    "reset": int(self._store[key][0] + self.window),
                    "retry_after": max(1, retry_after),
                }

            self._store[key].append(now)
            remaining = self.requests - len(self._store[key])
            reset = int(self._store[key][-1] + self.window)
            return True, {"remaining": remaining, "reset": reset}

    def get_limit(self) -> int:
        return self.requests


# Global limiter instance (60 req/min per key)
_global_limiter = RateLimiter(requests=60, window=60)


# Admin limiter (stricter: 30 req/min for admin endpoints)
_admin_limiter = RateLimiter(requests=30, window=60)


# =============================================================================
# Rate Limit Middleware
# =============================================================================
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces rate limits.
    Skips /health, /login, and /docs endpoints.
    """

    EXEMPT_PATHS = {"/health", "/login", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Exempt certain paths
        if path in self.EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Determine which limiter to use
        is_admin_endpoint = (
            path.startswith("/api/pool") or path.startswith("/api/models") or path.startswith("/api/keys")
        )
        limiter = _admin_limiter if is_admin_endpoint else _global_limiter

        # Extract client identifier
        client_key = self._get_client_key(request)

        allowed, info = await limiter.is_allowed(client_key)

        # Build response headers
        headers = {
            "X-RateLimit-Limit": str(limiter.get_limit()),
            "X-RateLimit-Remaining": str(info["remaining"]),
            "X-RateLimit-Reset": str(info["reset"]),
        }

        if not allowed:
            headers["Retry-After"] = str(info["retry_after"])
            return JSONResponse(
                status_code=429,
                headers=headers,
                content={"error": "Rate limit exceeded", "retry_after": info["retry_after"]},
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response

    def _get_client_key(self, request: Request) -> str:
        """Extract a unique key for the client (API key or IP)."""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]  # Use API key as rate limit key

        # Fallback to IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"


# =============================================================================
# Helper to expose limiter stats (for admin dashboard)
# =============================================================================
def get_rate_limit_stats() -> dict:
    """Returns current rate limit state for monitoring."""
    total_keys = len(_global_limiter._store)
    active_keys = sum(
        1
        for key, times in _global_limiter._store.items()
        if any(t > time.time() - _global_limiter.window for t in times)
    )
    return {
        "global": {
            "limit": _global_limiter.get_limit(),
            "window_seconds": _global_limiter.window,
            "tracked_keys": total_keys,
            "active_keys": active_keys,
        },
        "admin": {
            "limit": _admin_limiter.get_limit(),
            "window_seconds": _admin_limiter.window,
        },
    }
