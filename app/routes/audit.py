"""
Audit Routes - /api/audit/*
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request

import app.database as db

router = APIRouter(prefix="/api/audit", tags=["audit"])


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
# Audit Logs
# =============================================================================
@router.get("/logs")
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
    """Get audit logs with optional filters."""
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

    logs = db.get_audit_logs(filters=filters if filters else None, limit=limit, offset=offset)

    return {"status": "success", "data": logs, "pagination": {"limit": limit, "offset": offset, "total": len(logs)}}


@router.get("/stats")
async def get_audit_stats(request: Request, start_date: str = None, end_date: str = None, _: dict = Depends(api_auth)):
    """Get audit log statistics."""
    try:
        stats = db.get_audit_stats(start_date=start_date, end_date=end_date)
        return {"status": "success", "data": stats}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch stats: {str(e)}")


@router.post("/cleanup")
async def cleanup_audit_logs(days_to_keep: int = Form(30), _: dict = Depends(api_auth)):
    """Clean up old audit logs."""
    try:
        deleted = db.cleanup_old_logs(days_to_keep)
        return {"status": "success", "msg": f"Deleted {deleted} old audit log entries"}
    except Exception as e:
        raise HTTPException(500, f"Failed to cleanup: {str(e)}")
