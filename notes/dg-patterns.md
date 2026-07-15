# Deploy / Patterns (部署 / 模式归档)

> 本文档是 AGENTS.md 历史归档的部署/容器/PG/决策模式章节。当前生效的精简规则见 `AGENTS.md` Active Iron Rules。

---

## Docker 操作规范

### 重建 Web 容器（标准操作）

```bash
# 强制删旧容器 + 重建
docker stop tender-scraper-web 2>/dev/null
docker rm -f tender-scraper-web 2>/dev/null
docker rmi -f $(docker images -q tender-scraper-web 2>/dev/null) 2>/dev/null
cd ~/tender-scraper && docker compose up -d --build web
```

**原因：** `docker compose up -d --build` 对未改动层使用 CACHED，导致代码修改不生效。

### 别名

```bash
alias rebuild-web="cd ~/tender-scraper && docker stop \$WEB_SERVICE 2>/dev/null; docker rm -f \$WEB_SERVICE 2>/dev/null; docker rmi -f \$(docker images -q tender-scraper-web 2>/dev/null) 2>/dev/null; docker compose up -d --build web"
```

### Option B 部署（image 重建 + hot-replace）

```bash
# 1. 备份当前 image
docker tag tender-scraper-web:latest backup-pre-rebuild-$(date +%Y-%m-%d)

# 2. 重新构建
docker compose build web collector scheduler

# 3. force-recreate（不重启 redis/postgres）
docker compose up -d --no-deps --force-recreate web collector scheduler
```

**关键标志：**
- `--no-deps`：不动 redis/postgres volumes
- `--force-recreate`：不重用旧容器（避免 CACHED 层）

### docker compose up -d 副作用 (2026-06-28)

`docker compose up -d <service>` 会顺带 start 同文件的所有未运行 service（同 docker-compose.yml 里的 redis 也会被 start）。

**修复：**
1. `up -d --no-deps <service>`: 启动指定 service，不动依赖
2. 直接 `docker run`: 已知参数启动临时容器
3. 生产部署前：看 `docker-compose.yml` 里 service 的 image + 启动参数再决定

### Hot-deploy md5 对账 (核心规则)

任何 hot-deploy 必须对账 PR 所有 changed files，**不能"挑 deploy"**：

```bash
# 合并后立即跑
docker exec <container> sh -c "md5sum $(cat pr-changed-files.list | sed 's|^|/app/|') | sort"

# 每个文件 md5 必须 = git HEAD md5
# 主代理必须亲自抽查（不能只信子代理报告）
```

---

## PostgreSQL + psycopg2 开发笔记

### LIKE 'http%' + 双 % 转义 (2026-05-09)

psycopg2 用 `cursor.execute(sql, params)` 时，如果 SQL 含 `url LIKE 'http%'` 又有其他 `%s` 占位符，psycopg2 会将 `http%s` 误解为不完整格式说明符，导致 `IndexError: tuple index out of range`。

**修复：** 使用双 `%%` 转义 — `url LIKE 'http%%'` 告诉 psycopg2 将 `%%` 视为单个字面 `%`。

### `_convert_placeholders` 与 regex `?` 冲突

`_convert_placeholders()` 将所有 `?` 替换为 `%s`，如果 SQL 含 regex `?`（如 `url ~ '^https?://'`），这个 `?` 也会被替换。

**修复：** 用 `url LIKE 'http%%'` 或 `SUBSTRING(url, 1, 4) = 'http'` 替代 regex。

### PG/SQLite 双路径兼容

```python
# 任何 SQL 函数顶部必有此行
USE_PG = os.getenv("DB_TYPE", "sqlite").lower() == "pg"
placeholder = "%s" if USE_PG else "?"

# 然后所有 c.execute(sql, params) 都用 placeholder
c.execute(f"UPDATE tbl SET col = {placeholder} WHERE id = {placeholder}", (new_val, row_id))
```

**写函数必须 commit：**
```python
# SQLite 模式：c.commit() 自动写
# PG 模式：autocommit=False，必须手动 commit
c.execute(...)
c.commit()  # 缺这个 = 100% 静默丢数据
```

### Vector Library URL Schema 漂移 (2026-06-05)

**问题:** `/api/projects?keyword=xxx` 默认 `use_vector=true` 总是 0 行。

**根因：** 修复 UUID 字段后 project URL 格式从 `xxhz/.../date/uuid.html` 改为 `trade/catNum/uuid?categoryNum=xxx`，但 vector_store 表 metadata.url 还是旧格式（117 条）。

