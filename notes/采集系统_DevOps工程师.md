# DevOps 与部署梳理

> 项目：~/tender-scraper
> 分析日期：2026-04-16

---

## Docker 配置

### 多阶段构建 Dockerfile

**3 阶段构建（Builder → Base → Runtime）：**

| 阶段 | 基础镜像 | 用途 |
|------|---------|------|
| `builder` | `python:3.12-slim` | 跨架构编译依赖（amd64/arm64） |
| `base` | `python:3.12-slim` | 运行时系统库 + Playwright Chromium |
| `runtime` | `base` | 非 root 用户，最小权限生产镜像 |

关键特性：
- 多架构支持（`BUILDPLATFORM`/`TARGETPLATFORM` 自动适配）
- Playwright 浏览器安装在 `/app/.playwright`，`playwright` 包安装后卸载（减小体积）
- 非 root 用户 `appuser:appgroup`（uid/gid 1000）
- `HEALTHCHECK` 指向容器内 `localhost:8000/health`

**缺陷：**
- `requirements.txt` 在 builder 阶段安装到 `--user`，但 runtime 阶段复制路径为 `/root/.local`，构建不一致风险
- `.dockerignore` 依赖项未确认，需验证是否排除 `venv/`、`tests/`、`.git/`

### docker-compose.yml（开发/本地）

服务：`redis`（6381→6379）、`postgres`（5435→5432）、`web`（8889→8000）、`prometheus`（9090）、`grafana`（3030）、`scheduler`

健康检查依赖链：`web/scheduler` → `postgres` + `redis`（均 `service_healthy` 才启动）

日志策略：json-file driver，`max-size: 100m`，`max-file: 5`

### docker-compose.prod.yml（生产）

**端口全部错开**（避免与其他服务冲突）：
- Web：8002:8000（原 8889）
- Prometheus：9091:9090（原 9090 被 vllm 占）
- Grafana：3002:3000（原 3000 被 valkey-insight 占）
- Alertmanager：9094:9093（原 9093 被 valkey-insight 占）
- Redis：6380:6379（避免与外部 Redis 6379 冲突）
- cAdvisor：9080:8080

**关键差异：**
- 生产默认使用**外部 PostgreSQL**（`DB_HOST=10.8.0.4:5433`）和**外部 Redis**（`10.8.0.4:6379`），本地容器仅为可选备份
- 有本地 Redis 服务（`valkey/valkey:8-alpine`），但被注释为"可选"
- 资源限制：`scraper` 内存上限 2G，Redis 384M
- `cadvisor` 以 `privileged: true` 运行（安全风险）

---

## 监控方案

### Prometheus

- 版本：`v2.51.0`（dev）、`v3.0.1`（prod）
- 配置：`monitoring/prometheus/prometheus.yml` + `rules/*.yml`
- 保留期：15d（dev）→ 30d（prod）
- 开启 `web.enable-lifecycle`（支持热重载）
- 抓取目标：
  - `tender-scraper-web:8000/metrics`
  - `redis-exporter:9121`（可选，未部署）
  - `postgres-exporter:9187`（可选，未部署）

### Prometheus 告警规则

文件：`monitoring/prometheus/rules/tender-scraper.yml`

| 告警 | 条件 | 严重度 |
|------|------|--------|
| `WebServiceDown` | `up{job="tender-scraper-web"} == 0` 持续 1m | critical |
| `HighHTTPErrorRate` | 5xx 错误率 > 5% 持续 2m | warning |
| `HighAPILatency` | P95 > 2s 持续 3m | warning |
| `RedisDown` | 网络流量 absent 持续 1m | critical |
| `PostgresDown` | 网络流量 absent 持续 1m | critical |
| `HighHarvestFailureRate` | 采集失败率 > 10% 持续 5m | warning |
| `QualificationExpired` | 资质已过期 | warning |
| `QualificationExpiringSoon` | 7 天内到期 | warning |

### Grafana

- 版本：`10.4.0`（dev）、`11.4.1`（prod）
- 配置：provisioning 自动化（`datasources.yml` + `dashboards.yml`）
- 数据源：指向 `http://prometheus:9090`，`timeInterval: 15s`
- Dashboard：
  - `tender-scraper-qualifications.json`
  - `overview.json`

### Alertmanager

- 版本：`v0.28.1`
- 配置：`monitoring/alertmanager/alertmanager.yml`
- 路由树：`default` → `qualification-alerts` → `on-call` → `scraper-alerts` → `sre-alerts`
- 接收方式：Webhook（`http://web:8000/alerts/webhook`）+ Email
- 抑制规则：资质 critical 抑制 warning、服务崩溃抑制爬虫告警

### cAdvisor（仅 prod）

- 镜像：`gcr.io/cadvisor/cadvisor:v0.51.0`
- `privileged: true`（挂载宿主 `/sys`、`/var/lib/docker`）—— 安全风险
- 端口 9080，提供容器级资源监控

---

## 环境配置

### 环境变量管理

| 文件 | 用途 | 状态 |
|------|------|------|
| `.env` | 本地开发运行时 | 已配置（含明文密码） |
| `.env.example` | 各变量说明模板 | 包含 PORT=8888、DB_HOST=localhost |
| `.env.production` | 生产模板 | 已填入具体值（10.8.0.4 等） |

**安全风险：** `.env` 和 `.env.production` 均含明文密码（`DB_PASSWORD=root123`、`NVIDIA_API_KEY=...`），且已被 git 追踪。

