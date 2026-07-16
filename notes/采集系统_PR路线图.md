# 采集系统 PR 路线图 v2 (2026-06-11 07:42)

> **用户调整 (07:40)：** 不做 Caddy HTTP 模式 + 不做向量维度切换，重新评估
> **调整说明：**
> - 剔除：Caddy 相关 P0-1、P1-1
> - 替换：生产部署改用 **Nginx + certbot**（主机现有组件）
> - 剔除：维度切换相关建议（AI 文档同步）
> - 保留：HNSW 索引（**用现有 2560 维**，非切换）
>
> 编制时间：2026-06-11 07:42
>
> **用户决策 (2026-06-19)：** P0-1 Nginx + certbot **取消**
> - 原因：dev 端口 8889 走 Tailscale 内网足够；公网 HTTPS 部署非必要
> - 备选：Tailscale Funnel（暂不实施）
> - 决策记录：`memory/2026-06-19.md` 11:50

---

## 📋 主机环境预研（2026-06-11 07:41）

```
主机:        lewellyn (Tailscale: 100.67.207.69)
Web 反代:    /etc/nginx 存在 + certbot 已装
证书:        /usr/bin/certbot
Docker 网络: tender-scraper_tender-net (172.26.0.0/16)
目标:        8889 端口裸奔 → HTTPS + 反代 + 安全头
```

**为什么选 Nginx + certbot 而非 Caddy：**
1. 主机已装 Nginx + certbot（零新增依赖）
2. certbot 配合 Nginx 已有大量成熟 cron 自动续期
3. 项目文档已使用 Nginx 模式（早期评估）
4. Tailscale Serve 可选作内网 HTTPS（不暴露公网）

---

## 📋 PR 概览（4 个 P0 + 3 个 P1）

| # | PR | Owner | 类型 | 估时 | 风险 |
|---|----|-------|------|------|------|
| ~~**P0-1**~~ | ~~Nginx + certbot 反代 (替换 Caddy)~~ | ~~DevOps~~ | ~~加固~~ | ~~3h~~ | ❌ **已取消 (6-19)** |
| P0-2 | pgvector HNSW 索引 (2560 维) | AI 工程师 | 性能 | 2h | 🟢 低 |
| P0-3 | Startup 安全断言 | 安全工程师 | 加固 | 1h | 🟢 低 |
| P0-4 | main.py 拆分 run_collection_v2 | 后端架构师 | 重构 | 3h | 🟡 中 |
| P1-1 | RateLimit 重启 (team 模式) | 安全工程师 | 加固 | 2h | 🟢 低 |
| P1-2 | 采集器 health 探针 | DevOps | 可观测 | 1h | 🟢 低 |
| P1-3 | 向量去重 (similarity-based) | AI 工程师 | 新功能 | 4h | 🟡 中 |

---

## ❌ P0-1 Nginx + certbot 反代（已取消 2026-06-19）

> **状态：** ❌ 已取消（用户决策）
> **原因：** dev 端口 8889 走 Tailscale 内网足够；公网 HTTPS 部署非必要
> **方案稿保留：** `.pre-qual-feature/p0-1-cancel-2026-06-19/PR路线图.bak`（含完整 Nginx 配置 + certbot 流程，未来如需启用可一键复用）

<details>
<summary>📦 参考稿（已取消，仅供未来启用时复用）</summary>

### 方案选型

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **A. Nginx + certbot** | 主机已有，cron 自动续期 | 配置文件手动写 | ⭐⭐⭐ |
| B. Nginx 容器 | 与项目隔离 | 多一层网络 | ⭐⭐ |
| C. Tailscale Serve | 5 行配置，零依赖 | 仅 Tailscale 内网访问 | ⭐⭐ (内网场景) |
| ~~D. Caddy~~ | ~~自动 HTTPS~~ | ~~用户排除~~ | ❌ |

**推荐 A 方案**：Tailscale 内网也走 A（绑主机名）

