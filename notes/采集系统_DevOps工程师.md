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

### ✅ 已完成 (2026-04-22)
- **Redis 密码配置统一**: `.env` 更新为 `CHANGE_ME_redis_password`（与 docker-compose.yml secrets 一致），重启后 `REDIS_URL` 环境变量生效，Redis Ping ✅
- ⚠️ **注意**: `.env` 中密码已从 `YOUR_REDIS_PASSWORD_HERE` 更新为真实占位值，容器启动后环境变量正确注入
- **Docker Secrets 生产配置** (1fa1cad)
  - `secrets/` 目录（已 gitignore）：8 个 secret 占位文件
  - `secrets/.env`：env_file 格式
  - `secrets/README.md`：创建说明
  - `docker-compose.prod.yml`：top-level `secrets:` + 所有服务添加 `env_file`
  - 修复 `postgres-data` volume 缺失
- **Settings 页面信息架构** (b183ddb): 11 tab → 5 分组 (采集/数据/AI/系统/账户)
- **移动端表格适配** (b183ddb): 固定列宽 + truncate

**进度: 98%**

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

---

## 2026-06-11 07:30 重新评估

> 距 2026-04-24 收尾 48 天。**部署架构基本未变，DevOps 工作集中在数据回填脚本工程化**。

### 🟢 容器运行现状（healthy）

```
tender-scraper-collector: Up 9 hours (healthy)   # 采集 worker
tender-scraper-web:       Up 9 hours (healthy)   # Web API
tender-scraper-scheduler: Up 2 days (healthy)    # APScheduler
tender-scraper-redis:     Up 2 days (healthy)    # 缓存
tender-scraper-postgres:  Up 2 days (healthy)    # 主 DB + pgvector
tender-scraper-prometheus: Up 2 days              # 监控
tender-scraper-grafana:   Up 2 days               # 看板
```

**调度实际触发（来自 scheduler 日志）：**
- 每 2 小时一次：08/10/12/14/16/18/20 点（08:00 / 12:00 / 18:00 三段 cron + 中间补触发）
- 实际间隔：2h（不是 cron 配的 4h）
- Redis Pub/Sub 触发，collector worker 订阅

### 📊 端口占用（当前）

| 服务 | 容器→宿主 | 备注 |
|------|----------|------|
| Web | 8000→**8889** | 实际外部访问端口 |
| PostgreSQL | 5432→**5435** | pgvector 16 |
| Redis | 6379→**6381** | password: CHANGE_ME_redis_password |
| Prometheus | 9090 (内部) | 未对外暴露 |
| Grafana | 3000 (内部) | 未对外暴露 |

**注意：** docker-compose.yml 中端口映射与 4-24 收尾时一致。但实际外部访问仍走 dev 配置（8889），未启用 prod 配置（8002）。

### 📦 部署/部署方式现状

**当前使用：**
- `docker compose up` (开发模式，8889/6381/5435)
- APScheduler + Redis Pub/Sub 解耦调度
- 无 production docker-compose.prod.yml 启用证据（端口未用 8002）
- 无 GitHub Actions 自动部署（webhook 服务未运行）
- deploy.sh + start-webhook.sh 存在但未启用

### 🔧 DevOps 工程师重大工作（5-11 以来）

**1. 数据回填脚本工程化（8+ 个一次性脚本）**

| 脚本 | 行数 | 用途 | 状态 |
|------|------|------|------|
| `scripts/backfill_segment.py` | - | 单段 CQGGZY 列表+详情回填 | ✅ 跑中（10/20 段） |
| `scripts/run_backfill_2024_2026.sh` | - | 20 段启动器（master PID 45197） | ✅ 跑中 |
| `scripts/reprocess_pno_from_h1.py` | 5824B | Nuxt SSR 抓取 H1 项目编号 | ✅ 一次性 86.7% 命中 |
| `scripts/fix_cqggzy_urls.py` | - | 修复错误 URL 格式 | ✅ 完成 |
| `scripts/fix_deadlines.py` + v2 | - | 截止日期回填 | ✅ 完成 |
| `scripts/fix_info_type.py` | - | info_type 修正 | ✅ 完成 |
| `scripts/reprocess_014005.py` | - | 014005 数字 ID 重处理 | ✅ 完成 |
| `scripts/strip_title_dup_history.py` | - | 清除 content_preview 开头 title | ✅ 完成 |
| `scripts/reindex_vector_store.py` | - | 向量库重建（11K doc × 7 词） | ✅ 完成 |

**2. CI 改进（chore）**
- `.dockerignore` 增加 `*.orig` / `*.bak` 规则（9cf2082）
- `gitignore` 排除 `backup_*.tsv/csv/sql` 与 `*.orig` 临时文件（2aef251）
- 停止 git 追踪 `output/latest.json`（17a687b）

**3. .dockerignore 验证**
- 已排除 venv/、tests/、.git/、*.orig、*.bak
- 多阶段构建路径已对齐（/root/.local → /home/appuser/.local 风险待验证）

### 🟡 待完善/风险

1. **生产部署未启用**：端口仍走 dev 8889，无 certbot/HTTPS，无 Caddy/Nginx 反代
2. **deploy.sh + webhook 服务未运行**：webhook 8084 端口未监听
3. **监控告警无验证**：8 条 Prometheus 告警规则定义完整，但未确认 Alertmanager 当前状态
4. **采集器 health 探针缺失**：collector 容器无 /health 端点暴露
5. **.env 仍含明文**：DB_PASSWORD=***（虽在 .gitignore，但本地文件存在）
6. **Redis 端口 6381 安全**：直接暴露宿主，无防火墙限制
7. **PostgreSQL 端口 5435 安全**：同上

