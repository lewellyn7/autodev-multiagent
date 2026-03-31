"""
Model Management Routes - /api/models/*
"""

import httpx
from curl_cffi.requests import AsyncSession
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse

import app.database as db

router = APIRouter(prefix="/api/models", tags=["models"])


# =============================================================================
# Dependencies
# =============================================================================
async def api_auth(request: Request):
    """Admin authentication dependency."""
    from app.main import SESSION_KEY

    token = request.cookies.get("admin_token")
    if token != SESSION_KEY:
        raise HTTPException(401, "Unauthorized")


# =============================================================================
# Model Management
# =============================================================================
@router.post("")
async def add_model(name: str = Form(...), source: str = Form(...), _=Depends(api_auth)):
    """Add a model."""
    db.add_model(name, source)
    return {"status": "ok"}


@router.delete("/{id}")
async def del_model(id: int, _=Depends(api_auth)):
    """Delete a model (move to expired)."""
    model = db.get_model_by_id(id)
    if model:
        db.add_expired_model(model["name"], model["source"])
        db.del_model(id)
    return {"status": "ok"}


@router.delete("/expired/{id}")
async def del_expired_model(id: int, _=Depends(api_auth)):
    """Delete an expired model permanently."""
    db.del_expired_model(id)
    return {"status": "ok"}


@router.post("/fetch")
async def fetch_models_api(source: str = Form(...), api_key: str = Form(None), _=Depends(api_auth)):
    """Fetch available models from a provider."""
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

            elif source == "qwen":
                models_found = [("qwen-max", "qwen"), ("qwen-plus", "qwen")]

            elif source == "deepseek":
                if not token:
                    models_found = [("deepseek-chat", "deepseek")]
                else:
                    r = await s.get("https://api.deepseek.com/models", headers={"Authorization": f"Bearer {token}"})
                    if r.status_code == 200:
                        for m in r.json().get("data", []):
                            models_found.append((m["id"], "deepseek"))

            elif source == "moonshot":
                if not token:
                    models_found = [("moonshot-v1-8k", "moonshot")]
                else:
                    r = await s.get("https://api.moonshot.cn/v1/models", headers={"Authorization": f"Bearer {token}"})
                    if r.status_code == 200:
                        for m in r.json().get("data", []):
                            models_found.append((m["id"], "moonshot"))

            elif source == "openai":
                if not token:
                    models_found = [("gpt-4o", "openai")]
                else:
                    r = await s.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {token}"})
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
    except httpx.HTTPError:
        return JSONResponse({"status": "error", "msg": "网络错误"}, 400)
    except Exception as e:
        return JSONResponse({"status": "error", "msg": str(e)}, 400)

    if models_found:
        expired_set = db.get_all_expired_set()
        valid = [m for m in models_found if m not in expired_set]
        if valid:
            db.bulk_add_models(valid)
            return {"status": "success", "msg": f"更新 {len(valid)} 个模型"}

    return JSONResponse({"status": "error", "msg": "未找到模型"}, 400)
