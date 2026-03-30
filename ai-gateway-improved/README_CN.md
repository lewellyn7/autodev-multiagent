# AI Gateway - 智能路由网关

> 多源代理池 + OpenAI 兼容 API + 可视化管理后台

## 功能特性

- 🌐 **多源代理池** - ChatGPT / DeepSeek / Moonshot / Claude / Gemini / Qwen
- 🔄 **多账户轮询** - Round Robin / Random / Weighted / Circuit Breaker
- 🔗 **OAuth 支持** - GitHub / Google / Microsoft 账户绑定
- 📊 **用量监控** - OpenAI 订阅/配额实时查询
- 🔑 **API Key 管理** - 细粒度模型权限控制
- ⚡ **API 测试台** - 在线调试 chat completions
- 🛡️ **Rate Limiting** - 滑动窗口限流 (全局 60 req/min)
- 📝 **结构化日志** - 完整操作审计

## 快速部署

```bash
# 克隆项目
git clone https://github.com/lewellyn7/autodev-multiagent.git
cd autodev-multiagent

# 配置环境变量
export ADMIN_USER=admin
export ADMIN_PASSWORD=your_secure_password
export GITHUB_CLIENT_ID=your_github_client_id
export GITHUB_CLIENT_SECRET=your_github_secret

# Docker 构建并启动
docker build -t aigateway:latest .
docker run -d -p 28000:8000 \
  -e ADMIN_USER=admin \
  -e ADMIN_PASSWORD=your_password \
  --name aigateway \
  aigateway:latest
```

## API 端点

### 认证

| 端点 | 方法 | 说明 |
|------|------|------|
| `POST /login` | POST | 管理员登录 |
| `POST /logout` | POST | 登出 |

### 代理池

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/pool/{source}` | GET | 获取代理池数据 |
| `POST /api/pool/sync` | POST | Chrome 插件同步 |
| `POST /api/pool/test` | POST | 测试代理可用性 |
| `GET /api/pool/{source}/account` | GET | 获取下一个账户 (支持策略) |
| `POST /api/pool/{source}/account/{id}/report` | POST | 上报使用结果 |
| `GET /api/pool/{source}/health` | GET | 池健康状态 |

**轮询策略参数** (`strategy`):
- `round_robin` - 轮询 (默认)
- `random` - 随机
- `weighted` - 加权 (按成功率)
- `circuit_breaker` - 熔断 (失败 >5 次跳过)

### OpenAI 兼容

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

### 管理 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/pool/openai/subscription` | GET | OpenAI 订阅信息 |
| `GET /api/pool/{source}/stats` | GET | 池统计 |
| `GET /api/pool/stats` | GET | 全量池统计 |

### 模型管理

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/models` | GET | 模型列表 |
| `POST /api/models` | POST | 添加模型 |
| `DELETE /api/models/{id}` | DELETE | 删除模型 |
| `POST /api/models/fetch` | POST | 自动获取模型 |

### API Keys

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/keys` | GET | Key 列表 |
| `POST /api/keys` | POST | 创建 Key |
| `PUT /api/keys/{key}` | PUT | 更新 Key |
| `DELETE /api/keys/{key}` | DELETE | 删除 Key |

### OAuth

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /oauth/github` | GET | GitHub 授权 |
| `GET /oauth/github/callback` | GET | GitHub 回调 |
| `GET /api/oauth/accounts` | GET | 已绑定账户 |
| `DELETE /api/oauth/accounts/{provider}` | DELETE | 解绑账户 |

## 轮询策略详解

### Round Robin (轮询)
```python
# 按顺序循环选择账户
account = get_pool_by_strategy("chatgpt", "round_robin")
```

### Weighted (加权)
```python
# 按成功率权重选择
# 成功率 80% 的账户被选中概率是 60% 账户的 1.33 倍
account = get_pool_by_strategy("chatgpt", "weighted")
```

### Circuit Breaker (熔断)
```python
# 失败次数 > 5 的账户自动跳过
# 恢复后需手动或定时重置
account = get_pool_by_strategy("chatgpt", "circuit_breaker")
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_USER` | `admin` | 管理员账号 |
| `ADMIN_PASSWORD` | `password` | 管理员密码 |
| `GITHUB_CLIENT_ID` | - | GitHub OAuth App ID |
| `GITHUB_CLIENT_SECRET` | - | GitHub OAuth Secret |
| `GITHUB_REDIRECT_URI` | `http://localhost:8000/oauth/github/callback` | 回调地址 |
| `DB_TYPE` | `postgres` | 数据库类型 (postgres/sqlite) |
| `DATABASE_URL` | - | PostgreSQL 连接字符串 |

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

## Chrome 插件同步

1. 加载 `extension/` 目录为 Chrome 插件
2. 登录对应网站 (ChatGPT / Claude / etc.)
3. Cookie 自动同步到网关

## Docker Compose (生产环境)

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

## CI/CD

GitHub Actions 自动构建：
- `push to main` → 构建 Docker 镜像 → 推送到 GHCR
- `PR` → 运行测试 + Lint
- 镜像标签: `ghcr.io/lewellyn7/autodev-multiagent:latest`

## 项目结构

```
ai-gateway/
├── app/
│   ├── main.py          # FastAPI 主应用
│   ├── database.py      # 数据库操作
│   ├── middleware.py    # 中间件 (Rate Limiting)
│   └── templates/
│       ├── admin.html   # 管理后台 (Vue 3)
│       └── login.html   # 登录页面
├── extension/            # Chrome 插件
├── .github/workflows/     # CI/CD
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 技术栈

- **后端**: FastAPI + Uvicorn + Pydantic
- **数据库**: PostgreSQL / SQLite
- **前端**: Vue 3 + Tailwind CSS (CDN)
- **代理**: g4f (Google, Get Free ChatGPT)
- **容器**: Docker + Docker Compose

## License

MIT