### 📈 进度

- 4-24 收尾：98% ✅
- **5-11 以来：架构稳定，主要工作从基础设施转向数据工程**
- **6-11 当前：基础设施层 100% 稳定，新增需求集中在数据质量与回填**

### 🎯 建议下阶段 DevOps 任务

1. **启用 production 部署**：写 Caddyfile + docker-compose.prod.yml
2. **部署 certbot 自动续期**
3. **告警规则验证**：手动触发 WebServiceDown 测试 Alertmanager
4. **采集器加 health 探针**：每 30s 暴露任务积压量
5. **回填脚本收敛**：将 8+ 一次性脚本统一为 `scripts/oneoff/` 目录 + README

### 🔄 端口对照（生产 vs 当前）

```
生产 (prod compose):     当前 (dev compose):
  Web     8002            8889
  Redis   6380            6381
  PG      5433            5435
  Prom    9091            9090
  Grafana 3002            3000
  Cadvisor 9080           N/A
  Alertmgr 9094           N/A
  Webhook 8084            N/A
```

**当前实际只用 dev 一套**，prod compose.yml 存在但未启用。

---

## 2026-06-16 12:30 重新评估

> 距 6-11 评估 +5 天。**P1-2 health 探针上线，端口仍 8889，prod compose 未启**。

### 🟢 重大进展

**1. P1-2 采集器 health 探针（PR #16 MERGED + 部署）**
- 8001 端口：`/health` 端点 + docker healthcheck 接入
- 验证：collector 容器 up 50+ min healthy
- 价值：scheduler 触发 → collector 任务执行健康可见

**2. 阶段 1 部署收尾**
- web 容器：up 4+ hours (healthy)，3 次 rebuild（含 P0-3 漏配修复）
- collector 容器：up 50+ min (healthy, P0-4 hotfix 3 验证通过)
- scheduler 容器：up 6 days
- 5/5 核心容器 healthy

**3. 灰度监控（6-15 19:46 起 24h）**
- 20:00 周期 16 min 完成（255/255 详情成功，PG 552 条写入）
- 0 异常中断
- 行为兼容 100%（PURE LIFT 拆分后验证）

### 🟡 新发现风险

**1. cp "无内容" 大规模重抓需求（10,782 条）**
- 范围：工程招投标 + 招标计划 + publish_date < 2026-03-13
- spike 验证结果（6-15 20:21）：
  - `date=all` 参数 ❌ 不存在（API 忽略，返 0）
  - 需 `categorynum=014001019` (招标计划) + `sdt/edt` 自由范围
  - API 总共 18,386 条，DB 当年漏采 7,604 条
  - 详情 HTML 表格正文可用 regex 解析 `<td>`
- 三个方案待拍板：🅰️ 完整 fetch (3h) / 🅱️ 简化回填 (5min) / 🅲️ 混合 (先 1000 试)

**2. Bad Nuxt URL 修复脚本（working tree 未跟踪）**
- `scripts/fix_bad_nuxt_urls.py` (v3)
- `scripts/fix_9_unmatched.py`
- `scripts/restore_deleted.py`
- 备份：`.pre-qual-feature/bad-nuxt-url-fix-2026-06-15/` 之外

**3. publish_date 修复脚本（working tree 未跟踪）**
- `scripts/fix_publish_date.py` (一次性回填 233 条)
- 备份表：`_publish_date_backup`

### ❌ 已取消（用户决策 2026-06-19）

1. **P0-1 Nginx + certbot** — 取消
   - 原因：dev 模式部署足够（端口 8889 直接走 Tailscale 内网），公网 HTTPS 部署非必要
   - 替代：若需公网访问，统一走 Tailscale Funnel（暂不实施）
   - 决策记录：`memory/2026-06-19.md` 11:50

### 🟡 仍待办

1. **回填脚本收敛** — 8+ 一次性脚本统一为 `scripts/oneoff/` + README（之前建议未实施）
2. **CI 测试阶段** — `deploy.sh` 直接 pull + up，无 pytest 步骤
3. **告警规则验证** — 8 条 Prometheus 告警规则未手动测试
4. **采集器 health 探针已加**（✅ P1-2 完成）

### 📊 端口与容器现状

| 容器 | 状态 | 端口 | 备注 |
|------|------|------|------|
| tender-scraper-web | Up 4+ hours | 8889:8000 | dev compose |
| tender-scraper-collector | Up 50+ min | 探针 8001 | P1-2 完成 |
| tender-scraper-scheduler | Up 6 days | - | APScheduler |
| tender-scraper-redis | Up 2 days | 6381:6379 | CHANGE_ME_redis_password |
| tender-scraper-postgres | Up 2 days | 5435:5432 | pgvector + halfvec |
| tender-scraper-prometheus | Up 2 days | 内部 | 未对外 |
| tender-scraper-grafana | Up 2 days | 内部 | 未对外 |

**prod compose（8002/6380/5433）仍未启用**。

### 📈 进度

- 6-11 评估：100% ✅
- 6-16 当前：P1-2 完成 + 阶段 1 部署稳定；P0-1 阻塞中
- **6-19 当前：P0-1 已取消（用户决策），全部阻塞项清零 ✅**
