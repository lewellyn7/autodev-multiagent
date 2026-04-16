# 采集系统 - DevOps 与部署梳理

> 生成时间: 2026-04-16 17:50

## Docker 配置

### 服务架构 (docker-compose.prod.yml)

| 服务 | 镜像 | 端口 | 资源限制 |
|------|------|------|----------|
| redis | redis:7-alpine | 6381:6379 | 256MB |
| postgres | pgvector/pgvector:pg16 | 5435:5432 | 1GB |
| web | 自建 Dockerfile (runtime stage) | 8889:8000 | 2CPU/2GB |
| prometheus | prom/prometheus:v2.51.0 | 9090:9090 | 0.5CPU/512MB |
| grafana | grafana/grafana:10.4.0 | 3030:3000 | 0.5CPU/256MB |
| scheduler | 自建 Dockerfile (runtime stage) | - | 2CPU/2GB |

### 网络
- 独立 bridge 网络 `tender-net`

### 健康检查
- Redis: `redis-cli ping`
- PostgreSQL: `pg_isready`
- Web: `httpx.get('/health')`

### 日志
- JSON 文件日志，轮转 100MB，保留 5 个文件

## 监控方案

### Prometheus
- 配置文件: `monitoring/prometheus.yml`
- 规则目录: `monitoring/prometheus/rules`
- 保留期: 15 天
- 端口: 9090

### Grafana
- 端口: 3030
- 默认账号: admin / admin123
- 配置 provisioning: `monitoring/grafana/provisioning`

## 环境配置

关键环境变量：
- `DATABASE_URL` — PostgreSQL 连接字符串
- `REDIS_URL` — Redis 连接字符串
- `RAGFLOW_API_KEY` — RAGFlow API 密钥
- `RAGFLOW_MCP_URL` — RAGFlow MCP 服务
- `GRAFANA_PASSWORD` — Grafana 密码

## 部署流程

1. `docker compose -f docker-compose.prod.yml up -d --build`
2. 服务按依赖顺序启动（redis → postgres → web → scheduler）
3. healthcheck 通过后才启动下一个服务

## 已知问题

1. **Prometheus 配置问题导致重启循环** (MEMORY.md)
2. **Redis 密码硬编码** — `infini_rag_flow`
3. **PostgreSQL 密码硬编码** — `changeme_pg_password_2026`
4. **RAGFlow API Key 暴露** 在 docker-compose 中
5. **API Key 硬编码** — `ragflow-Z95CAjDHSyKZflHv6xMD6SXvmjdkSzCZCZK5BSyQcSw`

## 改进建议

1. 使用 .env 文件管理敏感配置（已在部分变量使用）
2. 清理 docker-compose 中的硬编码密钥
3. Prometheus 重启循环问题需排查 prometheus.yml 配置
4. 考虑使用 Docker secrets 管理数据库密码