
## 2026-07-15 — minimax 模型 context window (官方 docs verified 22:10)

- **minimax/MiniMax-M3**: **1,000,000 tokens** (1M context, max output 512K, MSA sparse attention)
  - 来源: <https://platform.minimax.io/docs/guides/text-generation>
  - 来源: <https://www.minimax.io/blog/minimax-m3> (2026-05-31 发布)
- **minimax/MiniMax-M2.7**: **204,800 tokens** (204.8K)
  - 来源: MiniMax API docs + cline PR #10007 (formerly 192K, corrected)
- `session_status` 显示的 `205k` ≈ **M2.7 上限**，**不是** M3 硬限 (M3 是 1M, 5× 高于 205k)
- 修正前 silent knowledge bug 第二次: 我拍脑袋假设 = 205k (实际 M3 = 1M)
  - 19:59 user 直告 "> 205k" → 我信但没追真值
  - 22:09 user 强制查 docs → 揭示 1M (差 ~5×)
- AGENTS.md 上下文管理 / lesson 13 已用真实数字 + source URL 替换
- 教训: 任何"X 模型 = Y tokens" 拍脑袋前先 docs / `models list` / 问 user

---

## 2026-07-15 — minimax context window 修正 (user 直告 19:59)

- **事实:** `minimax/MiniMax-M3` 和 `M2.7` 实际 context **> 205k**, 远超此
- **`session_status` 报 `Context: 28k/205k (14%)` 是 OpenClaw runtime 显示上限, 不是模型真硬限**
- **含义 (修正):
  - /compact 阈值 "50% of 205k = 102k" 实际永远到不了模型硬限
  - 我看到的 "28k → 21k → 28k" compaction 是 OpenClaw runtime session 历史滚动策略, **不是** 模型 context 真满
  - 当 "Context %" 看着高但模型仍正常工作 → 是 runtime 清缓存, 不是真断档
  - 后续不应再以 "X % of 205k" 拍脑袋算阈值
- **教训:** runtime 显示分母 ≠ 模型 API 真硬限。要查真硬限 → docs / `models list` / 问 user

## 双模式切换系统 (2026-04-21)

### 功能
- 自用模式 (`DEPLOYMENT_MODE=self`): 免登录，自动 admin 用户
- 团队模式 (`DEPLOYMENT_MODE=team`): 完整认证和用户管理

### 核心文件
- `app/config/settings.py` — DEPLOYMENT_MODE 配置
- `app/api/dependencies.py` — 认证依赖
- `app/api/routes_users.py` — 用户路由适配
- `app/api/routes/system.py` — 模式切换 API
- `web_server.py` — 启动时初始化 admin 用户
- `app/templates/login.html` — 自用模式自动登录

### MiniMax 多模态服务
- `app/services/minimax_service.py` — 图片理解/生成、歌词/音乐生成


## 2026-05-11 — CCGP DB集成 + 日期修复 + SmartScheduler修复

### 完成
1. **CCGP DB持久化** ✅
   - `ccgp.py`: 重写DB写入块，使用`upsert_projects_ccgp([row])`格式
   - `db.py`: 新增`upsert_projects_ccgp()`方法（mirrors `upsert_projects`）
   - `main.py`: CCGP采集器集成到主流程（5路并行：3路CCGP + 2路CQGGZY）
   - 修复CCGP `LIST_URLS`为`/info-notice/{type}-list`格式
   - 修复`crawler_fn`根据`task.source`选择正确的采集器

2. **CQGGZY `publish_date`修复** ✅
   - 已通过SQL从URL路径批量回填：`UPDATE projects_cqggzy SET publish_date = MAKE_DATE(...) WHERE url ~ '/[0-9]{8}/'`
   - 结果：902/903 条有日期（仅1条来自外部URL无日期）
   - 采集器新增`_extract_date_from_url()`作为fallback

3. **SmartScheduler skip逻辑修复** ✅
   - `smart_scheduler.py`: 跳过任务时重新入队而非丢弃（`await self._queue.put((priority, task_id))`）
   - 修复后CCGP详情页能被处理（之前被永久跳过）

4. **详情页采集器路由修复** ✅
   - `crawler_fn`中根据`task.source`选择`ccgp_crawler`或`crawler`

5. **来源均衡采样** ✅
   - `main.py`: 按来源（cqggzy/ccgp）均衡选择detail_items，避免CCGP全被CQGGZY挤占

6. **`projects_ccgp`已有5条记录** ✅
   - info_type=结果公告, publish_date=2026-05-11

