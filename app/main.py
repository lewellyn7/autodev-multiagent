import os, json, secrets, time, uuid, httpx, asyncio
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends, Form, Response, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import app.database as db
import g4f

from curl_cffi.requests import AsyncSession
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

db.init_db()
import os
import os
# Absolute path: templates are at /app/app/templates in Docker, ./app/templates locally
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

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
    return templates.TemplateResponse(request=r, name="login.html", context={})

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
        request=r,
        name="admin.html",
        context={
            "pool": db.get_all_pool_status(),
            "models": db.get_models(),
            "expired_models": db.get_expired_models(),
            "keys": db.list_keys(),
            "rateLimit": {"remaining": 60, "limit": 60},
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
        data.append({
            "id": m["name"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": m["source"],
        })
    return {"object": "list", "data": data}

@app.post("/v1/chat/completions", tags=["openai"])
async def chat_completions(req: ChatReq, key_info: dict = Depends(verify_client_key)):
    allowed = key_info["allowed_models"]
    if allowed:
        if req.model not in [x.strip() for x in allowed.split(",") if x.strip()]:
            return JSONResponse({"error": "Model not allowed"}, 403)

    g4f_kwargs = {}
    source_map = {
        "gpt": "chatgpt",
        "o1-": "chatgpt",
        "claude": "claude",
        "gemini": "gemini",
        "deepseek": "deepseek",
        "moonshot": "moonshot",
        "qwen": "qwen",
    }
    target_source = "g4f-free"
    for k, v in source_map.items():
        if k in req.model:
            target_source = v
            break

    pool = db.get_pool_data(target_source)
    if pool:
        if pool.get("cookies"):
            g4f_kwargs["cookies"] = pool["cookies"]
        if target_source in ["deepseek", "moonshot", "openai"]:
            t = pool.get("tokens", {})
            k = t.get("apiKey") or t.get("key") or t.get("token")
            if k:
                g4f_kwargs["api_key"] = k
        elif pool.get("tokens") and pool["tokens"].get("accessToken"):
            g4f_kwargs["access_token"] = pool["tokens"]["accessToken"]

    try:
        response = g4f.ChatCompletion.create(
            model=req.model,
            messages=[{"role": m.role, "content": m.content} for m in req.messages],
            stream=req.stream,
            **g4f_kwargs,
        )
    except Exception as e:
        logger.error(f"G4F error for model {req.model}: {e}")
        return JSONResponse({"error": f"G4F Error: {str(e)}"}, 500)

    if req.stream:
        async def stream_gen():
            try:
                for chunk in response:
                    if chunk:
                        yield f"data: {json.dumps({'id':'chatcmpl-gen','object':'chat.completion.chunk','created':int(time.time()),'model':req.model,'choices':[{'index':0,'delta':{'content':chunk},'finish_reason':None}]})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(stream_gen(), media_type="text/event-stream")
    else:
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response},
                "finish_reason": "stop",
            }],
        }
