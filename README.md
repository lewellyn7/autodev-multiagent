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
│  ├── Dashboard (stats, health, usage)                  │
│  ├── Proxy Pool (multi-account management)             │
│  ├── OAuth Accounts                                    │
│  ├── Model Library                                     │
│  ├── API Keys                                          │
│  └── API Test Console                                  │
├─────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                   │
│  ├── /v1/chat/completions (OpenAI compatible)          │
│  ├── /v1/models (OpenAI compatible)                   │
│  ├── /api/pool/* (proxy management)                   │
│  ├── /api/oauth/* (OAuth accounts)                    │
│  ├── /api/audit/* (audit logs)                        │
│  └── /api/models/* (model management)                  │
├─────────────────────────────────────────────────────────┤
│  Polling Engine                                        │
│  ├── Round Robin | Random | Weighted                   │
│  ├── Circuit Breaker | Health Scoring                 │
│  └── Fallback Chains (Model + Provider)               │
├─────────────────────────────────────────────────────────┤
│  Backend                                               │
│  ├── LiteLLM (100+ LLM providers)                    │
│  ├── Provider Wrappers (chatgpt, deepseek, etc.)    │
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

# Development (SQLite)
docker-compose -f docker-compose.dev.yml up -d --build

# Production (PostgreSQL)
cp .env.docker .env
# Edit .env with your credentials
docker-compose -f docker-compose.prod.yml up -d --build
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_USER` | `admin` | Admin username |
| `ADMIN_PASSWORD` | `password` | Admin password |
| `DB_TYPE` | `postgres` | Database type (postgres/sqlite) |
| `DB_FILE` | `data/gateway.db` | SQLite database file |
| `POSTGRES_HOST` | `postgres` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `ai_gateway` | PostgreSQL database |
| `POSTGRES_USER` | `postgres` | PostgreSQL user |
| `POSTGRES_PASSWORD` | - | PostgreSQL password |
| `GITHUB_CLIENT_ID` | - | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | - | GitHub OAuth App secret |
| `ENCRYPTION_KEY` | - | 32-byte encryption key |
| `SECRET_KEY` | - | Session secret key |

## API Reference

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /login` | GET | Login page |
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
| `POST /api/pool/sync` | POST | Chrome extension sync |
| `DELETE /api/pool/{source}` | DELETE | Delete pool |
| `POST /api/pool/update_token` | POST | Update token |
| `POST /api/pool/test` | POST | Test proxy availability |
| `GET /api/pool/openai/subscription` | GET | Get OpenAI subscription info |
| `GET /api/pool/{source}/stats` | GET | Pool statistics |
| `GET /api/pool/{source}/account` | GET | Get next account (with strategy) |
| `POST /api/pool/{source}/account/add` | POST | Add account |
| `DELETE /api/pool/{source}/account/{account_id}` | DELETE | Delete account |
| `POST /api/pool/{source}/account/{account_id}/report` | POST | Report usage result |
| `POST /api/pool/{source}/account/{account_id}/concurrent` | POST | Report concurrent usage |
| `PUT /api/pool/{source}/account/{account_id}/config` | PUT | Update account config |
| `GET /api/pool/{source}/health` | GET | Pool health status |
| `GET /api/pool/{source}/score` | GET | Account health score |
| `GET /api/pool/{source}/best` | GET | Get best account |

**Query Parameters for `/api/pool/{source}/account`:**
- `strategy` - `round_robin` | `random` | `weighted` | `circuit_breaker`

### Audit Logs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/audit/logs` | GET | Get audit logs (paginated) |
| `GET /api/audit/stats` | GET | Get audit statistics |

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
| `GET /api/models` | GET | List models (implicit, via /v1/models) |
| `POST /api/models` | POST | Add model |
| `DELETE /api/models/{id}` | DELETE | Delete model |
| `DELETE /api/models/expired/{id}` | DELETE | Delete expired model |
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

## Project Structure

```
ai-gateway/
├── app/
│   ├── main.py              # FastAPI application
│   ├── main.py.bak/backup   # Backup versions
│   ├── database.py          # Database operations
│   ├── database_async.py    # Async database layer (aiosqlite + asyncpg)
│   ├── config.py             # Configuration management (pydantic-settings)
│   ├── middleware.py         # Rate limiting middleware
│   ├── router.py            # Smart routing engine
│   ├── providers/            # Provider wrappers
│   │   ├── __init__.py
│   │   ├── chatgpt.py       # OpenAI ChatGPT
│   │   ├── deepseek.py      # DeepSeek
│   │   ├── moonshot.py      # Moonshot
│   │   ├── claude.py        # Anthropic Claude
│   │   ├── gemini.py        # Google Gemini
│   │   └── qwen.py          # Alibaba Qwen
│   ├── routes/               # APIRouter modules
│   │   ├── __init__.py
│   │   └── chat.py          # Chat completions route
│   └── templates/
│       ├── admin.html       # Admin dashboard (Vue 3)
│       └── login.html       # Login page
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Default compose
├── docker-compose.dev.yml    # Development (SQLite)
├── docker-compose.prod.yml  # Production (PostgreSQL)
├── .env.example             # Environment variables template
├── .env.docker              # Docker environment template
└── requirements.txt
```

## Tech Stack

- **Backend**: FastAPI + Uvicorn + Pydantic
- **LLM Integration**: LiteLLM (OpenAI, Anthropic, Google, DeepSeek, etc.)
- **Database**: PostgreSQL / SQLite (asyncpg + aiosqlite)
- **Frontend**: Vue 3 + Tailwind CSS (CDN)
- **Container**: Docker + Docker Compose

## Docker Images

### Multi-stage Build
- **Builder stage**: Compiles dependencies and creates wheel cache
- **Runtime stage**: Minimal Python runtime with pre-installed packages
- **Non-root user**: Runs as `appuser` for security

### Image Size Comparison
| Version | Size |
|---------|------|
| Original (with g4f) | ~2.4GB |
| Optimized (LiteLLM) | ~400MB |

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
| Image size | ~400MB |

## Related Projects

Inspired by:
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) - Go-based CLI proxy with OAuth
- [AIClient-2-API](https://github.com/justlovemaki/AIClient-2-API) - Node.js multi-protocol gateway
- [LiteLLM](https://github.com/BerriAI/litellm) - Unified LLM API layer

## License

MIT
