"""
OAuth Routes - /oauth/*
"""

import base64
import hashlib
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import app.database as db

router = APIRouter(prefix="/oauth", tags=["oauth"])


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
# GitHub OAuth
# =============================================================================
GITHUB_CLIENT_ID = None
GITHUB_CLIENT_SECRET = None
GITHUB_REDIRECT_URI = None


def get_github_config():
    global GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_REDIRECT_URI
    import os

    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:8000/oauth/github/callback")


def generate_oauth_state() -> str:
    """Generate a secure random state for OAuth."""
    return secrets.token_urlsafe(32)


def encode_oauth_state(state: str) -> str:
    """Encode state with session key for security."""
    from app.main import SESSION_KEY

    timestamp = str(int(time.time()))
    signature = hashlib.sha256(f"{state}{SESSION_KEY}{timestamp}".encode()).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{state}:{timestamp}:{signature}".encode()).decode()


def decode_oauth_state(encoded: str) -> bool:
    """Decode and verify OAuth state."""
    from app.main import SESSION_KEY

    try:
        decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
        state, timestamp, signature = decoded.split(":")
        expected_sig = hashlib.sha256(f"{state}{SESSION_KEY}{timestamp}".encode()).hexdigest()[:16]
        if signature != expected_sig:
            return False
        if time.time() - int(timestamp) > 300:
            return False
        return True
    except:
        return False


@router.get("/github")
async def oauth_github(request: Request):
    """Redirect to GitHub OAuth authorization page."""
    get_github_config()
    if not GITHUB_CLIENT_ID:
        raise HTTPException(500, "GitHub OAuth not configured")

    state = generate_oauth_state()
    encoded_state = encode_oauth_state(state)

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


@router.get("/github/callback")
async def oauth_github_callback(request: Request, code: str = None, state: str = None):
    """GitHub OAuth callback handler."""
    get_github_config()
    if not code:
        raise HTTPException(400, "Authorization code required")

    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(500, "GitHub OAuth not configured")

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
            raise HTTPException(400, "Failed to exchange code for token")

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        expires_at = int(time.time() + expires_in) if expires_in else None

        if not access_token:
            raise HTTPException(400, "No access token received")

        user_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        )

        if user_response.status_code != 200:
            raise HTTPException(400, "Failed to get user info")

        user_data = user_response.json()
        provider_user_id = str(user_data.get("id"))
        email = user_data.get("email")

        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
            )
            if emails_response.status_code == 200:
                for e in emails_response.json():
                    if e.get("primary"):
                        email = e.get("email")
                        break

        db.add_oauth_account(
            provider="github",
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            email=email,
        )

    return RedirectResponse("/", 302)


@router.get("/accounts")
async def get_oauth_accounts(_=Depends(api_auth)):
    """Get list of all bound OAuth accounts."""
    accounts = db.get_all_oauth_accounts()
    return {"status": "success", "data": accounts}


@router.delete("/accounts/{provider}")
async def delete_oauth_account(provider: str, _=Depends(api_auth)):
    """Unbind OAuth account by provider."""
    db.delete_oauth_account_by_provider(provider)
    return {"status": "success", "msg": f"Unbound {provider}"}
