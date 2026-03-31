"""
Admin Routes - /, /login, /admin/*
"""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import app.database as db

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


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
# Auth Routes
# =============================================================================
@router.get("/login", response_class=HTMLResponse)
async def login_page(r: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": r})


@router.post("/login")
async def login_do(username: str = Form(...), password: str = Form(...)):
    """Process login."""
    from app.main import ADMIN_PASS, ADMIN_USER, SESSION_KEY

    if username == ADMIN_USER and password == ADMIN_PASS:
        resp = JSONResponse({"status": "success"})
        resp.set_cookie("admin_token", SESSION_KEY, httponly=True, samesite="lax")
        return resp
    return JSONResponse({"status": "error", "msg": "Invalid credentials"}, 401)


# =============================================================================
# Admin Dashboard
# =============================================================================
@router.get("/", response_class=HTMLResponse)
async def index(r: Request):
    """Admin dashboard index."""
    from app.main import SESSION_KEY

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


@router.get("/admin")
async def admin_page(r: Request):
    """Admin dashboard (alias for /)."""
    from app.main import SESSION_KEY

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