### 待处理
1. **CQGGZY `_fetch_detail_page` bug**: `name 'title' is not defined` — 出现在line 142的日志语句，但tender.title有默认值""不会触发。疑似旧代码残留或__enter__/__exit__问题，需下一轮调试
2. **CCGP采集意向=0**: `/info-notice/intention-list`返回0条，可能需要换URL或增加分页
3. **API stale cache**: web容器重启后应清除，但需验证新数据是否正确返回
4. **`renderTable()`需验证**: data.html的renderTable/renderCards函数已检查，未发现明显bug

### 关键配置
- 外部访问端口: **8889**
- Redis: `6381:6379` (password: `CHANGE_ME_redis_password`)
- 采集器容器: `tender-scraper-collector`
- Web容器: `tender-scraper-web`

### 文件变更
- `main.py`: CCGP集成、来源均衡采样、detail_limit=30、crawler_fn路由
- `app/crawlers/ccgp.py`: LIST_URLS修复、upsert_projects_ccgp调用、traceback日志
- `app/core/harvest/smart_scheduler.py`: skip重入队修复
- `app/database/db.py`: upsert_projects_ccgp方法

---

## 2026-05-11 下午 — API验证 + 数据确认

### API 状态 ✅
- `curl http://localhost:8889/api/projects` 返回数据（无 auth）
- 包含 CQGGZY（完整 content_preview）+ CCGP（5条，内容为空）两种来源
- CCGP 项目详情采集因 `name 'title' is not defined` bug 失败，但基础字段（title、publish_date、url）正确写入

### data.html 页面
- `/data` 返回 200，页面正常

### 关键发现：CCGP 详情采集 bug
- `cqggzy.py` 和 `ccgp.py` 都报 `name 'title' is not defined`
- 只影响详情页 content 提取，不影响基础字段（title、date、url）
- CCGP upsert 成功（5条已写入 projects_ccgp）
- 根因未明，可能是 `__enter__`/`__exit__` 或闭包问题

### 待确认
- `/data` 页面实际渲染效果（需截图）
- 工程招投标 title 问题（从 API 看标题正常）

## 2026-06-20 — 中标分析按项目类型分组排序 (PR #28 + #29)

