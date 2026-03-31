import json
import os
import secrets
import time
from datetime import datetime, timedelta

import httpx
import litellm
from curl_cffi.requests import AsyncSession
from fastapi import Body, Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
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

db.init_db()
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


# =============================================================================
# Auth Routes
# =============================================================================
@app.get("/login", response_class=HTMLResponse, tags=["auth"])
async def login_page(r: Request):
    return templates.TemplateResponse("login.html", {"request": r})


@app.post("/login", tags=["auth"])
async def login_do(username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        logger.info(f"Admin login successful for user: {username}")
        resp = JSONResponse({"status": "success"})
        resp.set_cookie("admin_token", SESSION_KEY, httponly=True, samesite="lax")
        return resp
    logger.warning(f"Failed login attempt for user: {username}")
    return JSONResponse({"status": "error", "msg": "Invalid credentials"}, 401)


# =============================================================================
# Admin Dashboard
# =============================================================================
@app.get("/", tags=["admin"])
async def index(r: Request):
    if r.cookies.get("admin_token") != SESSION_KEY:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": r,
            "pool": db.get_all_pool_status(),
            "models": db.get_models(),
            "expired_models": db.get_expired_models(),
            "keys": db.list_keys(),
        },
    )


# =============================================================================
# Pool Management
# =============================================================================
@app.post("/api/pool/sync", tags=["pool"])
async def sync_pool(data: SyncData):
    db.update_pool(data.source, data.cookies, data.tokens)
    logger.info(f"Pool synced for source: {data.source}")
    return {"status": "success", "msg": f"Synced {data.source}"}


@app.delete("/api/pool/{source}", tags=["pool"])
async def delete_pool_item(source: str, _=Depends(api_auth)):
    db.delete_pool_data(source)
    logger.info(f"Pool item deleted: {source}")
    return {"status": "success"}


@app.post("/api/pool/update_token", tags=["pool"])
async def update_pool_token(source: str = Form(...), token: str = Form(...), _=Depends(api_auth)):
    pool = db.get_pool_data(source)
    cookies = pool.get("cookies", {}) if pool else {}
    new_tokens = {}
    if source == "chatgpt":
        new_tokens = {"accessToken": token}
    else:
        new_tokens = {"apiKey": token}
    db.update_pool(source, cookies, new_tokens)
    db.update_pool_status(source, "unknown")
    logger.info(f"Token updated for source: {source}")
    return {"status": "success", "msg": "Updated"}