### 文件改动
```
新增  /etc/nginx/sites-available/tender-scraper
新增  /etc/nginx/snippets/tender-scraper-headers.conf
修改  /etc/nginx/nginx.conf               # 包含 sites-enabled
修改  /etc/cron.d/certbot-renew           # 已有，确认 cron
新增  scripts/check_nginx_health.sh       # 端到端健康检查
修改  .env                                # 添加 EXTERNAL_URL=https://...
```

### Nginx 配置模板
```nginx
# /etc/nginx/sites-available/tender-scraper
upstream tender_scraper_backend {
    server 127.0.0.1:8889;  # 当前 dev 端口
    # server tender-scraper-web:8000;  # 容器内网 IP（需 tender-net）
}

server {
    listen 443 ssl http2;
    server_name tender.lewellyn.com;

    # SSL 由 certbot 管理
    ssl_certificate     /etc/letsencrypt/live/tender.lewellyn.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tender.lewellyn.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    include /etc/nginx/snippets/tender-scraper-headers.conf;

    location / {
        proxy_pass http://tender_scraper_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}

server {
    listen 80;
    server_name tender.lewellyn.com;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}
```

### 安全头配置
```nginx
# /etc/nginx/snippets/tender-scraper-headers.conf
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "no-referrer" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'" always;
```

### 风险评估
- 🟢 低：Nginx + certbot 是成熟方案
- 风险：证书签发需 80 端口可达，dev 阶段可走 certbot --staging
- 回滚：`rm /etc/nginx/sites-enabled/tender-scraper && nginx -s reload`

### 验证步骤
1. `sudo certbot --nginx -d tender.lewellyn.com --staging` 测试签发
2. `nginx -t && sudo nginx -s reload`
3. `curl -I https://tender.lewellyn.com/health` 返回 200
4. `curl -I http://tender.lewellyn.com` 返回 301
5. SSL Labs 扫描（可选）
6. `certbot renew --dry-run` 验证自动续期

### 依赖前置
- DNS: `tender.lewellyn.com → 主机公网 IP`（或 Tailscale MagicDNS）
- 80/443 端口空闲

### 估时
3h（撰写配置 1h + 申请证书 0.5h + 集成测试 1h + 文档 0.5h）

</details>

---

## 🟢 P0-2 pgvector HNSW 索引（保留 2560 维）

**Owner:** AI 工程师
**目标:** 给 vector_store 表加 HNSW 索引，**保持现有 2560 维不变**

### 背景
- vLLM 当前只支持 `Qwen/Qwen3-Embedding-4B`（4B 参数，**2560 维**）
- **不做切维度**：保留现有模型（切维度需启新服务，超出本 PR 范围）
- HNSW 支持任意维度（IVFFlat ≤2000 维不能用）
- 内存预估：14K × 2560 × 4B = ~140MB

### 文件改动
```
新增  scripts/create_hnsw_index.sql       # CREATE INDEX ... USING hnsw
新增  scripts/reindex_pgvector_hnsw.sh    # 在线创建（CONCURRENTLY）
修改  scripts/init_vectors.sql            # 集成到 init 脚本
修改  app/services/vector_store.py        # search() 用 HNSW（无需改）
```

### SQL 模板
```sql
-- 在线创建（不锁表）
CREATE INDEX CONCURRENTLY vector_store_hnsw_idx
ON vector_store USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 调整查询参数
SET hnsw.ef_search = 100;  -- 默认 40，越大越精确
```

### 风险评估
- 🟢 低：HNSW 是 PostgreSQL pgvector 0.5+ 标准索引
- 风险：构建期间 CPU 占用高（建议业务低峰 14:00 / 18:00 之间）
- 回滚：`DROP INDEX vector_store_hnsw_idx;`

### 验证步骤
```sql
-- 索引创建成功
\d vector_store
-- 期望看到: "vector_store_hnsw_idx" "hnsw" (embedding vector_cosine_ops)

-- 性能对比
EXPLAIN ANALYZE SELECT ... FROM vector_store
ORDER BY embedding <=> '[...]'::vector LIMIT 10;
-- 期望：Index Scan using vector_store_hnsw_idx
```

