"""Routes package - API routers."""

from app.routes.admin import router as admin_router
from app.routes.audit import router as audit_router
from app.routes.chat import router as chat_router
from app.routes.keys import router as keys_router
from app.routes.models import router as models_router
from app.routes.oauth import router as oauth_router
from app.routes.pool import router as pool_router

__all__ = [
    "chat_router",
    "pool_router",
    "keys_router",
    "models_router",
    "oauth_router",
    "audit_router",
    "admin_router",
]
