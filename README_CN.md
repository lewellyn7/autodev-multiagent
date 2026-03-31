# AI Gateway - 智能路由网关

> 多源代理池 + OpenAI 兼容 API + 可视化管理后台

[English](README.md) | 中文

## 功能特性

- 🌐 **多源代理池** - ChatGPT / DeepSeek / Moonshot / Claude / Gemini / Qwen
- 🔄 **多账户轮询** - Round Robin / Random / Weighted / Circuit Breaker
- 🔗 **OAuth 支持** - GitHub / Google / Microsoft 账户绑定
- 📊 **用量监控** - OpenAI 订阅/配额实时查询
- 🔑 **API Key 管理** - 细粒度模型权限控制
- ⚡ **API 测试台** - 在线调试 chat completions
- 🛡️ **Rate Limiting** - 滑动窗口限流 (全局 60 req/min)
- 📝 **审计日志** - 完整操作审计
- 🔄 **协议转换** - OpenAI ↔ Claude ↔ Gemini 格式转换
- 🏥 **健康评分** - 多维度账户健康评估
- 🔁 **回退链** - 模型和 Provider 回退链
- 📈 **实时仪表盘** - 实时日志、健康指标、用量统计

## 系统架构

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
│  └── /api/models/* (model management)                 │
├─────────────────────────────────────────────────────────┤
│  Polling Engine                                        │
│  ├── Round Robin | Random | Weighted                   │
│  ├── Circuit Breaker | Health Scoring                  │
│  └── Fallback Chains (Model + Provider)                │
├─────────────────────────────────────────────────────────┤
│  Backend                                               │
│  ├── LiteLLM (100+ LLM providers)                     │
│  ├── PostgreSQL + SQLite                              │
│  └── Redis (optional, for rate limiting)               │
└─────────────────────────────────────────────────────────┘
```

## 快速部署

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+ (本地开发)

### Docker 部署

```bash
# 克隆项目
git clone https://github.com/lewellyn7/autodev-multiagent.git
cd autodev-multiagent

# 开发环境 (SQLite)
docker-compose -f docker-compose.dev.yml up -d

# 生产环境 (PostgreSQL)
docker-compose -f docker-compose.prod.yml up -d

# 访问管理后台
open http://localhost:28000
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_USER` | `admin` | 管理员账号 |
| `ADMIN_PASSWORD` | `password` | 管理员密码 |
| `DB_TYPE` | `sqlite` | 数据库类型 (postgres/sqlite) |
| `POSTGRES_HOST` | `postgres` | PostgreSQL 主机 |
| `POSTGRES_PORT` | `5432` | PostgreSQL 端口 |
| `GITHUB_CLIENT_ID` | - | GitHub OAuth App ID |
| `GITHUB_CLIENT_SECRET` | - | GitHub OAuth Secret |
| `GITHUB_REDIRECT_URI` | `http://localhost:8000/oauth/github/callback` | 回调地址 |
| `RATE_LIMIT_REQUESTS` | `60` | 速率限制 (请求数) |
| `RATE_LIMIT_WINDOW` | `60` | 速率限制 (时间窗口, 秒) |

## API 参考

### 认证

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /login` | POST | 管理员登录 |
| `GET /login` | GET | 登录页面 |
| `POST /logout` | POST | 登出 |

### OpenAI 兼容 API

```bash
curl -X POST http://localhost:28000/v1/chat/completions \
  -H "Authorization: Bearer $YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /v1/chat/completions` | POST | Chat Completions |
| `GET /v1/models` | GET | 模型列表 |

### 代理池

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/pool/{source}` | GET | 获取代理池数据 |
| `POST /api/pool/sync` | POST | Chrome 插件同步 |
| `POST /api/pool/test` | POST | 测试代理可用性 |
| `GET /api/pool/{source}/account` | GET | 获取下一个账户 (支持策略) |
| `POST /api/pool/{source}/account/{id}/report` | POST | 上报使用结果 |
| `GET /api/pool/{source}/health` | GET | 池健康状态 |
| `GET /api/pool/{source}/score` | GET | 健康评分 |

**轮询策略参数** (`strategy`):
- `round_robin` - 轮询 (默认)
- `random` - 随机
- `weighted` - 加权 (按成功率)
- `circuit_breaker` - 熔断 (失败 >5 次跳过)
- `health_score` - 健康评分优先
- `priority` - 优先级优先

### 审计日志

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/audit/logs` | GET | 审计日志列表 |
| `GET /api/audit/stats` | GET | 审计统计 |
| `POST /api/audit/cleanup` | POST | 清理旧日志 |

### OAuth

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /oauth/github` | GET | GitHub 授权 |
| `GET /oauth/github/callback` | GET | GitHub 回调 |
| `GET /api/oauth/accounts` | GET | 已绑定账户 |
| `DELETE /api/oauth/accounts/{provider}` | DELETE | 解绑账户 |

### 模型管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/models` | GET | 模型列表 |
| `POST /api/models` | POST | 添加模型 |
| `DELETE /api/models/{id}` | DELETE | 删除模型 |
| `DELETE /api/models/expired/{id}` | DELETE | 删除过期模型 |
| `POST /api/models/fetch` | POST | 自动获取模型 |

### API Keys

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/keys` | GET | Key 列表 |
| `POST /api/keys` | POST | 创建 Key |
| `PUT /api/keys/{key}` | PUT | 更新 Key |
| `DELETE /api/keys/{key}` | DELETE | 删除 Key |

## 轮询策略

### Round Robin (轮询)
按顺序循环选择账户，确保负载均衡。

### Random (随机)
随机选择账户，适合无状态场景。

### Weighted (加权)
按成功率权重选择，成功率高的账户被选中概率更大。

### Circuit Breaker (熔断)
失败次数超过阈值的账户自动跳过，恢复后需手动重置。

### Health Score (健康评分)
综合响应时间、成功率、并发数计算健康评分，选择最健康的账户。

### Priority (优先级)
按预设优先级选择账户。

## 健康评分

```
health_score = (success_rate * 0.4) + (avg_latency_score * 0.3) + (concurrent_factor * 0.3)
```

- **success_rate**: 成功次数 / 总请求数
- **avg_latency_score**: 归一化延迟分数 (延迟越低分数越高)
- **concurrent_factor**: 并发利用率 (低并发 = 高分数)

## 回退链

### 模型回退
当指定模型不可用时，自动回退到备选模型：

```
gpt-4o → gpt-4o-mini → gpt-3.5-turbo
```

### Provider 回退
当 Provider 全部不可用时，切换到下一个 Provider：

```
ChatGPT → DeepSeek → Claude → Gemini → Qwen
```

## 管理后台

访问 `http://localhost:28000/` 登录后台。

功能模块：
- 📊 概览仪表盘 - 系统健康 / 统计数据
- 💰 用量查询 - OpenAI 订阅 / 配额进度
- 🍪 代理池 - 账户管理 / 状态监控
- 🔗 OAuth - 第三方账户绑定
- 📚 模型库 - 模型列表 / 批量操作
- 🔑 API Keys - Key 管理 / 权限配置
- ⚡ API 测试台 - 在线请求调试

## 项目结构

```
ai-gateway/
├── app/
│   ├── main.py              # FastAPI 主应用
│   ├── config.py           # 配置管理
│   ├── database.py         # 数据库操作 (sync)
│   ├── database_async.py   # 异步数据库操作
│   ├── router.py           # 智能路由
│   ├── middleware.py       # 中间件 (Rate Limiting)
│   ├── providers/          # LLM Provider 包装器
│   │   ├── chatgpt.py
│   │   ├── deepseek.py
│   │   ├── moonshot.py
│   │   ├── claude.py
│   │   ├── gemini.py
│   │   └── qwen.py
│   ├── routes/             # API Router 模块
│   │   ├── admin.py
│   │   ├── audit.py
│   │   ├── chat.py
│   │   ├── keys.py
│   │   ├── models.py
│   │   ├── oauth.py
│   │   └── pool.py
│   └── templates/
│       ├── admin.html      # 管理后台 (Vue 3)
│       └── login.html      # 登录页面
├── tests/                   # 单元测试
├── .github/workflows/       # CI/CD
├── Dockerfile              # 多阶段构建
├── docker-compose.yml      # SQLite 版本
├── docker-compose.dev.yml  # 开发环境
├── docker-compose.prod.yml # 生产环境 (PostgreSQL)
├── requirements.txt
└── pyproject.toml
```

## 技术栈

- **后端**: FastAPI + Uvicorn + Pydantic
- **LLM**: LiteLLM (100+ providers)
- **数据库**: PostgreSQL + SQLite + asyncpg
- **前端**: Vue 3 + Tailwind CSS (CDN)
- **容器**: Docker + Docker Compose

## Docker 镜像

### 多阶段构建

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder
RUN pip wheel --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl
COPY app/ ./app/
USER appuser
```

### 镜像大小对比

| 版本 | 大小 |
|------|------|
| 单阶段构建 | ~2.4 GB |
| 多阶段构建 | **~684 MB** |

## CI/CD

GitHub Actions 自动流水线：

1. **Lint** - Ruff 代码检查
2. **Test** - Docker 容器内运行 pytest
3. **Build** - 多架构 Docker 镜像构建
4. **Deploy** - 自动部署到服务器

触发条件：
- `push to main` → 构建 + 推送镜像 + 部署
- `PR` → Lint + Test

镜像地址: `ghcr.io/lewellyn7/autodev-multiagent:latest`

## 性能

- **吞吐量**: 1000+ req/min (单实例)
- **延迟**: P99 < 500ms (不含 LLM 响应时间)
- **并发**: 支持 100+ 并发连接

## 相关项目

- [LiteLLM](https://github.com/BerriAI/litellm) - 统一 LLM 调用
- [gpt4free](https://github.com/xtekky/gpt4free) - Reference only

## License

MIT
