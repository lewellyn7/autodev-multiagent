# AI Gateway - Intelligent Routing Gateway

> Multi-source proxy pool + OpenAI compatible API + Visual management dashboard

[中文](README_CN.md) | English

## Features

- 🌐 **Multi-source Proxy Pool** - ChatGPT / DeepSeek / Moonshot / Claude / Gemini / Qwen
- 🔄 **Multi-account Polling** - Round Robin / Random / Weighted / Circuit Breaker strategies
- 🔗 **OAuth Support** - GitHub / Google / Microsoft account binding
- 📊 **Usage Monitoring** - OpenAI subscription/quota real-time query
- 🔑 **API Key Management** - Fine-grained model permission control
- ⚡ **API Test Console** - Online chat completions debugging
- 🛡️ **Rate Limiting** - Sliding window (60 req/min global)
- 📝 **Audit Logging** - Complete operation audit trail
- 🔄 **Protocol Conversion** - OpenAI ↔ Claude ↔ Gemini format conversion
- 🏥 **Health Scoring** - Multi-dimensional account health evaluation
- 🔁 **Fallback Chains** - Model and Provider fallback chains
- 📈 **Real-time Dashboard** - Live logs, health indicators, usage stats

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AI Gateway                          │
├─────────────────────────────────────────────────────────┤
│  Admin UI (Vue 3 + Tailwind CSS)                       │
│  ├── Dashboard (stats, health, usage)                   │
│  ├── Proxy Pool (multi-account management)              │
│  ├── OAuth Accounts                                    │
│  ├── Model Library                                     │
│  ├── API Keys                                          │
│  └── API Test Console                                  │
├─────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                   │
│  ├── /v1/chat/completions (OpenAI compatible)          │
│  ├── /api/pool/* (proxy management)                   │
│  ├── /api/oauth/* (OAuth accounts)                    │
│  ├── /api/audit/* (audit logs)                        │
│  └── /api/models/* (model management)                 │
├─────────────────────────────────────────────────────────┤
│  Polling Engine                                        │
│  ├── Round Robin | Random | Weighted                   │
│  ├── Circuit Breaker | Health Scoring                 │
│  └── Fallback Chains (Model + Provider)               │
├─────────────────────────────────────────────────────────┤
│  Backend                                               │
│  ├── g4f (free ChatGPT)                               │
│  ├── Cookie/Token pools                               │
│  ├── OAuth authentication                             │
│  └── PostgreSQL / SQLite                              │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Docker 20.0+
- PostgreSQL 15+ (optional, SQLite fallback)

### Docker Deployment

```bash
# Clone the repository
git clone https://github.com/lewellyn7/autodev-multiagent.git
cd autodev-multiagent

# Build and run
docker build -t aigateway:latest .
docker run -d -p 28000:8000 \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=your_secure_password \
  --name aigateway \
  aigateway:latest
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_USER` | `admin` | Admin username |
| `ADMIN_PASSWORD` | `password` | Admin password |
| `GITHUB_CLIENT_ID` | - | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | - | GitHub OAuth App secret |
| `GITHUB_REDIRECT_URI` | `http://localhost:8000/oauth/github/callback` | OAuth callback URL |
| `DB_TYPE` | `postgres` | Database type (postgres/sqlite) |
| `DATABASE_URL` | - | PostgreSQL connection string |

### Docker Compose

```yaml
version: '3'
services:
  gateway:
    build: .
    ports:
      - "28000:8000"
    environment:
      - ADMIN_USER=admin
      - ADMIN_PASSWORD=your_secure_password
      - DB_TYPE=postgres
      - DATABASE_URL=postgresql://user:pass@postgres:5432/gateway
    depends_on:
      - postgres
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=gateway
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

## API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /login` | POST | Admin login |
| `POST /logout` | POST | Logout |

### OpenAI Compatible

```bash
curl -X POST http://localhost:28000/v1/chat/completions \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /v1/chat/completions` | POST | Chat completions |
| `GET /v1/models` | GET | Model list |

### Proxy Pool

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/pool/{source}` | GET | Get pool data |
| `POST /api/pool/sync` | POST | Chrome extension sync |
| `POST /api/pool/test` | POST | Test proxy availability |
| `GET /api/pool/{source}/account` | GET | Get next account (with strategy) |
| `POST /api/pool/{source}/account/{id}/report` | POST | Report usage result |
| `GET /api/pool/{source}/health` | GET | Pool health status |
| `GET /api/pool/{source}/score` | GET | Account health score |
| `GET /api/pool/{source}/best` | GET | Get best account |

**Query Parameters for `/api/pool/{source}/account`:**
- `strategy` - `round_robin` | `random` | `weighted` | `circuit_breaker`

### OpenAI Subscription

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/pool/openai/subscription` | GET | Get OpenAI subscription info |

### Audit Logs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/audit/logs` | GET | Get audit logs (paginated) |
| `GET /api/audit/stats` | GET | Get audit statistics |
| `POST /api/audit/cleanup` | POST | Cleanup old logs |

### OAuth

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /oauth/github` | GET | GitHub authorization |
| `GET /oauth/github/callback` | GET | GitHub OAuth callback |
| `GET /api/oauth/accounts` | GET | List bound accounts |
| `DELETE /api/oauth/accounts/{provider}` | DELETE | Unbind account |

### Model Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/models` | GET | List models |
| `POST /api/models` | POST | Add model |
| `DELETE /api/models/{id}` | DELETE | Delete model |
| `POST /api/models/fetch` | POST | Auto-fetch models |

### API Keys

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/keys` | GET | List API keys |
| `POST /api/keys` | POST | Create key |
| `PUT /api/keys/{key}` | PUT | Update key |
| `DELETE /api/keys/{key}` | DELETE | Delete key |

## Polling Strategies

### Round Robin
Cyclic rotation based on last_used timestamp.

### Random
Random account selection.

### Weighted
Selection weighted by success rate.
```
weight = success_count / (success_count + fail_count)
```

### Circuit Breaker
Skip accounts with >5 recent failures.

## Health Scoring

Multi-dimensional scoring algorithm:
```
score = (success_rate × 0.4) + (latency_score × 0.3) + (availability × 0.3)

where:
  success_rate = success_count / (success_count + fail_count)
  latency_score = 1 - (avg_latency / max_latency_threshold)
  availability = 1 if status='active' else 0
```

## Fallback Chains

### Model Fallback
```
gpt-4o → gpt-4o-mini → gpt-4-turbo → gpt-3.5-turbo
claude-3-opus → claude-3-sonnet → claude-3-haiku
gemini-1.5-pro → gemini-1.5-flash → gemini-pro
```

### Provider Fallback
```
chatgpt → deepseek → moonshot → openai
claude → chatgpt → deepseek
gemini → chatgpt → deepseek
```

## Admin Dashboard

Access `http://localhost:28000/` to manage:

- 📊 **Dashboard** - System health, stats, usage overview
- 💰 **Usage** - OpenAI subscription/quota with progress bars
- 🍪 **Proxy Pool** - Account management, status monitoring
- 🔗 **OAuth** - Third-party account binding
- 📚 **Model Library** - Model list, batch operations
- 🔑 **API Keys** - Key management, permission config
- ⚡ **API Test** - Online request debugging

## Chrome Extension Sync

1. Load `extension/` directory as Chrome extension
2. Login to target websites (ChatGPT / Claude / etc.)
3. Cookies automatically sync to gateway

## Project Structure

```
ai-gateway/
├── app/
│   ├── main.py           # FastAPI application
│   ├── database.py       # Database operations
│   ├── middleware.py     # Rate limiting middleware
│   └── templates/
│       ├── admin.html    # Admin dashboard (Vue 3)
│       └── login.html    # Login page
├── extension/            # Chrome extension
├── .github/workflows/    # CI/CD pipelines
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Tech Stack

- **Backend**: FastAPI + Uvicorn + Pydantic
- **Database**: PostgreSQL / SQLite
- **Frontend**: Vue 3 + Tailwind CSS (CDN)
- **Proxy**: g4f (Google, Get Free ChatGPT)
- **Container**: Docker + Docker Compose

## CI/CD

GitHub Actions workflows:
- `docker.yml` - Build and push to GHCR
- `test.yml` - pytest + coverage
- `lint.yml` - ruff + flake8 + mypy

## Performance

| Metric | Value |
|--------|-------|
| Health check latency | ~30ms |
| Concurrent requests | 10 concurrent @ ~90ms |
| Memory usage | ~61MB |
| Image size | 378MB |

## Related Projects

Inspired by:
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) - Go-based CLI proxy with OAuth
- [AIClient-2-API](https://github.com/justlovemaki/AIClient-2-API) - Node.js multi-protocol gateway

## License

MIT
