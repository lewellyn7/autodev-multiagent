import os
import secrets
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import app.database as db
from app.middleware import RateLimitMiddleware

# =============================================================================
# App Configuration (Externalized)
# =============================================================================
APP_CONFIG = {
    "admin_user": os.getenv("ADMIN_USER", "admin"),
    "admin_pass": os.getenv("ADMIN_PASSWORD", "password"),
    "session_key": secrets.token_hex(16),
    "debug": os.getenv("DEBUG", "false").lower() == "true",
}
ADMIN_USER = APP_CONFIG["admin_user"]
ADMIN_PASS = APP_CONFIG["admin_pass"]
SESSION_KEY = APP_CONFIG["session_key"]
DEBUG = APP_CONFIG["debug"]

# =============================================================================
# Structured Logging
# =============================================================================
import logging

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ai-gateway")


# =============================================================================
# Models
# =============================================================================
class SyncData(BaseModel):
    source: str
    cookies: dict
    tokens: dict


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    model: str
    messages: list[ChatMsg]
    stream: bool = False


# =============================================================================
# App
# =============================================================================
app = FastAPI(
    title="AI Gateway",
    version="1.0.0",
    debug=DEBUG,
    description="""
## 🦞 AI Gateway - Multi-LLM Proxy API

A unified API gateway that aggregates multiple LLM providers (ChatGPT, Claude, DeepSeek, Moonshot, Qwen, etc.)
behind a single OpenAI-compatible interface.

### Features
- **OpenAI Compatible** - Use existing OpenAI clients with minimal changes
- **Multi-Provider** - Seamlessly route requests across ChatGPT, Claude, Gemini, DeepSeek, and more
- **WAF Bypass** - Advanced fingerprint spoofing for strict cloud services
- **Rate Limiting** - Per-key rate limits with sliding window
- **Admin Dashboard** - Web UI for managing pools, models, and API keys
- **Docker Ready** - Multi-stage build for minimal image size

### Rate Limits
- **Global**: 60 requests/minute per API key
- **Admin**: 30 requests/minute per session

### Authentication
- **Client**: Bearer token in `Authorization` header
- **Admin**: Session cookie after login at `/login`
""",
    openapi_tags=[
        {"name": "health", "description": "Health check endpoints"},
        {"name": "auth", "description": "Admin authentication"},
        {"name": "admin", "description": "Admin dashboard"},
        {"name": "pool", "description": "Proxy pool management"},
        {"name": "models", "description": "Model registry management"},
        {"name": "keys", "description": "API key management"},
        {"name": "openai", "description": "OpenAI-compatible API endpoints"},
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    docs_theme="universe",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Rate limiting: 60 req/min global, 30 req/min for admin endpoints
app.add_middleware(RateLimitMiddleware)

# Add audit middleware for request logging
# =============================================================================
# Audit Logging Middleware
# =============================================================================
import time as time_module


class AuditMiddleware:
    """Middleware to log all API requests for audit purposes."""

    SENSITIVE_FIELDS = [
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "auth",
        "authorization",
        "credential",
        "private_key",
        "secret_key",
        "secretkey",
        "key",
    ]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        start_time = time_module.time()
        method = scope["method"]
        path = scope["path"]

        client = scope.get("client", ("unknown", 0))
        ip_address = client[0] if client else "unknown"

        headers = dict(scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode()
        user_id = "anonymous"
        if auth_header.startswith("Bearer "):
            user_id = auth_header[7:]
        elif not auth_header:
            cookie_header = headers.get(b"cookie", b"").decode()
            if "admin_token" in cookie_header:
                user_id = "admin"

        if "/api/" in path or "/v1/" in path:
            action = "API_CALL"
        elif path in ["/", "/login", "/admin"]:
            action = "PAGE_VIEW"
        else:
            action = "UNKNOWN"

        request_body = None
        content_length = int(headers.get(b"content-length", 0))
        if scope["method"] in ["POST", "PUT", "PATCH"] and content_length > 0:
            request_body = f"[Body: {content_length} bytes]"

        response_status = None

        async def send_wrapper(message):
            nonlocal start_time, response_status

            if message["type"] == "http.response.start":
                response_status = message["status"]
                latency_ms = int((time_module.time() - start_time) * 1000)

                try:
                    db.log_request(
                        action=action,
                        user_id=user_id,
                        ip=ip_address,
                        method=method,
                        path=path,
                        body=request_body,
                        status=response_status,
                        latency=latency_ms,
                    )
                except Exception as e:
                    logger.error(f"Audit logging failed: {e}")

                if path not in ["/health", "/"]:
                    logger.info(f"AUDIT: {action} {method} {path} {response_status} {latency_ms}ms")

            await send(message)

        return await self.app(scope, receive, send_wrapper)


def sanitize_request_body(body: dict) -> dict:
    """Sanitize sensitive information from request body."""
    if not body:
        return body

    sanitized = {}
    for key, value in body.items():
        key_lower = key.lower()
        is_sensitive = any(sensitive in key_lower for sensitive in AuditMiddleware.SENSITIVE_FIELDS)

        if is_sensitive:
            if isinstance(value, str):
                sanitized[key] = value[:2] + "***" if len(value) > 2 else "***"
            else:
                sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value

    return sanitized


app.add_middleware(AuditMiddleware)


# =============================================================================
# API Routers
# =============================================================================
from app.routes.admin import router as admin_router
from app.routes.audit import router as audit_router
from app.routes.chat import router as chat_router
from app.routes.keys import router as keys_router
from app.routes.models import router as models_router
from app.routes.oauth import router as oauth_router
from app.routes.pool import router as pool_router

db.init_db()

# =============================================================================
# Include API Routers
# =============================================================================
app.include_router(admin_router)
app.include_router(audit_router)
app.include_router(chat_router)
app.include_router(keys_router)
app.include_router(models_router)
app.include_router(oauth_router)
app.include_router(pool_router)

templates = Jinja2Templates(directory="app/templates")


# =============================================================================
# Dependencies
# =============================================================================
async def api_auth(request: Request):
    token = request.cookies.get("admin_token")
    if token != SESSION_KEY:
        logger.warning(f"Unauthorized admin access attempt from {request.client.host}")
        raise HTTPException(401, "Unauthorized")


async def verify_client_key(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Key")
    key_info = db.get_key_info(auth.split(" ")[1])
    if not key_info:
        raise HTTPException(401, "Invalid Key")
    return key_info


# =============================================================================
# Health Check Endpoint
# =============================================================================
@app.get("/health", tags=["health"])
async def health_check():
    """Kubernetes / Docker health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": time.time(),
    }


#