@app.post("/api/pool/test", tags=["pool"])
async def test_pool_item(source: str = Form(...), _=Depends(api_auth)):
    pool = db.get_pool_data(source)
    if not pool:
        return JSONResponse({"status": "error", "msg": "No data"}, 400)
    cookies = pool.get("cookies", {})
    tokens = pool.get("tokens", {})
    api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")
    access_token = tokens.get("accessToken")
    is_valid = False
    details = ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://google.com",
    }

    try:
        async with AsyncSession(impersonate="chrome120", verify=False, timeout=20) as s:
            if source == "chatgpt":
                if not cookies:
                    is_valid = False
                    details = "Cookies 缺失"
                else:
                    if access_token:
                        headers["Authorization"] = f"Bearer {access_token}"
                    r = await s.get("https://chatgpt.com/backend-api/me", cookies=cookies, headers=headers)
                    if r.status_code == 200:
                        is_valid = True
                        details = "有效 (Web Session)"
                    elif r.status_code == 401:
                        is_valid = False
                        details = "会话已过期 (401)"
                    elif r.status_code == 403:
                        is_valid = False
                        details = "IP 被风控/WAF 强拦截 (403)"
                    else:
                        is_valid = False
                        details = f"HTTP {r.status_code}"

            elif source == "claude":
                if not cookies:
                    is_valid = False
                    details = "Cookies 缺失"
                else:
                    r = await s.get("https://api.claude.ai/api/organizations", cookies=cookies, headers=headers)
                    if r.status_code == 200:
                        is_valid = True
                        details = "有效"
                    else:
                        is_valid = False
                        details = f"HTTP {r.status_code}"

            elif source == "qwen":
                if not cookies:
                    is_valid = False
                    details = "Cookies 缺失"
                else:
                    r = await s.get("https://chat.qwen.ai/", cookies=cookies, headers=headers)
                    if "login" not in str(r.url) and r.status_code == 200:
                        is_valid = True
                        details = "有效"
                    else:
                        is_valid = False
                        details = "会话过期"

            elif source == "deepseek":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get(
                        "https://api.deepseek.com/user/balance",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    if r.status_code == 200:
                        is_valid = True
                        details = "有效"
                    else:
                        is_valid = False
                        details = "Key 无效"

            elif source == "moonshot":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get(
                        "https://api.moonshot.cn/v1/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    if r.status_code == 200:
                        is_valid = True
                        details = "有效"
                    else:
                        is_valid = False
                        details = "Key 无效"

            elif source == "openai":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get(
                        "https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    if r.status_code == 200:
                        is_valid = True
                        details = "有效"
                    else:
                        is_valid = False
                        details = "Key 无效"

            else:
                is_valid = True
                details = "Cookie 存在"

    except httpx.TimeoutException:
        is_valid = False
        details = "连接超时"
        logger.warning(f"Pool test timeout for source: {source}")
    except httpx.HTTPError as e:
        is_valid = False
        details = f"网络错误: {type(e).__name__}"
        logger.error(f"Pool test HTTP error for source {source}: {e}")
    except Exception as e:
        is_valid = False
        details = f"Error: {str(e)}"
        logger.error(f"Pool test unexpected error for source {source}: {e}")

    db.update_pool_status(source, "active" if is_valid else "expired")
    return {"status": "success", "data": {"valid": is_valid, "msg": details}}


# =============================================================================
# OpenAI Subscription & Usage (NEW)
# =============================================================================
@app.get("/api/pool/openai/subscription", tags=["pool"])
async def get_openai_subscription(_=Depends(api_auth)):
    """
    Get OpenAI account subscription info including usage and reset date.
    OpenAI billing period resets on the 1st of each month.
    """
    pool = db.get_pool_data("openai")
    if not pool:
        return JSONResponse({"status": "error", "msg": "OpenAI pool not configured"}, 400)

    tokens = pool.get("tokens", {})
    api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")
    if not api_key:
        return JSONResponse({"status": "error", "msg": "OpenAI API key not found"}, 400)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    try:
        async with AsyncSession(impersonate="chrome120", verify=False, timeout=30) as s:
            # Get subscription info
            sub_r = await s.get("https://api.openai.com/v1/dashboard/billing/subscription", headers=headers)

            if sub_r.status_code != 200:
                return JSONResponse(
                    {"status": "error", "msg": f"API error: {sub_r.status_code}", "detail": sub_r.text}, 400
                )

            sub_data = sub_r.json()

            # Get current usage
            now = datetime.utcnow()
            start_date = now.replace(day=1).strftime("%Y-%m-%d")
            end_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")

            usage_r = await s.get(
                f"https://api.openai.com/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}",
                headers=headers,
            )

            usage_data = usage_r.json() if usage_r.status_code == 200 else {}

            # Calculate totals
            total_usage = usage_data.get("total_usage", 0) / 100  # cents to dollars

            # Subscription info
            plan = sub_data.get("plan", {})
            soft_limit = sub_data.get("hard_limit_usd", 0)
            hard_limit = sub_data.get("hard_limit_usd", 0)
            has_payment_method = sub_data.get("has_payment_method", False)

            # Calculate reset date (1st of next month UTC)
            if now.day >= 1:
                reset_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
            else:
                reset_date = now.replace(day=1)

            return {
                "status": "success",
                "data": {
                    "account_id": sub_data.get("account_id", ""),
                    "plan_id": plan.get("id", ""),
                    "plan_name": plan.get("title", "Unknown"),
                    "is_active": sub_data.get("status", "") == "active",
                    "has_payment_method": has_payment_method,
                    "soft_limit_usd": soft_limit,
                    "hard_limit_usd": hard_limit,
                    "total_usage_usd": round(total_usage, 4),
                    "remaining_usd": round(max(0, soft_limit - total_usage), 4),
                    "usage_percent": round(total_usage / soft_limit * 100, 1) if soft_limit > 0 else 0,
                    "reset_date": reset_date.isoformat() + "Z",
                    "days_until_reset": (reset_date - now).days,
                    "daily_avg": round(total_usage / max(1, now.day), 2),
                },
            }

    except httpx.TimeoutException:
        return JSONResponse({"status": "error", "msg": "请求超时"}, 400)
    except httpx.HTTPError as e:
        logger.error(f"OpenAI subscription error: {e}")
        return JSONResponse({"status": "error", "msg": f"网络错误: {type(e).__name__}"}, 400)
    except Exception as e:
        logger.error(f"Unexpected error in subscription: {e}")
        return JSONResponse({"status": "error", "msg": str(e)}, 400)


@app.get("/api/pool/{source}/stats", tags=["pool"])
async def get_pool_stats(source: str, _=Depends(api_auth)):
    """Get detailed stats for a specific pool source."""
    pool = db.get_pool_data(source)
    if not pool:
        return JSONResponse({"status": "error", "msg": "Pool not found"}, 404)

    # Get usage for OpenAI
    if source == "openai":
        tokens = pool.get("tokens", {})
        api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")
        if api_key:
            headers = {"Authorization": f"Bearer {api_key}"}
            try:
                async with AsyncSession(impersonate="chrome120", verify=False, timeout=15) as s:
                    # Model usage breakdown
                    models_r = await s.get("https://api.openai.com/v1/models", headers=headers)
                    model_list = []
                    if models_r.status_code == 200:
                        for m in models_r.json().get("data", []):
                            model_list.append(
                                {"id": m["id"], "created": m.get("created", 0), "owned_by": m.get("owned_by", "")}
                            )

                    return {
                        "status": "success",
                        "data": {
                            "source": source,
                            "status": pool.get("status", "unknown"),
                            "cookie_count": len(pool.get("cookies", {})),
                            "has_api_key": bool(api_key),
                            "models_count": len(model_list),
                        },
                    }
            except:
                pass

    return {
        "status": "success",
        "data": {
            "source": source,
            "status": pool.get("status", "unknown"),
            "cookie_count": len(pool.get("cookies", {})),
        },
    }


# =============================================================================
# Polling Strategy API - Multi-account轮询
# =============================================================================
@app.get("/api/pool/{source}/account", tags=["pool"])
async def get_polling_account(source: str, strategy: str = "round_robin", _=Depends(api_auth)):
    """Get next available account based on polling strategy.

    Strategies:
    - round_robin: Cyclic rotation (default)
    - random: Random selection
    - weighted: By success rate
    - circuit_breaker: Skip failing accounts
    """
    account = db.get_pool_by_strategy(source, strategy)
    if not account:
        return JSONResponse({"status": "error", "msg": f"No active account for {source}"}, 404)
    return {
        "status": "success",
        "data": {
            "id": account["id"],
            "source": account["source"],
            "account_index": account["account_index"],
            "cookies": account["cookies"],
            "tokens": account["tokens"],
            "strategy_used": strategy,
        },
    }


@app.post("/api/pool/{source}/account/{account_id}/report", tags=["pool"])
async def report_account_result(
    source: str, account_id: int, success: bool = Form(...), latency: float = Form(None), _=Depends(api_auth)
):
    """Report request result for an account (for stats tracking)."""
    db.update_account_stats(int(account_id), success, latency)
    return {"status": "success"}


@app.get("/api/pool/{source}/health", tags=["pool"])
async def get_pool_health(source: str, _=Depends(api_auth)):
    """Get health summary for a source pool."""
    health = db.get_account_health(source)
    return {"status": "success", "data": health}


@app.post("/api/pool/{source}/account/add", tags=["pool"])
async def add_pool_account(
    source: str,
    account_index: int = Form(...),
    cookies: str = Form("{}"),
    tokens: str = Form("{}"),
    _=Depends(api_auth),
):
    """Add a proxy account to the pool."""
    import json

    try:
        cookies_dict = json.loads(cookies)
        tokens_dict = json.loads(tokens)
    except:
        return JSONResponse({"status": "error", "msg": "Invalid JSON for cookies/tokens"}, 400)
    db.add_proxy_account(source, account_index, cookies_dict, tokens_dict)
    logger.info(f"Proxy account added: {source}[{account_index}]")
    return {"status": "success"}


@app.delete("/api/pool/{source}/account/{account_id}", tags=["pool"])
async def delete_pool_account(source: str, account_id: int, _=Depends(api_auth)):
    """Delete a proxy account."""
    db.delete_proxy_account(account_id)
    return {"status": "success"}


# =============================================================================
# Health Score API - Multi-dimensional health evaluation
# =============================================================================


@app.get("/api/pool/{source}/score", tags=["pool"])
async def get_pool_score(source: str, max_latency: float = 5000, _=Depends(api_auth)):
    """
    Get health scores for all accounts in a pool.
    Returns detailed health metrics for each account.
    """
    try:
        health_scores = db.get_account_health_batch(source, max_latency)
        return {"status": "success", "data": {"source": source, "health_scores": health_scores}}
    except Exception as e:
        logger.error(f"Error getting pool scores: {e}")
        return {"status": "error", "msg": str(e)}


@app.get("/api/pool/{source}/best", tags=["pool"])
async def get_best_pool_account(source: str, strategy: str = "health_score", _=Depends(api_auth)):
    """
    Get the best available account for a source based on health score.
    Strategies:
    - health_score: Select by highest health score (default)
    - priority: Select by priority weight
    - round_robin: Traditional round-robin selection
    """
    try:
        account = db.get_best_account(source, strategy)
        if not account:
            return JSONResponse({"status": "error", "msg": f"No active account for {source}"}, 404)

        # Calculate health score for the best account
        health = db.calculate_account_health(account["id"])

        return {
            "status": "success",
            "data": {
                "account": {
                    "id": account["id"],
                    "source": account["source"],
                    "account_index": account["account_index"],
                    "status": account["status"],
                },
                "health_score": health["score"] if health else None,
                "strategy_used": strategy,
            },
        }
    except Exception as e:
        logger.error(f"Error getting best account: {e}")
        return {"status": "error", "msg": str(e)}


@app.post("/api/pool/{source}/account/{account_id}/concurrent", tags=["pool"])
async def update_account_concurrent(source: str, account_id: int, delta: int = Form(...), _=Depends(api_auth)):
    """
    Update concurrent request count for an account.
    Use delta: +1 to increment, -1 to decrement.
    """
    try:
        db.increment_concurrent(account_id, delta)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating concurrent count: {e}")
        return {"status": "error", "msg": str(e)}


@app.put("/api/pool/{source}/account/{account_id}/config", tags=["pool"])
async def update_account_config(
    source: str, account_id: int, max_concurrent: int = Body(None), priority: int = Body(None), _=Depends(api_auth)
):
    """
    Update account configuration.
    - max_concurrent: Maximum concurrent requests allowed
    - priority: Priority weight for selection
    """
    try:
        if max_concurrent is not None:
            db.update_account_concurrent_limit(account_id, max_concurrent)
        if priority is not None:
            db.update_account_priority(account_id, priority)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating account config: {e}")
        return {"status": "error", "msg": str(e)}


# =============================================================================
# Model Management
# =============================================================================
@app.post("/api/models", tags=["models"])
async def add_model(name: str = Form(...), source: str = Form(...), _=Depends(api_auth)):
    db.add_model(name, source)
    logger.info(f"Model added: {name} ({source})")
    return {"status": "ok"}


@app.delete("/api/models/{id}", tags=["models"])
async def del_model(id: int, _=Depends(api_auth)):
    model = db.get_model_by_id(id)
    if model:
        db.add_expired_model(model["name"], model["source"])
        db.del_model(id)
        logger.info(f"Model deleted (moved to expired): {model['name']}")
    return {"status": "ok"}


@app.delete("/api/models/expired/{id}", tags=["models"])
async def del_expired_model(id: int, _=Depends(api_auth)):
    db.del_expired_model(id)
    logger.info(f"Expired model removed: id={id}")
    return {"status": "ok"}


@app.post("/api/models/fetch", tags=["models"])
async def fetch_models_api(source: str = Form(...), api_key: str = Form(None), _=Depends(api_auth)):
    models_found = []
    token = api_key
    if not token:
        pool = db.get_pool_data(source)
        if pool and pool.get("tokens"):
            t = pool["tokens"]
            token = t.get("apiKey") or t.get("key") or t.get("token") or t.get("accessToken")
    try:
        async with AsyncSession(impersonate="chrome120", verify=False) as s:
            if source == "chatgpt":
                pool = db.get_pool_data("chatgpt")
                cookies = pool.get("cookies", {}) if pool else {}
                if not cookies:
                    raise Exception("缺 Cookies")
                headers = {"Authorization": f"Bearer {token}", "User-Agent": "Mozilla/5.0"}
                r = await s.get("https://chatgpt.com/backend-api/models", cookies=cookies, headers=headers)
                if r.status_code == 200:
                    for m in r.json().get("models", []):
                        models_found.append((m["slug"], "chatgpt"))
                else:
                    raise Exception(f"HTTP {r.status_code}")

            elif source == "qwen":
                models_found = [("qwen-max", "qwen"), ("qwen-plus", "qwen")]

            elif source == "deepseek":
                if not token:
                    models_found = [("deepseek-chat", "deepseek")]
                else:
                    r = await s.get(
                        "https://api.deepseek.com/models",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code == 200:
                        for m in r.json().get("data", []):
                            models_found.append((m["id"], "deepseek"))

            elif source == "moonshot":
                if not token:
                    models_found = [("moonshot-v1-8k", "moonshot")]
                else:
                    r = await s.get(
                        "https://api.moonshot.cn/v1/models",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code == 200:
                        for m in r.json().get("data", []):
                            models_found.append((m["id"], "moonshot"))

            elif source == "openai":
                if not token:
                    models_found = [("gpt-4o", "openai")]
                else:
                    r = await s.get(
                        "https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code == 200:
                        for m in r.json().get("data", []):
                            if "gpt" in m["id"] or "o1" in m["id"]:
                                models_found.append((m["id"], "openai"))

            elif source == "claude":
                models_found = [("claude-3-5-sonnet-20240620", "claude")]

            elif source == "gemini":
                models_found = [("gemini-1.5-pro", "gemini")]

    except httpx.TimeoutException:
        return JSONResponse({"status": "error", "msg": "获取模型列表超时"}, 400)
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch models for {source}: {e}")
        return JSONResponse({"status": "error", "msg": f"网络错误: {type(e).__name__}"}, 400)
    except Exception as e:
        logger.error(f"Model fetch error for {source}: {e}")
        return JSONResponse({"status": "error", "msg": str(e)}, 400)

    if models_found:
        expired_set = db.get_all_expired_set()
        valid = [m for m in models_found if m not in expired_set]
        if valid:
            db.bulk_add_models(valid)
            logger.info(f"Fetched and added {len(valid)} models for {source}")
            return {"status": "success", "msg": f"更新 {len(valid)} 个模型"}
    return {"status": "error", "msg": "未找到模型"}


# =============================================================================
# API Key Management
# =============================================================================
@app.post("/api/keys", tags=["keys"])
async def add_key(name: str = Form(...), models: str = Form(""), _=Depends(api_auth)):
    k = f"sk-{secrets.token_hex(16)}"
    db.add_key(k, name, models)
    logger.info(f"API key created: {name} (models: {models or 'all'})")
    return {"status": "ok", "key": k}


@app.put("/api/keys/{key}", tags=["keys"])
async def upd_key(key: str, name: str = Body(...), models: str = Body(""), _=Depends(api_auth)):
    db.update_key(key, name, models)
    logger.info(f"API key updated: {key[:12]}...")
    return {"status": "ok"}


@app.delete("/api/keys/{key}", tags=["keys"])
async def del_key(key: str, _=Depends(api_auth)):
    db.del_key(key)
    logger.info(f"API key deleted: {key[:12]}...")
    return {"status": "ok"}


# =============================================================================
# OpenAI Compatible API
# =============================================================================
@app.get("/v1/models", tags=["openai"])
async def list_models(request: Request):
    models = db.get_models()
    data = []
    for m in models:
        data.append(
            {
                "id": m["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": m["source"],
            }
        )
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions", tags=["openai"])
async def chat_completions(req: ChatReq, key_info: dict = Depends(verify_client_key)):
    """OpenAI-compatible chat completions endpoint using LiteLLM"""
    allowed = key_info["allowed_models"]
    if allowed:
        if req.model not in [x.strip() for x in allowed.split(",") if x.strip()]:
            return JSONResponse({"error": "Model not allowed"}, 403)

    # Map model to provider and get API key
    source_map = {
        "gpt": "chatgpt",
        "o1-": "chatgpt",
        "claude": "claude",
        "gemini": "gemini",
        "deepseek": "deepseek",
        "moonshot": "moonshot",
        "qwen": "qwen",
    }
    target_source = "chatgpt"
    for k, v in source_map.items():
        if k in req.model:
            target_source = v
            break

    pool = db.get_pool_data(target_source)
    api_key = None
    if pool:
        t = pool.get("tokens", {})
        api_key = t.get("apiKey") or t.get("key") or t.get("token")

    try:
        response = await litellm.acompletion(
            model=req.model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            stream=req.stream,
            timeout=60,
            api_key=api_key,
        )
    except Exception as e:
        logger.error(f"LiteLLM error for model {req.model}: {e}")
        return JSONResponse({"error": f"LiteLLM Error: {str(e)}"}, 500)

    if req.stream:

        async def stream_gen():
            try:
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        yield f"data: {json.dumps({'id': chunk.id, 'object': 'chat.completion.chunk', 'created': int(time.time()), 'model': req.model, 'choices': [{'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    else:
        return {
            "id": response.id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response.choices[0].message.content},
                    "finish_reason": response.choices[0].finish_reason,
                }
            ],
        }


@app.get("/api/audit/logs", tags=["audit"])
async def get_audit_logs(
    request: Request,
    action: str = None,
    user_id: str = None,
    method: str = None,
    path: str = None,
    status: int = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 100,
    offset: int = 0,
    _: dict = Depends(api_auth),
):
    """
    Get audit logs with optional filters.

    Query Parameters:
    - action: Filter by action type (e.g., "API_CALL", "ADMIN_ACTION")
    - user_id: Filter by user ID
    - method: Filter by HTTP method (GET, POST, etc.)
    - path: Filter by path (substring match)
    - status: Filter by response status code
    - start_date: Start timestamp (ISO format)
    - end_date: End timestamp (ISO format)
    - limit: Maximum records to return (default: 100)
    - offset: Offset for pagination (default: 0)
    """
    try:
        # Build filters dict
        filters = {}
        if action:
            filters["action"] = action
        if user_id:
            filters["user_id"] = user_id
        if method:
            filters["method"] = method
        if path:
            filters["path"] = path
        if status:
            filters["status"] = status
        if start_date:
            filters["start_date"] = start_date
        if end_date:
            filters["end_date"] = end_date

        # Get logs from database
        logs = db.get_audit_logs(filters=filters if filters else None, limit=limit, offset=offset)

        return {"status": "success", "data": logs, "pagination": {"limit": limit, "offset": offset, "total": len(logs)}}
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        raise HTTPException(500, f"Failed to fetch audit logs: {str(e)}")


@app.get("/api/audit/stats", tags=["audit"])
async def get_audit_stats(request: Request, start_date: str = None, end_date: str = None, _: dict = Depends(api_auth)):
    """
    Get audit log statistics.

    Query Parameters:
    - start_date: Start timestamp (ISO format)
    - end_date: End timestamp (ISO format)

    Returns:
    - total_requests: Total number of requests
    - by_action: Breakdown by action type
    - by_method: Breakdown by HTTP method
    - avg_latency_ms: Average response latency
    - min_latency_ms: Minimum response latency
    - max_latency_ms: Maximum response latency
    - error_count: Number of error responses (4xx/5xx)
    - error_rate: Percentage of error responses
    """
    try:
        stats = db.get_audit_stats(start_date=start_date, end_date=end_date)
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error(f"Error fetching audit stats: {e}")
        raise HTTPException(500, f"Failed to fetch audit stats: {str(e)}")


@app.post("/api/audit/cleanup", tags=["audit"])
async def cleanup_audit_logs(days_to_keep: int = Form(30), _: dict = Depends(api_auth)):
    """
    Clean up old audit logs.

    Form Parameters:
    - days_to_keep: Number of days to retain logs (default: 30)
    """
    try:
        deleted = db.cleanup_old_logs(days_to_keep)
        logger.info(f"Cleaned up {deleted} old audit logs")
        return {"status": "success", "msg": f"Deleted {deleted} old audit log entries"}
    except Exception as e:
        logger.error(f"Error cleaning up audit logs: {e}")
        raise HTTPException(500, f"Failed to cleanup audit logs: {str(e)}")


# =============================================================================
# Protocol Conversion Layer - OpenAI / Claude / Gemini 互转
# =============================================================================

# Model fallback chains (按优先级尝试)
MODEL_FALLBACK_CHAIN = {
    "gpt-4o": ["gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    "gpt-4o-mini": ["gpt-3.5-turbo", "claude-3-sonnet-20240229"],
    "claude-3-opus": ["claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
    "claude-3-sonnet": ["claude-3-haiku-20240307", "gpt-4o-mini"],
    "gemini-1.5-pro": ["gemini-1.5-flash", "gemini-pro"],
    "gemini-1.5-flash": ["gemini-pro"],
}

# Provider fallback chains
PROVIDER_FALLBACK_CHAIN = {
    "chatgpt": ["deepseek", "moonshot", "openai"],
    "claude": ["chatgpt", "deepseek"],
    "gemini": ["chatgpt", "deepseek"],
    "deepseek": ["moonshot", "openai"],
    "moonshot": ["openai", "deepseek"],
    "openai": ["chatgpt", "deepseek"],
    "qwen": ["deepseek", "chatgpt"],
}


def convert_claude_to_openai(messages: list) -> list:
    """Convert Claude message format to OpenAI format."""
    openai_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        if role == "assistant":
            role = "assistant"
        elif role == "user":
            role = "user"
        elif role == "system":
            role = "system"
        content = msg.get("content", "")
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
        else:
            # Handle Claude content blocks
            text_content = ""
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_content += block.get("text", "")
            else:
                text_content = str(content)
            openai_messages.append({"role": role, "content": text_content})
    return openai_messages


def convert_gemini_to_openai(messages: list) -> list:
    """Convert Gemini message format to OpenAI format."""
    openai_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        # Gemini uses "model" for assistant, normalize to "assistant"
        if role == "model":
            role = "assistant"
        content = msg.get("parts", [{}])
        if isinstance(content, list):
            text = "".join([p.get("text", "") for p in content if isinstance(p, dict)])
        else:
            text = str(content)
        openai_messages.append({"role": role, "content": text})
    return openai_messages


def convert_openai_to_claude(messages: list) -> list:
    """Convert OpenAI message format to Claude format."""
    claude_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            claude_messages.append({"role": role, "content": content})
        else:
            text_content = ""
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_content += block.get("text", "")
                        elif block.get("type") == "image_url":
                            text_content += "[image] "
            claude_messages.append({"role": role, "content": text_content})
    return claude_messages


def get_fallback_models(model: str) -> list:
    """Get fallback models for a given model."""
    return MODEL_FALLBACK_CHAIN.get(model, [])


def get_fallback_providers(source: str) -> list:
    """Get fallback providers for a given source."""
    return PROVIDER_FALLBACK_CHAIN.get(source, [])


def build_openai_error_response(message: str, error_type: str = "invalid_request", code: str = None) -> dict:
    """Build OpenAI compatible error response."""
    return {"error": {"message": message, "type": error_type, "code": code, "param": None, "status": 400}}


class StreamingKeepAlive:
    """Send keep-alive comments during streaming to prevent connection timeout."""

    def __init__(self, interval_ms: int = 15000):
        self.interval = interval_ms / 1000.0
        self.enabled = True

    def __iter__(self):
        import time

        last_yield = time.time()
        while self.enabled:
            current_time = time.time()
            if current_time - last_yield >= self.interval:
                yield f": keepalive_{int(current_time)}\n\n"
                last_yield = current_time
            time.sleep(0.1)

    def stop(self):
        self.enabled = False


# =============================================================================
# GitHub OAuth Handler
# =============================================================================

import base64

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/oauth/github/callback")


def generate_oauth_state() -> str:
    """Generate a secure random state for OAuth."""
    return secrets.token_urlsafe(32)


def encode_oauth_state(state: str) -> str:
    """Encode state with session key for security."""
    # Simple encoding: state:timestamp:hmac
    timestamp = str(int(time.time()))
    import hashlib

    signature = hashlib.sha256(f"{state}{SESSION_KEY}{timestamp}".encode()).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{state}:{timestamp}:{signature}".encode()).decode()


def decode_oauth_state(encoded: str) -> bool:
    """Decode and verify OAuth state."""
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
        state, timestamp, signature = decoded.split(":")
        import hashlib

        expected_sig = hashlib.sha256(f"{state}{SESSION_KEY}{timestamp}".encode()).hexdigest()[:16]
        if signature != expected_sig:
            return False
        # Check timestamp (5 minutes validity)
        if time.time() - int(timestamp) > 300:
            return False
        return True
    except:
        return False


@app.get("/oauth/github", tags=["oauth"])
async def oauth_github(request: Request):
    """
    Redirect to GitHub OAuth authorization page.
    Scopes: user:email (to get user's email address)
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(500, "GitHub OAuth not configured")

    state = generate_oauth_state()
    encoded_state = encode_oauth_state(state)

    # Store state in cookie for validation
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": "user:email",
        "state": encoded_state,
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    redirect_url = f"https://github.com/login/oauth/authorize?{query}"

    response = RedirectResponse(redirect_url)
    response.set_cookie("oauth_state", encoded_state, max_age=300, httponly=True, samesite="lax")
    return response


@app.get("/oauth/github/callback", tags=["oauth"])
async def oauth_github_callback(request: Request, code: str = None, state: str = None):
    """
    GitHub OAuth callback handler.
    Exchanges code for access token and stores account info.
    """
    if not code:
        raise HTTPException(400, "Authorization code required")

    if not state:
        raise HTTPException(400, "State parameter required")

    # Validate state
    # Note: In production, also validate against cookie-stored state
    # For simplicity, we skip strict state validation here

    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(500, "GitHub OAuth not configured")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
        )

        if token_response.status_code != 200:
            logger.error(f"GitHub token exchange failed: {token_response.text}")
            raise HTTPException(400, "Failed to exchange code for token")

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        expires_at = int(time.time() + expires_in) if expires_in else None

        if not access_token:
            raise HTTPException(400, "No access token received")

        # Get user info from GitHub API
        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        )

        if user_response.status_code != 200:
            logger.error(f"GitHub user info failed: {user_response.text}")
            raise HTTPException(400, "Failed to get user info")

        user_data = user_response.json()
        provider_user_id = str(user_data.get("id"))
        email = user_data.get("email")

        # If no email in user data, try to get from emails endpoint
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                for e in emails:
                    if e.get("primary"):
                        email = e.get("email")
                        break

        # Store OAuth account in database
        db.add_oauth_account(
            provider="github",
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            email=email,
        )

        logger.info(f"GitHub OAuth successful for user: {email} (ID: {provider_user_id})")

    # Redirect to admin dashboard or show success page
    # For now, redirect to admin dashboard
    return RedirectResponse("/", 302)


@app.get("/api/oauth/accounts", tags=["oauth"])
async def get_oauth_accounts(request: Request, _=Depends(api_auth)):
    """
    Get list of all bound OAuth accounts.
    Requires admin authentication.
    """
    accounts = db.get_all_oauth_accounts()
    return {"status": "success", "data": accounts}


@app.delete("/api/oauth/accounts/{provider}", tags=["oauth"])
async def delete_oauth_account(provider: str, request: Request, _=Depends(api_auth)):
    """
    Unbind OAuth account by provider.
    Requires admin authentication.
    """
    # Delete all accounts for the provider
    db.delete_oauth_account_by_provider(provider)
    logger.info(f"OAuth account unbound: {provider}")
    return {"status": "success", "msg": f"Unbound {provider}"}


async def refresh_github_token(provider_user_id: str, current_token: str) -> str:
    """
    Refresh GitHub access token if expired.
    Returns valid access token.

    Note: GitHub OAuth tokens don't expire by default unless using
    expiring tokens feature. This is a placeholder for when needed.
    """
    # GitHub tokens don't typically expire unless using expiring tokens
    # Return current token as-is
    return current_token
