import pytest, os, time
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient

# Set test env before importing app
os.environ["ADMIN_USER"] = "testadmin"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["DEBUG"] = "false"

from app.main import (
    app, ADMIN_USER, ADMIN_PASS, SESSION_KEY,
    health_check, verify_client_key, api_auth,
    SyncData, ChatMsg, ChatReq,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def auth_cookies(client):
    resp = client.post("/login", data={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    return resp.cookies

# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_check(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data

# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_success(client):
    resp = client.post("/login", data={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "admin_token" in resp.cookies

def test_login_failure(client):
    resp = client.post("/login", data={"username": "wrong", "password": "wrong"})
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"

def test_login_wrong_password(client):
    resp = client.post("/login", data={"username": "testadmin", "password": "wrongpass"})
    assert resp.status_code == 401

# ---------------------------------------------------------------------------
# Auth Guard - Redirect
# ---------------------------------------------------------------------------
def test_index_redirects_without_auth(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"

def test_index_accessible_with_auth(client, auth_cookies):
    resp = client.get("/", cookies=auth_cookies)
    assert resp.status_code == 200

# ---------------------------------------------------------------------------
# API Key Auth
# ---------------------------------------------------------------------------
def test_v1_models_no_auth(client):
    resp = client.get("/v1/models")
    # Should return model list without auth (public endpoint)
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_chat_completions_no_key(async_client):
    resp = await async_client.post("/v1/chat/completions", json={
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "hello"}],
    })
    assert resp.status_code == 401

# ---------------------------------------------------------------------------
# Pool Management (requires auth)
# ---------------------------------------------------------------------------
def test_pool_sync(client):
    # Pool sync doesn't require auth (client-side operation)
    resp = client.post("/api/pool/sync", json={
        "source": "deepseek",
        "cookies": {},
        "tokens": {"apiKey": "test"},
    })
    assert resp.status_code == 200

def test_pool_delete_requires_auth(client):
    resp = client.delete("/api/pool/deepseek")
    assert resp.status_code == 401

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
def test_sync_data_model():
    data = SyncData(source="deepseek", cookies={}, tokens={"apiKey": "sk-123"})
    assert data.source == "deepseek"
    assert data.tokens["apiKey"] == "sk-123"

def test_chat_req_model():
    req = ChatReq(
        model="gpt-4o",
        messages=[ChatMsg(role="user", content="hi")],
        stream=False,
    )
    assert req.model == "gpt-4o"
    assert len(req.messages) == 1
    assert req.messages[0].content == "hi"

def test_chat_req_stream_default():
    req = ChatReq(model="gpt-4o", messages=[ChatMsg(role="user", content="hi")])
    assert req.stream is False

# ---------------------------------------------------------------------------
# Config Externalization
# ---------------------------------------------------------------------------
def test_config_from_env():
    assert ADMIN_USER == "testadmin"
    assert ADMIN_PASS == "testpass"

# ---------------------------------------------------------------------------
# Session Key
# ---------------------------------------------------------------------------
def test_session_key_is_hex():
    assert len(SESSION_KEY) == 32  # 16 bytes = 32 hex chars
    assert all(c in "0123456789abcdef" for c in SESSION_KEY)
