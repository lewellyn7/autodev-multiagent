"""
Pool Management Routes - /api/pool/*
"""

from datetime import datetime, timedelta

import httpx
from curl_cffi.requests import AsyncSession
from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse

import app.database as db

router = APIRouter(prefix="/api/pool", tags=["pool"])


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
# Pool Sync & Management
# =============================================================================
@router.post("/sync")
async def sync_pool(data: dict):
    """Sync pool data from source."""
    source = data.get("source")
    cookies = data.get("cookies", {})
    tokens = data.get("tokens", {})
    db.update_pool(source, cookies, tokens)
    return {"status": "success", "msg": f"Synced {source}"}


@router.delete("/{source}")
async def delete_pool_item(source: str, _=Depends(api_auth)):
    """Delete pool data for a source."""
    db.delete_pool_data(source)
    return {"status": "success"}


@router.post("/update_token")
async def update_pool_token(source: str = Form(...), token: str = Form(...), _=Depends(api_auth)):
    """Update token for a pool source."""
    pool = db.get_pool_data(source)
    cookies = pool.get("cookies", {}) if pool else {}
    new_tokens = {"apiKey": token} if source != "chatgpt" else {"accessToken": token}
    db.update_pool(source, cookies, new_tokens)
    db.update_pool_status(source, "unknown")
    return {"status": "success", "msg": "Updated"}


@router.post("/test")
async def test_pool_item(source: str = Form(...), _=Depends(api_auth)):
    """Test pool credentials validity."""
    pool = db.get_pool_data(source)
    if not pool:
        return JSONResponse({"status": "error", "msg": "No data"}, 400)

    cookies = pool.get("cookies", {})
    tokens = pool.get("tokens", {})
    api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")
    access_token = tokens.get("accessToken")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://google.com",
    }

    is_valid = False
    details = ""

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
                    is_valid = r.status_code == 200
                    details = "有效" if is_valid else f"HTTP {r.status_code}"

            elif source == "qwen":
                if not cookies:
                    is_valid = False
                    details = "Cookies 缺失"
                else:
                    r = await s.get("https://chat.qwen.ai/", cookies=cookies, headers=headers)
                    is_valid = "login" not in str(r.url) and r.status_code == 200
                    details = "有效" if is_valid else "会话过期"

            elif source == "deepseek":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get(
                        "https://api.deepseek.com/user/balance", headers={"Authorization": f"Bearer {api_key}"}
                    )
                    is_valid = r.status_code == 200
                    details = "有效" if is_valid else "Key 无效"

            elif source == "moonshot":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get("https://api.moonshot.cn/v1/models", headers={"Authorization": f"Bearer {api_key}"})
                    is_valid = r.status_code == 200
                    details = "有效" if is_valid else "Key 无效"

            elif source == "openai":
                if not api_key:
                    is_valid = False
                    details = "Key 缺"
                else:
                    r = await s.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"})
                    is_valid = r.status_code == 200
                    details = "有效" if is_valid else "Key 无效"

            else:
                is_valid = True
                details = "Cookie 存在"

    except httpx.TimeoutException:
        is_valid = False
        details = "连接超时"
    except httpx.HTTPError:
        is_valid = False
        details = "网络错误"
    except Exception:
        is_valid = False
        details = "未知错误"

    db.update_pool_status(source, "active" if is_valid else "expired")
    return {"status": "success", "data": {"valid": is_valid, "msg": details}}


# =============================================================================
# OpenAI Subscription
# =============================================================================
@router.get("/openai/subscription")
async def get_openai_subscription(_=Depends(api_auth)):
    """Get OpenAI account subscription info."""
    pool = db.get_pool_data("openai")
    if not pool:
        return JSONResponse({"status": "error", "msg": "OpenAI pool not configured"}, 400)

    tokens = pool.get("tokens", {})
    api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")
    if not api_key:
        return JSONResponse({"status": "error", "msg": "OpenAI API key not found"}, 400)

    headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0"}

    try:
        async with AsyncSession(impersonate="chrome120", verify=False, timeout=30) as s:
            sub_r = await s.get("https://api.openai.com/v1/dashboard/billing/subscription", headers=headers)
            if sub_r.status_code != 200:
                return JSONResponse({"status": "error", "msg": f"API error: {sub_r.status_code}"}, 400)

            sub_data = sub_r.json()
            now = datetime.utcnow()
            start_date = now.replace(day=1).strftime("%Y-%m-%d")
            end_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1).strftime("%Y-%m-%d")

            usage_r = await s.get(
                f"https://api.openai.com/v1/dashboard/billing/usage?start_date={start_date}&end_date={end_date}",
                headers=headers,
            )
            usage_data = usage_r.json() if usage_r.status_code == 200 else {}
            total_usage = usage_data.get("total_usage", 0) / 100

            plan = sub_data.get("plan", {})
            soft_limit = sub_data.get("soft_limit_usd", 0)
            hard_limit = sub_data.get("hard_limit_usd", 0)
            reset_date = (now.replace(day=1) + timedelta(days=32)).replace(day=1)

            return {
                "status": "success",
                "data": {
                    "account_id": sub_data.get("account_id", ""),
                    "plan_name": plan.get("title", "Unknown"),
                    "is_active": sub_data.get("status", "") == "active",
                    "has_payment_method": sub_data.get("has_payment_method", False),
                    "soft_limit_usd": soft_limit,
                    "hard_limit_usd": hard_limit,
                    "total_usage_usd": round(total_usage, 4),
                    "remaining_usd": round(max(0, soft_limit - total_usage), 4),
                    "usage_percent": round(total_usage / soft_limit * 100, 1) if soft_limit > 0 else 0,
                    "reset_date": reset_date.isoformat() + "Z",
                    "days_until_reset": (reset_date - now).days,
                },
            }
    except httpx.TimeoutException:
        return JSONResponse({"status": "error", "msg": "请求超时"}, 400)
    except httpx.HTTPError:
        return JSONResponse({"status": "error", "msg": "网络错误"}, 400)