### 估时
2h（SQL 验证 0.5h + 应用层集成 0.5h + 灰度 1h）

### 已剔除的"切维度"建议
~~降维到 1536 (OpenAI) / 1024 (Qwen3-Embedding-0.6B) / 512 (m3e-small)~~
原因：用户明确不做维度切换。如未来需要切维度，独立起 spike。

---

## 🟢 P0-3 Startup 安全断言

**Owner:** 安全工程师
**目标:** production 环境禁止 self 模式启动

### 文件改动
```
修改  config/settings.py                   # 添加 ENVIRONMENT 字段
修改  web_server.py / main.py              # startup 断言
新增  app/core/safety_guard.py             # 启动检查装饰器
```

### 实现模板
```python
# config/settings.py
class Settings(BaseSettings):
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEPLOYMENT_MODE: Literal["self", "team"] = "self"

# app/core/safety_guard.py
def check_production_safety():
    if settings.ENVIRONMENT == "production" and settings.DEPLOYMENT_MODE == "self":
        raise RuntimeError(
            "DEPLOYMENT_MODE=self is FORBIDDEN in production. "
            "Set DEPLOYMENT_MODE=team and configure authentication."
        )

# web_server.py / main.py
if __name__ == "__main__":
    check_production_safety()
    main()
```

### 风险评估
- 🟢 低：纯加防御，dev 环境不受影响
- 误启动：env 没设 ENVIRONMENT 时不触发（默认 development）

### 验证步骤
1. dev 环境启动正常
2. `ENVIRONMENT=production DEPLOYMENT_MODE=self python main.py` → 抛 RuntimeError
3. `ENVIRONMENT=production DEPLOYMENT_MODE=team` → 正常启动

### 估时
1h

---

## 🟡 P0-4 main.py 拆分 (run_collection_v2)

**Owner:** 后端架构师
**目标:** 把 551 行 main.py 拆为模块化结构

### 当前问题
- main.py 含 5 大职责：采集/调度/向量化/导出/统计
- 单文件 86% 增长（296→551 行）
- 模块边界清晰：
  - `_build_vector_text` (40-58)
  - `_upsert_to_vector_store` (59-86)
  - `_build_crawl_task` (86-118)
  - `run_collection` (118-537)
  - `main` (537+)

### 文件改动
```
新增  app/core/harvest/pipeline.py         # run_collection_v2
新增  app/core/harvest/vectorize.py       # _build_vector_text / _upsert
新增  app/core/harvest/scheduler.py       # _build_crawl_task
修改  main.py                              # 改为入口 stub
```

### 拆分边界
```python
# app/core/harvest/pipeline.py
async def run_collection_v2() -> dict:
    """v2 入口：列表采集 → 详情采集 → 向量化 → 写 DB"""
    items = await fetch_lists()
    projects = await fetch_details(items)
    await vectorize_projects(projects)
    return await save_to_db(projects)

# main.py
from app.core.harvest.pipeline import run_collection_v2
# 仅保留 main() 调用 + ENABLE_CCGP 配置
```

### 风险评估
- 🟡 中：影响采集主流程，需逐项端到端验证
- 缓解：保留 main.py 旧 run_collection 7 天，参数切换
- 回滚：git revert + 重启容器

### 验证步骤
1. 端到端测试：触发采集 → DB 写入 → 向量入库
2. 24h 漏采回放验证
3. 来源均衡采样验证
4. 容器重启 → 数据落库

### 估时
3h（拆分 1.5h + 集成测试 1h + 灰度 0.5h）

---

## 🟢 P1-1 RateLimit 重启 (team 模式)

**Owner:** 安全工程师
**依赖:** P0-3
**目标:** team 模式强制 RateLimitMiddleware

### 文件改动
```
修改  app/middleware/security.py
修改  web_server.py
```

### 验证步骤
```bash
# 60s 内 100 次 /api/projects
ab -n 100 -c 10 https://tender.lewellyn.com/api/projects
# 期望：429 Too Many Requests
```

### 估时
2h

