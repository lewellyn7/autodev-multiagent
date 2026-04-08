"""
Rate Limiting Middleware.
Implements sliding window rate limiting per IP/client.
"""
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import threading

# Thread-safe rate limit storage
_rate_limit_data: dict = defaultdict(list)
_rate_limit_lock = threading.Lock()

# Default rate limits
DEFAULT_LIMIT = 60  # requests per minute
DEFAULT_WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window algorithm.
    Limits: 60 requests/minute per IP for general endpoints.
    """

    def __init__(self, app, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW):
        super().__init__(app)
        self.limit = limit
        self.window = window
        # Special limits for specific paths
        self.path_limits = {
            "/login": 5,  # 5 attempts per window for login
        }
        self.path_windows = {
            "/login": 300,  # 5 minutes window for login
        }

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Determine limit based on path
        path = request.url.path
        limit = self.path_limits.get(path, self.limit)
        window = self.path_windows.get(path, self.window)

        # Check rate limit
        if not self._check_rate_limit(client_ip, path, limit, window):
            return JSONResponse(
                {
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after": window,
                },
                status_code=429,
                headers={"Retry-After": str(window)},
            )

        response = await call_next(request)
        return response

    def _check_rate_limit(self, ip: str, path: str, limit: int, window: int) -> bool:
        """Check if request is within rate limit."""
        now = time.time()

        with _rate_limit_lock:
            # Clean old entries
            if ip in _rate_limit_data:
                _rate_limit_data[ip] = [
                    t for t in _rate_limit_data[ip] if now - t < window
                ]
            else:
                _rate_limit_data[ip] = []

            # Check if limit exceeded
            if len(_rate_limit_data[ip]) >= limit:
                return False

            # Record this request
            _rate_limit_data[ip].append(now)
            return True

    def cleanup_old_entries(self):
        """Periodically clean up old entries (can be called from a background task)."""
        now = time.time()
        with _rate_limit_lock:
            for ip in list(_rate_limit_data.keys()):
                _rate_limit_data[ip] = [
                    t for t in _rate_limit_data[ip] if now - t < self.window
                ]
                if not _rate_limit_data[ip]:
                    del _rate_limit_data[ip]