@router.get("/{source}/stats")
async def get_pool_stats(source: str, _=Depends(api_auth)):
    """Get pool statistics."""
    pool = db.get_pool_data(source)
    if not pool:
        return JSONResponse({"status": "error", "msg": "Pool not found"}, 404)

    tokens = pool.get("tokens", {})
    api_key = tokens.get("apiKey") or tokens.get("key") or tokens.get("token")

    return {
        "status": "success",
        "data": {
            "source": source,
            "status": pool.get("status", "unknown"),
            "cookie_count": len(pool.get("cookies", {})),
            "has_api_key": bool(api_key),
        },
    }


# =============================================================================
# Polling Strategy
# =============================================================================
@router.get("/{source}/account")
async def get_polling_account(source: str, strategy: str = "round_robin", _=Depends(api_auth)):
    """Get next available account based on polling strategy."""
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


@router.post("/{source}/account/{account_id}/report")
async def report_account_result(
    source: str, account_id: int, success: bool = Form(...), latency: float = Form(None), _=Depends(api_auth)
):
    """Report request result for an account."""
    db.update_account_stats(int(account_id), success, latency)
    return {"status": "success"}


@router.get("/{source}/health")
async def get_pool_health(source: str, _=Depends(api_auth)):
    """Get health summary for a source pool."""
    health = db.get_account_health(source)
    return {"status": "success", "data": health}


@router.post("/{source}/account/add")
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
        return JSONResponse({"status": "error", "msg": "Invalid JSON"}, 400)
    db.add_proxy_account(source, account_index, cookies_dict, tokens_dict)
    return {"status": "success"}


@router.delete("/{source}/account/{account_id}")
async def delete_pool_account(source: str, account_id: int, _=Depends(api_auth)):
    """Delete a proxy account."""
    db.delete_proxy_account(account_id)
    return {"status": "success"}


@router.get("/{source}/score")
async def get_pool_score(source: str, max_latency: float = 5000, _=Depends(api_auth)):
    """Get health scores for all accounts in a pool."""
    try:
        health_scores = db.get_account_health_batch(source, max_latency)
        return {"status": "success", "data": {"source": source, "health_scores": health_scores}}
    except Exception as e:
        return JSONResponse({"status": "error", "msg": str(e)}, 500)


@router.get("/{source}/best")
async def get_best_pool_account(source: str, strategy: str = "health_score", _=Depends(api_auth)):
    """Get the best available account for a source."""
    try:
        account = db.get_best_account(source, strategy)
        if not account:
            return JSONResponse({"status": "error", "msg": f"No active account for {source}"}, 404)
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
        return JSONResponse({"status": "error", "msg": str(e)}, 500)


@router.post("/{source}/account/{account_id}/concurrent")
async def update_account_concurrent(source: str, account_id: int, delta: int = Form(...), _=Depends(api_auth)):
    """Update concurrent request count for an account."""
    try:
        db.increment_concurrent(account_id, delta)
        return {"status": "success"}
    except:
        return JSONResponse({"status": "error", "msg": "Update failed"}, 500)


@router.put("/{source}/account/{account_id}/config")
async def update_account_config(
    source: str, account_id: int, max_concurrent: int = Body(None), priority: int = Body(None), _=Depends(api_auth)
):
    """Update account configuration."""
    try:
        if max_concurrent is not None:
            db.update_account_concurrent_limit(account_id, max_concurrent)
        if priority is not None:
            db.update_account_priority(account_id, priority)
        return {"status": "success"}
    except:
        return JSONResponse({"status": "error", "msg": "Update failed"}, 500)