---

## 🟢 P1-2 采集器 health 探针

**Owner:** DevOps 工程师
**目标:** collector 容器暴露 /health 端点

### 文件改动
```
修改  main.py / pipeline.py              # 末尾加 _health_server
修改  docker-compose.yml                 # collector 加 healthcheck
修改  docker-compose.prod.yml
```

### 实现模板
```python
# main.py 末尾
from aiohttp import web
async def health(request):
    return web.json_response({
        "status": "ok",
        "last_crawl": _last_crawl_time.isoformat() if _last_crawl_time else None,
        "queue_size": scheduler.queue_size() if scheduler else 0,
    })

app = web.Application()
app.router.add_get("/health", health)
web.run_app(app, host="0.0.0.0", port=8001)
```

### 估时
1h

---

## 🟡 P1-3 向量去重 (similarity-based)

**Owner:** AI 工程师
**目标:** 用 embedding 相似度 > 0.95 判定重复项目
**约束:** 使用现有 2560 维 + HNSW 索引

### 文件改动
```
新增  app/services/dedupe.py              # SimilarityDedupe 类
修改  main.py / pipeline.py               # 采集完成后调用
新增  scripts/eval_dedupe_precision.py    # 精度评估
```

### 设计要点
- 同一标题/项目编号的近义变体
- URL 域名变更（http→https、参数差异）
- 阈值 0.95 起步，根据评估调整

### 估时
4h（设计 1.5h + 实现 1.5h + 评估 1h）

---

## 🎯 推荐执行顺序（v2）

```
Week 1 (本次):
  P0-3 (1h)  ─┐
  P0-2 (2h)  ─┼─ 并行，无依赖
  P1-2 (1h)  ─┘
        ↓
  ~~P0-1 (3h)~~  ←  ~~依赖 DNS + 80 端口~~ → **已取消 (6-19)**
        ↓
  P0-4 (3h)  ←  重构，需灰度

Week 2:
  P1-1 (2h)  ←  依赖 P0-3

Week 3+:
  P1-3 (4h)  ←  需先评估精度
```

**总估时：Week 1 11h，Week 2 2h，Week 3+ 4h**

---

## 📊 风险矩阵

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| certbot 申请失败 | 高 | 中 | staging 测试 + 80 端口验证 |
| HNSW 构建占 CPU | 中 | 低 | 业务低峰 + CONCURRENTLY |
| main.py 拆分回归 | 高 | 中 | 双版本并行 7 天 |
| self 模式误启动 | 高 | 低 | startup 断言 |

---

## ❌ 已剔除（用户要求）

| 原 PR | 剔除原因 | 替代方案 |
|-------|---------|---------|
| P0-1 Caddy + compose | 用户明确不做 Caddy | ~~Nginx + certbot (主机现有)~~ → **6-19 整体取消** |
| P1-1 Caddy HTTPS 自动续期 | 同上 | certbot cron 续期（已成熟） |
| 切维度 spike (2560→1536) | 用户明确不做 | HNSW 索引（用现有维度） |

---

## 📝 审核检查清单（提交前）

按用户 AGENTS.md 铁律"先审核 → 后备份 → 再执行"：

- [ ] 每个 PR 单独分支
- [ ] dirty state 已 `git stash` 或建 WIP commit
- [ ] 关键文件 `.orig` 快照
- [ ] commit message 用中文，描述 why
- [ ] 单测 + 端到端 curl 验证
- [ ] 推分支到 origin
- [ ] 出 PR 让用户 review
- [ ] **不主动合并到 main**

---

## 🔗 关联资源

- 主项目: `/home/lewellyn/tender-scraper`
- 主机: `100.67.207.69` (Tailscale)
- Web 反代: **无需公网反代**（dev 端口 8889 + Tailscale 内网；公网 HTTPS 走 Tailscale Funnel 待评估）
- 容器网络: `tender-net` (172.26.0.0/16)
- 监控: Prometheus 9090 + Grafana 3030
- 当前后台: 回填 10/20 段进行中（无冲突）
