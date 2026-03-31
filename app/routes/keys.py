"""
API Key Management Routes - /api/keys/*
"""

import secrets

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request

import app.database as db

router = APIRouter(prefix="/api/keys", tags=["keys"])


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
# Key Management
# =============================================================================
@router.post("")
async def add_key(name: str = Form(...), models: str = Form(""), _=Depends(api_auth)):
    """Create a new API key."""
    k = f"sk-{secrets.token_hex(16)}"
    db.add_key(k, name, models)
    return {"status": "ok", "key": k}


@router.put("/{key}")
async def upd_key(key: str, name: str = Body(...), models: str = Body(""), _=Depends(api_auth)):
    """Update an API key."""
    db.update_key(key, name, models)
    return {"status": "ok"}


@router.delete("/{key}")
async def del_key(key: str, _=Depends(api_auth)):
    """Delete an API key."""
    db.del_key(key)
    return {"status": "ok"}