**API 层 fallback（`app/api/routes/projects.py:270-318`）：**
```python
# 检测与 project_url_set 的 overlap
project_url_set = {p.get("url", "") for p in projects}
vector_matched_urls = {u for u in raw_vec_urls if u in project_url_set}
vector_had_url_overlap = len(vector_matched_urls) > 0

# 若 attempted 但 overlap=0 → 回退简单匹配
if (vector_attempted and not vector_had_url_overlap) or vector_matched_urls is None:
    vector_matched_urls = None  # 关键：清空避免二次过滤
```

**数据层根治（`scripts/reindex_vector_store.py`）：**
- 清空 `vector_store` 表
- 重新拉取所有 `projects_cqggzy` 记录
- title+content_preview+full_content[:500] 构造文本
- `vs.upsert_documents(docs)` 重建
- 批大小 ≤10（vLLM 单批 >10 → 400 Bad Request）

---

## 项目决策记录

### CCGP 停采决策 (2026-06-02)

**状态：** 停采。`main.py` 中 `ENABLE_CCGP = False` 双重保险（创建条件 + 列表过滤 + 详情调度 None 检查）。

**原因：**
1. CCGP（重庆政府采购网）是 React SPA，URL 参数不生效，**无法指定日期范围**重采历史数据
2. 详情页 URL 提取依赖 `window.open` JS 拦截，稳定性差、IP 封禁率高
3. 服务端只保留 3 个月窗口，超过即不可重新发现
4. 唯一 58 条历史记录保留在 `projects_ccgp` 表中，不删

**重启用条件：** 需先完成 (1) 逆向 CCGP SPA 找到 XHR 端点 (2) 实现服务端日期过滤 (3) 验证反爬绕过

**联动文件：**
- `tender-scraper/main.py` — `ENABLE_CCGP` flag + None check
- `memory/2026-06-02.md` — 详细评估

### CQGGZY 节假日/周末无发布 (2026-06-23)

**经验：** CQGGZY 招标平台**只在工作日发布**（周末/节假日休市）。怀疑缺数据时**先看日历**：

| 日期 | 周几 | 类型 | 是否发布 |
|---|---|---|---|
| 6-06/07 | 六/日 | 周末 | ❌ |
| 6-13/14 | 六/日 | 周末 | ❌ |
| 6-19/20 | 五/六 | 端午 | ❌ |

**API 0 条 ≠ 数据丢失**：先看日历，再排查 API 限制（这是 6-23 才确认的，之前误以为是 API 历史窗口限制）。

### partial hot-deploy 容灾（2026-07-14）

PR #77 合并时 hot-deploy **只 deploy 了 1/4 文件**（commit 1 `cqggzy.py` + migration 007 SQL），**漏了 `db.py` commit 3+4 修复**。容器跑 7 天旧代码，前端 `/api/projects/latest` 静默返 `projects: []`。

**调用链：**
```
frontend /data → authFetch('/api/projects/latest?limit=1000') →
  /api/projects/latest → Database.get_latest_projects() →
    self._get_conn().conn  ← psycopg2 pool 关闭的 conn 在 _local 缓存
    → conn.execute(sql) 抛 "connection already closed" →
      except → logger.error + return [] →
        response {projects: [], total: 115025} →
          frontend mergeLatestItems → allItems=[] → 页面空
```

**silent-killer 特征：**
- `/api/health` 200 healthy
- `/api/projects` 200 + 完整 115025 条（不调 `get_latest_projects`）
- `/api/projects/latest` 200 + **空数组** ← silent fallback

**修复后规则：**
- 核心模块（db.py / settings.py / auth/* / migrations/*）修改必须 `docker cp` + `docker restart` + **5 次重复 smoke 验证**
- 容器内 md5 vs `git ls-files` 必须对账
- container image label 必须含 commit SHA（否则无法对比容器代码 vs git HEAD）
- 遇 "/api/xxx 正常但前端空" → 立即 `docker logs --since 5m | grep -E "ERROR|Traceback"` 必有 silent-fallback 抛错

---

## Hot-deploy 标准操作模板（sub-agent 必走）

```bash
# 1. 主代理派工时硬性要求
docker cp <file> <container>:/app/<file>
docker restart <container>
sleep 8

# 2. sub-agent 必须 attach 验证结果
docker exec <container> grep "关键改动" /app/<file>  # 文件已就位
curl <health_url>  # 端到端 5× smoke
docker logs --since 30s <container> | grep -E "ERROR|Traceback"  # 0 错

# 3. 主代理收到报告时必须亲自抽查 ≥1 个文件
# 不能只信 "测试通过"
```

**反例：** 子代理省略 `docker restart` 步骤 → 容器内仍是旧代码 → silent 6 天（PR #77 历史）。