### 完成
1. **数据 ETL (PR #28)**:
   - `config/project_types.py` — 词典独立配置 (8 类型 + priority)
   - `bid_parser.classify_project_type(title, content)` — 多标签分类
   - migration `002_add_project_types.sql` — `bid_results.project_types TEXT[]` + GIN 索引
   - `scripts/backfill_project_types.py` — 增量回填脚本 (无重解析)
2. **UI + API (PR #29)**:
   - `/api/analysis/bid-rank?project_type=...` 过滤
   - 新端点 `/api/analysis/bid-rank-by-type` 按类型分组的 Top N
   - analytics.html chip + 排序下拉
3. **测试**: 69/69 单测 (51 bid_parser + 18 analysis)

### 用户后续操作 (无须 PR)
```bash
# 1. 合并 PR #28 → PR #29 (顺序)
# 2. 生产部署:
psql $DATABASE_URL -f app/database/migrations/002_add_project_types.sql
python3 scripts/backfill_project_types.py
docker restart tender-scraper-web
# 3. 词典独立编辑:
vim config/project_types.py  # 加关键词
# 4. 增量回填:
python3 scripts/backfill_project_types.py  # 全量 ~30-60s
```

### 关键文件
- 代码: `app/utils/bid_parser.py` / `app/api/routes/analysis.py` / `app/templates/analytics.html`
- 词典: `config/project_types.py`
- 备份: `.pre-qual-feature/bid-type-2026-06-20/` (5 源文件)
- 分支: `feat/bid-analysis-by-type-etl` / `feat/bid-analysis-by-type-ui`
- PR: #28 (ETL) / #29 (UI)

## Promoted From Short-Term Memory (2026-07-13)

<!-- openclaw-memory-promotion:memory:memory/2026-07-06.md:43:45 -->
- 执行 (AGENTS.md 铁律 4 步全走): `af0f52b`: API + 注册 (ccgp_intent.py + pages.py + __init__.py) — +228 行; `7b2edb7`: UI (ccgp_intent.html + base.html nav) — +350 行; 累计: 5 个文件, +578/-0 [score=0.834 recalls=0 avg=0.620 source=memory/2026-07-06.md:43-45]
<!-- openclaw-memory-promotion:memory:memory/2026-07-06.md:48:51 -->
- 执行 (AGENTS.md 铁律 4 步全走): ✓ `/api/ccgp_intent/health` → 1195 条, 1000 意向 + 195 调查; ✓ `/api/ccgp_intent/stats` → by_info_type + by_date (30 天) + range; ✓ `?info_type=采购意向` → total=1000; ✓ `?info_type=需求调查` → total=195 [score=0.834 recalls=0 avg=0.620 source=memory/2026-07-06.md:48-51]
<!-- openclaw-memory-promotion:memory:memory/2026-07-06.md:52:55 -->
- 执行 (AGENTS.md 铁律 4 步全走): ✓ `?keyword=智能` → 43 条匹配; ✓ `?page=2&page_size=10` → 分页 has_more 正确; ✓ `/ccgp-intent` HTML → HTTP 200, 45K, 12ms; ✓ 容器 hot-deploy: 3 文件 md5 本地=容器, 刷新即用 [score=0.834 recalls=0 avg=0.620 source=memory/2026-07-06.md:52-55]
<!-- openclaw-memory-promotion:memory:memory/2026-07-06.md:47:47 -->
- 执行 (AGENTS.md 铁律 4 步全走): **验证** (端到端 7/7 通过) [score=0.824 recalls=0 avg=0.620 source=memory/2026-07-06.md:47-47]
<!-- openclaw-memory-promotion:memory:memory/2026-07-07.md:36:38 -->
- 9:42 用户 "检查触发失败的原因" — 诊断 5 root cause: `41915c0` (chore p3 季度清理) 误删 import，但留下 line 238 调用 — pyflakes/ruff 应该报错但没报; 6-27 → 7-7 期间 cqggzy 列表采集 = 几乎全 0 (KeywordsService bug 持续 10 天); Bug #4 真实根因: `_get_conn()` 是 thread-local 缓存，失败后 conn 遗留 aborted state [score=0.819 recalls=0 avg=0.620 source=memory/2026-07-07.md:36-38]
<!-- openclaw-memory-promotion:memory:memory/2026-07-07.md:43:45 -->
- 修复执行: **修 #1**: `cqggzy.py` 加 `from app.services.keywords_service import KeywordsService`; **修 #3**: migration 007 (`ALTER TABLE favorites ADD COLUMN deadline TEXT`); **修 #4**: `db.py` `_get_conn()` 入口加 `conn.rollback()` 清理状态 + try/finally + `pool.putconn()` [score=0.819 recalls=0 avg=0.620 source=memory/2026-07-07.md:43-45]
<!-- openclaw-memory-promotion:memory:memory/2026-07-07.md:48:51 -->
- 验证结果: 11:58 手动触发: **620 条 / 255 匹配** (vs 之前 1/0) ✓; 12:00 cron 触发: **621 条 / 257 匹配** ✓; 12:13 完成 summary: 621/257，详情提取全部成功 ✓; watchdog 静默期: log 显示 `quiet hours (20:00-8:00), skip stale alert` ✓ [score=0.819 recalls=0 avg=0.620 source=memory/2026-07-07.md:48-51]
<!-- openclaw-memory-promotion:memory:memory/2026-07-07.md:53:53 -->
- 验证结果: → **PR #77** 创建 (fix/cqggzy-keywords-service-import-2026-07-07) [score=0.819 recalls=0 avg=0.620 source=memory/2026-07-07.md:53-53]

## Promoted From Short-Term Memory (2026-07-14)

<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:12:12 -->
- 修复前快照 (cron.get 2026-07-11 17:49): **daily-summary-21:00** (`2005eeb0-d865-40aa-b151-a298f1db3380`) [score=0.815 recalls=0 avg=0.620 source=memory/2026-07-11.md:12-12]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:19:19 -->
- 修复前快照 (cron.get 2026-07-11 17:49): **中午汇报 - 采集关键项目** (`12eb4804-6cfb-42e7-8a94-eca22225c5a1`) [score=0.815 recalls=0 avg=0.620 source=memory/2026-07-11.md:19-19]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:24:24 -->
- 修复前快照 (cron.get 2026-07-11 17:49): 7-10 12:00 run: M3 + M2.7 双 overload, 217s, error "All models failed" [score=0.815 recalls=0 avg=0.620 source=memory/2026-07-11.md:24-24]

## Promoted From Short-Term Memory (2026-07-15)

<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:13:16 -->
- 修复前快照 (cron.get 2026-07-11 17:49): model: `minimax/MiniMax-M3`; fallbacks: **未配置** ❌; thinking: "off"; timeoutSeconds: 1800 [score=0.821 recalls=0 avg=0.620 source=memory/2026-07-11.md:13-16]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:17:17 -->
- 修复前快照 (cron.get 2026-07-11 17:49): 7-10 21:00 run: qwen3.5-397b/nvidia, 153s, error "Agent couldn't generate" [score=0.821 recalls=0 avg=0.620 source=memory/2026-07-11.md:17-17]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:20:23 -->
- 修复前快照 (cron.get 2026-07-11 17:49): model: `minimax/MiniMax-M3`; fallbacks: `["minimax/MiniMax-M2.7", "minimax/MiniMax-M3"]` ❌ 全 minimax; thinking: "minimal" ⚠️ 历史已知不兼容 M3; timeoutSeconds: 1500 [score=0.821 recalls=0 avg=0.620 source=memory/2026-07-11.md:20-23]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:29:31 -->
- 修复计划 (方案 B — 加 qwen 122b fallback): qwen3.5-122b-a10b 是 NVIDIA 上更稳定的小模型 (历史 AGENTS.md 6-3 记录); 加到 fallback 链第 3 位，minimax 全 fail 时退到 qwen 122b; 修 thinking "minimal" → "off" (避免 M3 兼容性问题) [score=0.821 recalls=0 avg=0.620 source=memory/2026-07-11.md:29-31]
<!-- openclaw-memory-promotion:memory:memory/2026-07-11.md:6:8 -->
- 背景: 7-10 21:00 daily-summary-21:00 失败 (qwen3.5-397b 过载); 7-10 12:00 中午汇报失败 (minimax M3+M2.7 双 overload); 用户 23:15 问"检查失败的原因" → 我报告 → 用户 17:49 答"继续" [score=0.821 recalls=0 avg=0.620 source=memory/2026-07-11.md:6-8]

---

## 2026-07-16 00:09 — ABC 三件事收尾 + M2.7 context 留档

- **A (修 3845a680 晚间汇报)** ✅ 完成
  - `openclaw cron edit 3845a680-d513-40af-a2a9-aee6f21aa5e6 --fallbacks 'minimax/MiniMax-M2.7,minimax/MiniMax-M3'`
  - verify: `cron get` 独立确认 `fallbacks = ['minimax/MiniMax-M2.7', 'minimax/MiniMax-M3']` ✅
  - thinking/toolsAllow 未动（thinking=minimal, toolsAllow=35 项原本正常）
- **B (AGENTS.md slim commit + PR)** ⏸️ 暂停
  - 原因: `git status` 显示 **538 files** M+D，远超 slim 工作量 (5 文件: AGENTS.md / MEMORY.md / TOOLS.md / notes/lessons-learned.md / notes/dg-patterns.md)
  - 涉及 D 删除: Dockerfile, Makefile, README.md, README_CN.md, BOOTSTRAP.md, IMPROVEMENT_SUMMARY.md, REFACTORING_GUIDE.md 等 — 这些**不是 slim 工作范围**，可能是历史未提交状态
  - 等 user 拍板: (a) 只 commit slim 5 文件 (b) 全 commit (c) 撤回所有不相关改动
- **C (M2.7 context)** ⚠️ 维持 204.8K (备选路径)
  - User 23:58 直告"M2.7 不止 205k"，我查 6+ 独立源全部 204.8K
  - User 00:09 "一起"未补 M2.7 来源 → 选备选 = 维持 204.8K
  - 留档: AGENTS.md / MEMORY.md / notes/lessons-learned.md 已记 "user 直告但未提供 source URL"
  - 后续: user 任何时候给来源 (provider URL / 实测 payload / docs 截图) → 立即覆盖
- **lesson 15 新增**: cron edit CLI `--fallbacks` 接受**逗号分隔纯 model id 字符串**，不接受 JSON 数组
  - 错误尝试: `--fallbacks '["minimax/MiniMax-M2.7","minimax/MiniMax-M3"]'` → 解析成 `['["minimax/MiniMax-M2.7"', '"minimax/MiniMax-M3"]']` (string-of-list)
  - 正确: `--fallbacks 'minimax/MiniMax-M2.7,minimax/MiniMax-M3'` → 解析成 `['minimax/MiniMax-M2.7', 'minimax/MiniMax-M3']`
  - 回退: `--clear-fallbacks` 可清掉错误状态