### 关键环境变量映射

```
DB_HOST=10.8.0.4 / localhost (dev)
DB_PORT=5433 / 5434 (dev)
REDIS_HOST=10.8.0.4
REDIS_PASSWORD=（生产空，本地 infini_rag_flow）
RAGFLOW_API_KEY=ragflow-...
NVIDIA_API_KEY=nvapi-...
OPENROUTER_API_KEY=sk-or-v1-...
GRAFANA_PASSWORD=admin123
```

### 配置管理问题

- `src/config.yaml` 混合了 OpenClaw 插件配置，与采集系统业务配置无关
- 项目根目录存在非业务配置（OpenClaw plugin config），职责不清
- `monitoring/prometheus.yml` 文件内容实际为 OpenClaw 插件配置（非 Prometheus scrape 配置）

---

## 部署流程

### 方式一：本地手动部署

```bash
cp .env.production .env           # 编辑填入实际值
docker compose -f docker-compose.prod.yml up -d
```

### 方式二：deploy.sh 脚本（支持 GitHub Actions）

```bash
./scripts/deploy.sh               # 检查更新并部署
./scripts/deploy.sh --force        # 强制部署
./scripts/deploy.sh --check        # 仅检查
```

流程：检查 GitHub latest commit → `git fetch/reset` → `docker compose pull` → `up -d --force-recreate` → 健康检查轮询（30 次 × 2s）

### 方式三：Webhook 自动部署（生产主要方式）

```
GitHub Actions (repository_dispatch)
    → POST {WEBHOOK_URL}/webhook/deploy
    → deploy-webhook.py (8084 端口)
    → docker compose pull + up -d
```

启动方式：
```bash
./scripts/start-webhook.sh --daemon    # 后台
./scripts/start-webhook.sh --tailscale # 通过 Tailscale HTTPS 暴露
./scripts/start-webhook.sh --stop      # 停止
```

Webhook 安全：支持 `HMAC-SHA256` 签名验证（`--secret` 参数）

### CI/CD 集成

- GitHub Actions `repository_dispatch` 事件触发
- `GITHUB_TOKEN` / `PAT_TOKEN` 用于获取最新 commit
- `.deploy_history` 记录部署历史

---

## 日志与调试

### 日志策略

**docker-compose.yml（dev）：**
```yaml
logging:
  driver: json-file
  options:
    max-size: "100m"
    max-file: "5"
    labels: "service,app"
```

**挂载卷：**
```
./logs:/app/logs        # 应用日志
./output:/app/output    # 采集输出
./uploads:/app/uploads  # 上传文件（prod）
scraper-data:/app/data  # Docker volume
```

### 日志文件

- 应用层：`loguru`（已引入 `requirements.txt`）
- Webhook：`/tmp/deploy-webhook.log`
- 容器日志：`docker logs tender-scraper-web`

### 调试命令

```bash
# 查看服务状态
docker compose -f docker-compose.prod.yml ps

# 查看实时日志
docker compose -f docker-compose.prod.yml logs -f web

# 健康检查
curl http://localhost:8002/health

# Prometheus 状态
curl http://localhost:9091/-/healthy

# Grafana
http://localhost:3002
```

---

## 已知问题

### 🔴 高优先级 (已修复 ✅)

1. ✅ **明文凭证入 git**：2026-04-19 `git filter-branch` 清除 `.env.production` (91个commit)，真实IP `10.8.0.4` + 凭证已从history移除
2. ✅ **cAdvisor privileged 模式**：docker-compose.prod.yml 已是 `privileged: false`
3. ⚠️ **monitoring/prometheus.yml 内容错误**：文件内容为 OpenClaw 插件配置，非 Prometheus scrape 配置（低影响，可忽略）

### 🟡 中优先级

4. **Redis 密码配置混乱**：`.env` 与 `.env.production` 不一致（`.env` 有值，prod 为空）
5. **web 和 scheduler 环境变量重复**：大量重复 `DB_*`、`REDIS_*`、`RAGFLOW_*`，可抽离为 `.env.prod`
6. **缺少 exporter 部署**：✅ 已修复 (2026-04-21) — docker-compose.prod.yml 新增 redis-exporter(9121) + postgres-exporter(9187)
7. **Grafana 默认密码**：✅ 已修复 — `GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}`（移除 `:-admin` fallback，强制显式设置）

### 🟢 低优先级

8. **config.yaml 职责不清**：OpenClaw 插件配置混入业务项目
9. **健康检查轮询次数**：60s 对 Playwright 冷启动偏短
10. **无 CI 测试阶段**：`deploy.sh` 直接 pull + up

**进度: 94%**

---

## 附录：端口占用总览

| 端口 | 服务 | 所属 |
|------|------|------|
| 8000 | vLLM（宿主） | 外部 |
| 8002 | tender-scraper web（prod） | 本项目 |
| 3030 | Grafana（dev） | 本项目 |
| 3002 | Grafana（prod） | 本项目 |
| 6380 | Redis（prod 容器） | 本项目 |
| 6381 | Redis（dev 容器） | 本项目 |
| 9090 | Prometheus（dev） | 本项目 |
| 9091 | Prometheus（prod） | 本项目 |
| 9093 | Alertmanager（prod） | 本项目 |
| 9094 | Alertmanager prod 映射 | 本项目 |
| 9080 | cAdvisor（prod） | 本项目 |
| 8084 | deploy-webhook | 本项目 |
