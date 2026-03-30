# AI Gateway API Documentation

> **Version:** 1.0.0 | **Base URL:** `http://localhost:8000`

---

## Table of Contents

1. [Health Check](#health-check)
2. [Authentication](#authentication)
3. [Admin Dashboard](#admin-dashboard)
4. [Proxy Pool](#proxy-pool)
5. [Models](#models)
6. [API Keys](#api-keys)
7. [OpenAI-Compatible API](#openai-compatible-api)
8. [Rate Limiting](#rate-limiting)

---

## Health Check

### `GET /health`

Kubernetes/Docker health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": 1743321234.567
}
```

---

## Authentication

### `GET /login`

Returns the login page HTML.

### `POST /login`

Admin login endpoint.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `username` | string | ✅ | Admin username |
| `password` | string | ✅ | Admin password |

**Response:**
```json
{ "status": "success" }
```
Sets `admin_token` cookie.

---

## Admin Dashboard

### `GET /`

Returns admin dashboard HTML (requires `admin_token` cookie).

---

## Proxy Pool

### `POST /api/pool/sync`

Sync proxy pool data.

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `source` | string | ✅ | Pool source (chatgpt, claude, etc.) |
| `cookies` | object | ✅ | Cookie dictionary |
| `tokens` | object | ✅ | Token dictionary |

### `DELETE /api/pool/{source}`

Delete pool data for a source (requires auth).

### `POST /api/pool/update_token`

Update token for a pool source (requires auth).

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `source` | string | ✅ | Pool source |
| `token` | string | ✅ | New token value |

### `POST /api/pool/test`

Test pool validity (requires auth).

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `source` | string | ✅ | Pool source to test |

**Response:**
```json
{
  "status": "success",
  "data": {
    "valid": true,
    "msg": "有效 (Web Session)"
  }
}
```

---

## Models

### `POST /api/models`

Add model manually (requires auth).

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `name` | string | ✅ | Model name |
| `source` | string | ✅ | Model source |

### `DELETE /api/models/{id}`

Delete model (requires auth). Moves to expired list.

### `DELETE /api/models/expired/{id}`

Delete from expired list (requires auth).

### `POST /api/models/fetch`

Auto-fetch models from provider (requires auth).

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `source` | string | ✅ | Provider source |
| `api_key` | string | ❌ | Override API key |

**Response:**
```json
{
  "status": "success",
  "msg": "更新 25 个模型"
}
```

---

## API Keys

### `POST /api/keys`

Create new API key (requires auth).

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `name` | string | ✅ | Key name/label |
| `models` | string | ❌ | Comma-separated model list (empty = all) |

**Response:**
```json
{ "status": "ok", "key": "sk-abc123..." }
```

### `PUT /api/keys/{key}`

Update API key (requires auth).

**Request Body:**
```json
{ "name": "new name", "models": "gpt-4o,claude-3-5-sonnet" }
```

### `DELETE /api/keys/{key}`

Delete API key (requires auth).

---

## OpenAI-Compatible API

### `GET /v1/models`

List available models (public).

**Response:**
```json
{
  "object": "list",
  "data": [
    { "id": "gpt-4o", "object": "model", "created": 1743321234, "owned_by": "chatgpt" },
    { "id": "claude-3-5-sonnet-20240620", "object": "model", "created": 1743321234, "owned_by": "claude" }
  ]
}
```

### `POST /v1/chat/completions`

OpenAI-compatible chat completion endpoint.

**Request:**
```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "system", "content": "You are helpful." },
    { "role": "user", "content": "Hello!" }
  ],
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1743321234,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "Hello! How can I help?" },
      "finish_reason": "stop"
    }
  ]
}
```

**Streaming Response:**
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1743321234,"model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: [DONE]
```

---

## Rate Limiting

All endpoints are subject to rate limiting.

| Scope | Limit | Scope |
|-------|-------|-------|
| Global (per API key) | 60 req/min | All endpoints |
| Admin (per session) | 30 req/min | `/api/*` endpoints |

**Response Headers (on every response):**
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1743321294
```

**Rate Limit Exceeded (429):**
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 45
}
```

---

## Error Codes

| HTTP Code | Meaning |
|-----------|---------|
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid/missing API key or session |
| 403 | Forbidden - Model not allowed for this key |
| 404 | Not Found |
| 429 | Rate Limit Exceeded |
| 500 | Internal Server Error |

---

## Model Name Mapping

| Prefix | Provider |
|--------|----------|
| `gpt`, `o1-` | ChatGPT |
| `claude` | Claude |
| `gemini` | Gemini |
| `deepseek` | DeepSeek |
| `moonshot` | Moonshot (Kimi) |
| `qwen` | Qwen |
