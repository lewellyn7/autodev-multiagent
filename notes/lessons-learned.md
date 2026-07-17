# Lessons Learned (历史教训归档)

> 本文档是 AGENTS.md 中 "Learned Lessons" 章节的历史归档。**完整教训背景、修复细节、AGENTS 6-7 铁律应用**已在此展开。当前生效的精简规则在 `AGENTS.md` → Active Iron Rules (7)。

---

## 资管修复操作顺序：先审核 → 后备份 → 再执行 (2026-06-07)

**事件：** lewellyn 在 #22672 / #22715 两次明确："**先审核再执行，做好必要的备份和版本管理工作**" + "**记住 先审核 后备份，做好项目管理，再执行修改**"。升级为长期工作铁律。

**铁律（任何代码/数据修改都要按此顺序）：**
1. **审核（先）** — 动手前先：
   - 列出所有要改的文件 + 关键行号
   - 评估每个改动的风险（数据/接口/回归）
   - 写执行计划 + 提交粒度 + 回滚方案
   - 让用户拍板再进入下一步
2. **备份（后）** — 审核通过后才动：
   - dirty state → `git stash` 或建 WIP commit
   - 建独立分支（**不在 main/master 上改**）
   - 关键文件 `.orig` 快照（便于一键对比）
   - 生产 DB 关键表 snapshot（防误改）
3. **项目管理** — 期间维护：
   - 每个独立改动 = 1 个 commit
   - commit message 用中文，描述清楚 why
   - `.pre-qual-feature/` 类工作目录放备份，**不进 git**
   - 端到端验证（curl）后才能合并
4. **执行（最后）** — 改完后：
   - 单测通过 + 端到端 curl 验证
   - 推分支到 origin
   - 出 PR 让用户 review
   - **不主动合并到 main**

**反面例子（要避免）：**
- ❌ 看到 bug 直接改（跳过审核）
- ❌ 审核完不备份就改（脏改污染）
- ❌ 多个改动塞一个 commit（无法回滚单个）
- ❌ 在 main 分支直接改（生产风险）

---

## backfill 脚本必须传 scraped_at (2026-06-03)

**事件：** 跑 `scripts/backfill_6-2.py` 补采 6-2 丢失数据，row 字典没传 `scraped_at` 字段，导致 `ON CONFLICT (url) DO UPDATE` 把 `projects_cqggzy` 表里 600+ 条已存在记录的 `scraped_at` 字段设为 NULL（8004 次 upsert 中大部分都是 ON CONFLICT）。

**规则：**
1. **任何 `upsert_projects` 调用都必须传 `scraped_at`**，否则会破坏已存在数据的时间戳
2. row 字典应该包含 `db.py:340` cols 列表中的所有字段，或至少传 scraped_at
3. **写入前**先 SELECT 验证 URL 是否已存在，预估影响范围
4. 一次性补采脚本：参考 `scripts/backfill_6-2.py`（已修），必须传 `scraped_at`

**修复：** 补采脚本已修复（加入 `scraped_at: datetime.now().strftime(...)`）。已破坏的 600+ 条 NULL scraped_at 不补救（不值得复杂化；publish_date 仍准确）。

---

## 列表采集只采第 1 页 bug (2026-06-03)

**事件：** `main.py:156` 调用 `crawler.fetch_list(category=c, start_date=..., end_date=...)`，没传 `page_num`，默认 1，导致每次采集每分类只采 50 条（API 第 1 页），丢失 50+ 之后的数据。

**影响：** 6-1 / 6-2 那次只采到 95 条 / 31 条（应为 400+）。6-2 publish_date 范围内实际丢失 46 条左右。

**修复：** main.py 新增 `_fetch_all_pages` 函数，循环 page=1..N 直到 API 返回 <50 条。

---

## 列表 API 不再返回 content 字段 (2026-06-03)

**事件：** CQGGZY 改版后 `/api/v2/search-engine-page` 返回的 `content` 字段为空字符串。`app/crawlers/cqggzy.py:225` 的 `if raw_content:` 永远不进入，导致 `tender.full_content` 保持空。`extract_project_info` 兜底逻辑用 `title[:100]` 填充 `content_preview`。

**规则：**
1. **不要相信 API 注释** — 改版后注释会过期
2. **定期抓包验证** API 字段是否仍存在
3. 兜底逻辑不要用 title 截断填充"摘要"字段

---

## 批量 DELETE 需双重确认 (2026-06-01)

**事件：** 误删 5,973 条 `projects_cqggzy` 历史数据（2026-02-26 至 2026-05-22）。

**根因：** 误用 `DELETE FROM ... WHERE url LIKE '/xxhz/%'` 把旧 URL 整批清掉，但其中部分记录含有有效项目（仅 UUID 错误）。

**规则：**
1. **DELETE 前必须 SELECT 验证** — 先 `SELECT id, url, title FROM ... WHERE ...` 看清楚匹配数
2. **带 LIMIT 起步** — `DELETE ... WHERE ... LIMIT 100`，跑两步看日志
3. **加事务回滚能力** — `BEGIN; DELETE ...; ROLLBACK;` 演练一遍再 COMMIT
4. **保留 24h 自动备份** — `pg_dump` cron 每日 3 点；删除前 `pg_dump -t table_name > backup.sql`
5. **不可逆操作需用户二次确认** — `rm -rf`、`DROP TABLE`、`DELETE > 100 行` 必须等用户说"确认"

**不可恢复数据特征：**
- API 列表页只保留 3 个月窗口（>90 天不可重新发现）
- 单条详情页 URL 仍可访问，但**列表搜索失效**导致无法补采
- 唯一恢复途径：CCGP/搜索引擎缓存（不可靠）

---

## CQGGZY API edt 排他 (2026-06-05)

**问题:** `end_date = today` 导致每天漏掉当天数据（~50 条/天）。

**验证:**
- `sdt=6-5, edt=6-5` → 0 条
- `sdt=6-5, edt=''` → 23 条
- `sdt=6-4, edt=6-5` → 297 条（仅 6-4）
- `sdt=6-3, edt=6-5` → 539 条（6-3+6-4）
- `sdt=5-30, edt=6-5` → 1011 条（5-30~6-4）

**结论:** edt 是排他的（不含当天）。修复：`end_date = today + timedelta(days=1)`。

**影响范围:** AGENTS.md 学到的"列表采集只采第 1 页 bug (6-3)"之前的代码，每天漏采当天。

---

## scraped_at NULL 大规模修复 (2026-06-05)

**问题:** AGENTS.md 之前记录"600+ 条 NULL scraped_at 不补救"，但实际检查发现 **10,331 条**受影响（远超预期）。

**原因:** backfill_6-2.py 等补采脚本的 `ON CONFLICT (url) DO UPDATE SET scraped_at=NULL` 蔓延到了所有 upsert 的字段。

**修复:** `UPDATE projects_cqggzy SET scraped_at = created_at WHERE scraped_at IS NULL AND created_at IS NOT NULL`（10,331/10,331 全部修复）。

**教训:** AGENTS.md 的"不可逆操作需用户二次确认"只涵盖 DELETE/UPDATE；规模估算错误时应重新检查，不应轻信旧记录。

---

## detail_limit 提升 (2026-06-05)

**问题:** main.py 100 条/周期，匹配 3,684 条中只有 100 条有详情正文。

**修复:** `min(100, ...) → min(300, ...)`，每周期 ~16min 跑到 300 条。

**验证:** 下一周期 (10:00) 生效，300 条详情采集后写 full_content。

---

## sub-agent hot-deploy 漏验证 (2026-06-27)

**事件:** P2 子代理报告说 "已完成 page_size 上限修改 (le=20000→le=5000)"，但端到端烟测 `?page_size=10000` 仍返回 200 (期望 422)。Worktree 里是 `le=5000`，但容器里还是 `le=20000`。子代理 `docker cp` 后没 `docker restart`，或 restart 后 hot-deploy 没生效。

**规则:**
1. **每个 sub-agent 改完文件 → 强制 `docker restart`** + smoke 端到端验证 (不能只 `docker cp`)
2. **主代理收到 sub-agent 报告 → 抽查 ≥1 个 hot-deploy 改动在容器内文件实际内容** (用 `docker exec grep`)
3. **smoke 验证结果必须 attach 到 sub-agent 报告**, 不能只说 "测试通过"
4. sub-agent 不能省略 `docker restart` 步骤 (p1-api 子代理就漏了)

**修复:** 后续派工模板加硬性 hot-deploy 校验步骤
```bash
docker cp <file> <container>:/app/<file>
docker restart <container>
sleep 8
docker exec <container> grep "关键改动" /app/<file>  # 主代理抽查
curl ...   # smoke 验证
```

---

## PG 路径 ? 占位符静默失败 (2026-06-27)

**事件:** `app/database/tables/keywords.py:96` `update_keyword` 用 `f"UPDATE keywords SET ... WHERE id = ?"`。SQLite 路径正常, PG 路径下应 `%s`。生产配 PG, 直接 psycopg2 报错 → 单元测试 sqlite 路径通过, 集成路径失败。

**根因:** 历史代码用 SQLite 开发, 后期切 PG 但占位符没改。`add_keyword` 已用 `placeholder = "%s" if USE_PG else "?"` 兼容, 但 `update_keyword` 漏改。

**规则:**
1. **任何 SQL 必须用 `placeholder = "%s" if USE_PG else "?"` 双路径兼容**, 禁止硬编码单一占位符
2. **新增 SQL 函数**: 顶部 1 行 placeholder 变量是必填
3. **子代理审查 SQL 改动时**: 必须 grep `?` 和 `%s` 出现位置, 报告给主代理
4. **生产 DB 切换日志**: db.py 启动应打 "using PG" 或 "using SQLite" 便于排查

**主代理验真经验:** 4 子代理并行审查时, 主代理必须**额外 grep 一遍 SQL 占位符** (sub-agent 易漏跨文件引用)

---

## SQLite autocommit vs PG 事务边界 (2026-06-27)

**事件:** `keywords.py` 4 个写函数 (add/update/delete/toggle) 调 `c.execute()` 后直接 return True, **没有 commit**。SQLite autocommit 模式 → 数据写入；PG 默认 autocommit=False → execute 只发送, 没 commit = 写入丢失但函数返 True = 静默丢数据。

**生产配置:** `async_models.py:18` 用 PG, 当前生产是 PG 路径, 4 个写函数 100% 静默失败。

**规则:**
1. **任何写函数 execute → 必须 commit/putconn**: SQLite `c.commit()`, PG `self._conn_pool.putconn(c)` + `c.connection.commit()` 或统一 `c.commit()` (psycopg2 connection 也有 .commit)
2. **统一 commit helper**: 抽 `_commit(c)` 函数, 内部按 USE_PG 分支
3. **写函数 docstring 必须声明事务边界**: "SQLite autocommit / PG manual commit"
4. **测试必走 2 路径**: 单元测试不能只跑 SQLite, 必加 psycopg2 mock 或 testcontainers

**检查清单 (代码 review):**
- [ ] 写函数有 commit() 调用
- [ ] 占位符按 USE_PG 分支
- [ ] docstring 声明事务边界
- [ ] 单元测试 2 路径都跑

---

## upsert 覆盖详情 bug (2026-06-05)

**问题:** `db.py:348` 的 `ON CONFLICT (url) DO UPDATE SET {set_clause}` 会把空 `full_content`/`content_preview` 写回。每周期 8001 条里 7700+ 条详情被清空（仅保留详情阶段 fetch 的 ~300 条）。

**根因:**
1. 列表 API 不返回 content（AGENTS.md 6-3 bug）
2. main.py 先 list upsert（空 fc）→ 再 detail upsert（限 300 条）
3. step 1 的空 fc 覆盖了之前 backfill 填好的 fc

**修复:**
```sql
-- app/database/db.py:351-358
protected_cols = {"full_content", "content_preview"}
set_parts = []
for c in cols[1:]:
    if c in protected_cols:
        set_parts.append(f"{c}=COALESCE(NULLIF(EXCLUDED.{c}, ''), projects_cqggzy.{c})")
    else:
        set_parts.append(f"{c}=EXCLUDED.{c}")
```

**验证:** 4个补采脚本对 6-2~6-5 共 488 条 100% 填上 fc，0 cp=title。

**附带修复:** `app/utils/filter.py:156` 移除 `title[:100]` 兜底，避免列表项 cp 总是 title。

**原则:**
- 详情的 `INSERT ... ON CONFLICT ... DO UPDATE` 写时必须保护非空字段
- 列表 API 补采的 row 不应覆盖已填的详情字段
- 兜底逻辑不能用 title 充摘要（会误导用户）

---

## 导出 CSV 端点 business_type 丢失 (2026-06-05)

**问题:** `/api/export/csv?category=政府采购` 返回空数据。

**根因:**
1. DB `business_type` 字段 11307/11307 全部为 NULL（采集器从未写入）
2. `/api/projects` 路由在序列化时**根据 URL 推理**填充 `business_type`（`projects.py:90-105`）
3. `/api/export/csv` 直接查 DB `business_type = ?` → NULL → 0 结果

**修复 (`app/api/routes/exports.py`):**
```python
if category == "政府采购":
    conditions.append("(url LIKE '%%014005%%' OR url LIKE '%%order%%')")
elif category == "工程招投标":
    conditions.append("(url LIKE '%%014001%%' OR url LIKE '%%bidding%%')")
```

**附带修复:** 前端导出按钮 (`data.html:624`) 未传 `date_start`/`date_end`——筛选面板有日期范围，导出按钮忽略。补充参数后完整生效。

**验证:**
- `category=工程招投标` → 4673 行
- `category=政府采购` → 5001 行
- `keyword=智能&category=政府采购&date_start=2026-06-04&date_end=2026-06-05` → 5 行

**教训:**
- DB 字段 NULL 时，API 层 "推理" 不可靠，导出端点需复用同一推理逻辑或用 URL 模式
- 前端筛选面板和导出按钮必须传相同参数集

---

## 项目链接修复模式 (2026-06-01)

**问题：** UUID 用错字段（`syscollectguid` 应为 `infoid`），导致 6335 条 URL 全部错误。

**修复模式：**
- 列表页 → 详情页 跳转时，必须用**项目唯一 ID**（`infoid`），不是**分类共享 ID**（`syscollectguid`）
- 采集 API 返回多 ID 字段时，**优先取 UUID 格式字段**，数字 ID 通常是排序/索引位
- URL 转换时保留 `categoryNum`（10 位）作为查询参数，路径中只放 UUID
## 13. 模型能力数据严禁脑补 (2026-07-15, 22:10 verified)

**事件：** AGENTS.md 6-3 写了"context > 50% 就 /compact"，隐含假设 minimax M3/M2.7 = 205k。User 22:09 强制查官方 docs → 揭示真实数字与假设差 ~5× (M3 = 1M)。

**官方 docs 查证 (22:10)：**
- **MiniMax-M3 = 1,000,000 tokens (1M)**, max output 512K
  - 来源: <https://platform.minimax.io/docs/guides/text-generation>
  - 来源: <https://www.minimax.io/blog/minimax-m3> (2026-05-31 发布)
- **MiniMax-M2.7 = 204,800 tokens (204.8K)**
  - 来源: MiniMax API docs + cline PR #10007 (192K → 204.8K 修正)
- `session_status` 报的 205k ≈ **M2.7 上限**, **不是 M3 硬限**

**根因 (silent knowledge bug):**
- 我把 runtime 网关显示当成模型 API 硬限
- 没查 docs / `models list` / 问 user — 直接拍脑袋

**规则：**
1. **任何 "X 模型 = Y tokens / Y RPM / Y 能力" 断言无证据 → 标 "unknown"** — docs / runtime / 问 user 三取一
2. **`session_status` 显示分母 ≠ 模型硬限**（可能只反映一个 fallback 模型或纯 gateway 上限）
3. **写规则前, 三取一验证 + 引用 source URL**
4. **silent knowledge bug 自检：** AGENTS.md / MEMORY.md 出现 "X 就是 Y" 时默认自检一次

**后果：** 6-3 老规则 50% threshold 在 M3 1M 上下文下 = 500K, **过度激进**（实际几乎不会触发）

**修复：**
- `AGENTS.md` → 上下文管理（2026-07-15 修正, verified 22:10）阈值 50% → **85% (used)** + 800k 绝对阈值
- `MEMORY.md` fact 条用真实数字 + source URL
- 本条 lesson 13 (verified 22:10)

**同类高风险 silent 假设 (同期自检清单)：**
- cron 频率 (9 分钟 vs 30 分钟 — 实测还是 docs?)
- API 限速 (60 / 100 rpm? — docs 还是脑补?)
- 采集上限 (300 条/周期 — 实测还是脑补?)
- 容器内存上限 (2 / 4 GB? — docs 还是脑补?)
- **全部默认配置前先实跑一次, 不脑补**## 14. cron / 状态修改工具的 silent failure 套路 (2026-07-15)

**事件：** 修中午汇报 cron 用了 6 次 `cron update` 工具调用，每次返回的响应看起来成功（updatedAtMs 更新），我都回复用户"已修"。**实际上**：6 次都把 `fallbacks` 和 `toolsAllow` 设成了 `[]`（我以为传空数组 = "删除 qwen"，实际 patch 是 **REPLACE 不 MERGE**，空数组 = 清空整个列表）。等用户 22:02 说"修"我才反应过来并改用 `openclaw CLI` via exec 验证 — `cron get` 显示 `fallbacks: [] toolsAllow: []`，是真的双重残废。

**双重 root cause（组合陷阱）：**
1. **patch 是 REPLACE 不是 MERGE** — `cron` (model tool) 的 `patch.payload.fallbacks: []` 直接覆盖原数组，不是移除元素
2. **trajectory 切片 → `synthetic_tool_result`** — agent loop 在 final user turn 后被 sliced 时，工具调用可能记录为成功但实际响应被 mock 替换；agent 据此写"已修"但其实没动

**规则（必须）：**
1. **任何 cron / config / 状态修改 → 必须用独立路径 verify**：写后立刻用 `cron get` / 文件读取 / DB query / api 校验重新获取状态
2. **model tool 的 patch 不能默认相信** — `[]` 不是 "清空 qwen"，是清空**整个**列表
3. **trajectory 切片出现时，立刻换 CLI** — 用 exec 跑 `openclaw cron edit --fallbacks "..."` 是真实可验证的路径（绕开 model tool 的 mock）
4. **不要在失败循环里继续** — 1 次失败后立刻换工具/路径，而不是重试相同的 tool N 次

**修复路径模板（下次遇到）：**
```bash
# 1. 用 exec 跑 openclaw CLI（不被 mock 替换）
export PATH="/home/lewellyn/.nvm/versions/node/v24.18.0/bin:$PATH"
openclaw cron get <id>  # 拿真实当前状态
openclaw cron edit <id> --fallbacks "m1,m2" --tools "t1,t2,t3"  # 精确 flag
openclaw cron get <id>  # 独立 verify

# 2. 写关键 lesson 用 exec + cat >> 或 python (write tool 也可能 mock)
cat >> notes/lessons-learned.md << 'L_EOF'
... lesson content ...
L_EOF

# 3. git 提交也是 exec (真实 shell)
git add -A && git commit -m "..."
```

**silent failure 自检清单（写前 30 秒）：**
- [ ] 是不是 list/array 字段？patch 行为是不是 REPLACE 而非 MERGE？
- [ ] 这个 tool 是否会受 trajectory 切片影响？是否被 mock 替换过？
- [ ] 验证路径是否独立于修改路径？不能 edit → edit 自证

**影响范围：** 任何写操作（cron / config / DB / 文件 / message send）。下次遇到 silent tool result 立刻换 CLI/独立 verify，**不重试同一 tool**。

**增订 (00:04 7/16) — lesson 13 更严版本：User 给数字也要 source URL 验证**

- 事件：user 23:58 直告 "M2.7 不止 205k"，我查 6+ 源全部 204.8K，**未立刻覆盖文件**，问 user 来源 → 避免 lesson 13 silent knowledge bug 第三次
- 教训：lesson 13 原始版只防"我脑补"，**没防"user 给数字就盲信"**
- 新规则：
  1. **user 断言 = 数据点**，不是结论 — 必须查 docs / 跑实测 / cross-reference ≥ 2 个独立源
  2. **冲突时**："user 直告但没源" vs "≥2 独立源一致" → 后者赢，但**两种结果都列出来**给 user 拍板
  3. **不 silent 覆盖** — 任何 "X 是 Y" 改动必须先列证据再改文件
- 同类高风险盲信：user 说"这个 cron 没事" / "这个 API 快" / "这个采集正常" — 全部默认 verify 一次

## 15. cron edit CLI 格式坑 (2026-07-16, 00:09)

**事件:** 修 3845a680 晚间汇报 fallbacks 时第一次执行 `--fallbacks '["...","..."]'` (JSON 数组)，CLI 错误解析成 `['["minimax/MiniMax-M2.7"', '"minimax/MiniMax-M3"]']` — 把整个 JSON 字符串当作单个字符串 list 元素。

**坑点:**
- `--fallbacks` / `--tools` 接受**逗号分隔的纯字符串 list**，不是 JSON 数组
- 文档里 `--tools <list>` 的 example 是 `exec,read,write or exec read write` — 没用 JSON 包装
- bug 后果: cron edit 静默成功，但 `cron get` 显示 fallbacks 是 string-of-list，无法被 agent runtime 当作有效 fallback chain

**规则:**
1. **CLI 字符串 list 参数永远用逗号分隔纯值**: `--fallbacks 'a,b,c'`，**不用** `'["a","b","c"]'`
2. **改 cron 后必须独立 verify**: 用 `cron get` (不是 edit 的 response — 那是 echo)
3. **错误状态可用 `--clear-xxx` 回退**: `--clear-fallbacks` / `--clear-model` 等
4. **同类参数**: `--tools`, `--fallbacks`, `--failure-alert-to` 等多值参数全部走此规则

**修复路径:**
1. `cron edit <id> --clear-fallbacks` 清掉错误状态
2. `cron edit <id> --fallbacks 'm1,m2,m3'` 用正确格式
3. `cron get <id>` 独立 verify `fallbacks = ['m1','m2','m3']` (Python list, 不是 string-of-list)

**lesson 14 增订:** lesson 14 只说 "patch REPLACE not MERGE"，没提 CLI 参数格式坑 — lesson 15 补齐。

## 16. cron runs --limit N 排序不保证最新 (2026-07-16, 06:14)

**事件:** verify 3845a680 / 2005eeb0 昨晚是否成功时，第一轮 `cron runs --id 2005eeb0 --limit 50` 返回的"最新"是 **2026-06-04 21:00**（42 天前），差点误判 silent-killer（以为 cron 没跑 / run history 被清空）。

**真相:** 改 `cron runs --id <id> --limit 3` + grep `runAtIso` 才看到真实昨晚记录（2026-07-15 21:00:02.006, status ok, model M2.7, fallbackUsed false）。

**坑点:**
- `cron runs --limit N` 返回的 N 条**不保证是最新 N 条** — OpenClaw runtime 2026.7.1 实测返回**最早** N 条（按时间正序）
- 看到 "old date" 不能直接断定 silent-killer — 必须交叉 verify
- silent-killer 误判会让 user 多余 work（已修好 fallback 又被怀疑没修 → 二次修复浪费时间）

**规则:**
1. **永远用 `cron runs --id <id> --limit 3` + grep `runAtIso` 作为 first-step** — 不直接用 limit=50/100
2. **silent-killer 警报前必须交叉验证** — 至少 2 个独立数据点：
   - `cron list` 的 `Xh ago` 字段（调度器视角）
   - `cron runs` 的 `runAtIso`（实际 run history）
3. **看到旧日期不要立刻拍结论** — 先验证排序逻辑

**修复路径:**
1. `cron runs --id <id> --limit 3` — 看最新 3 条
2. `grep runAtIso` 找真实最新日期
3. 跟 `cron list` 的 `Xh ago` 字段交叉验证
4. 两者一致才下结论

**lesson 7 增订:** lesson 7 silent-killer 审计 routine 只说 "核心模块改动必须 verify + `return []` / `return None` 路径审计"，没提 **数据排序陷阱** — lesson 16 补齐。

## 17. `git checkout HEAD -- <file>` 之前永远先 diff (2026-07-16, 09:30)

**事件:** C-1.3 处理 M 文件时按 plan "3 runtime checkout HEAD" 执行 `git checkout HEAD -- .clawhub/lock.json .openclaw/workspace-state-state.json .github/workflows/ci.yml`。**几乎误删 ci.yml** — diff 显示它有真用户修改:
- `branches: [main, develop]` (加 develop 触发)
- `release: types: [published]` (加 release event)
- 移除 `PYTHON_VERSION: '3.11'` env
- 重构 jobs (`test` → `lint`, 删 PYTHON_VERSION, 加 release job)

**恢复路径:** 因为 Step 1 backup 把 ci.yml modified 备份到 `.backup-2026-07-16-pre-c1/ci.yml.before-checkout` (159 lines) → 立刻 `cp` 还原 → M 状态恢复 → 重新 `git add` → 上线。

**坑点:**
- `git checkout HEAD -- <file>` 是**不可逆 destructive** — working tree 修改丢失 (除非 stage)
- `.gitignore` / `.github/workflows/*` / `*.config` 等文件**不是 runtime state**，可能是用户真配置
- 默认假设 M = runtime 是错的 — 必须先 diff

**规则:**
1. **`git checkout HEAD -- <file>` 之前永远先 `git diff <file> | head -30` 看内容**
2. **如果 diff 显示用户实质修改 (新字段/新触发/重构)**: NOT runtime — 用 `git add` 保留
3. **如果 diff 是空白 / 自动生成标记**: 可能是 runtime — checkout HEAD
4. **核心模块配置文件永远不 checkout HEAD** — 包括 `.github/workflows/*`, `*.config`, `requirements.txt`, `pyproject.toml`, `Dockerfile`, `docker-compose.yaml` 等
5. **destructive 命令前先 cp 备份** — 哪怕只是 one-line `cp file .backup/file.before-op`

**lesson 13 增订:** lesson 13 (silent-killer 误判陷阱) 只说 "看到旧数据先验证排序"，没提 **destructive 命令的 reverse 风险** — lesson 17 补齐。

---

**C-1 结果（2026-07-16, 09:34）:**

**修复统计:**
- 533 unstaged → 1 untracked (claude/)
- D 251 → 0
- M 11 → 0
- ?? 732 → 1
- Staged 105: 56 sessions (删) + 34 ai-gateway-improved (删) + 5 采集系统 notes + 2 memory + lessons-learned + .gitignore + ci.yml + .env.sample + 4 新 notes
- Trash: 9 temp files + tmp/ → `.trash-2026-07-16-c1/`

**关键教训:**
1. 8 docs M 修正 → 实际在 D (审计误判，lesson 13 关联)
2. ci.yml 不是 runtime (lesson 17)
3. notes/后端架构.md 不存在 → 后端架构**师**.md (文件名错)
4. memory/ 318 文件 → .gitignore 化
5. sessions/ + ai-gateway-improved/ → `git rm --cached` + .gitignore
6. trash 不可用 → 用 `mkdir .trash-* + mv`

## 18. PG transaction aborted + audit 数字 silent-killer 双重 bug (2026-07-16, 23:35)

**事件**：用户 19:25 改方向修"链接和详情"，我出诊断报告 + audit，4 轮下来发现：

### Bug A：PG transaction aborted 吞 179 条详情

**evidence**（采集器日志 18:18）：
```
📄 详情页成功: 酉阳县泔溪镇... (2338字)
⚠️ 详情写 DB 失败: current transaction is aborted
```

**根因**（不是诊断报告写的 `pipeline.py:crawler_fn`，该文件不存在）：
- 真实位置 `app/database/async_models.py:626 save_harvest_records`：
  ```python
  async def save_harvest_records(records, source_name):
      async with DatabaseManager.transaction() as conn:  # ← tx 上下文
          for r in records:
              _, is_new = await HarvestRecord.upsert_by_url(conn, ...)
              # ⚠️ 单条失败 → 整个 tx aborted → 后续全失败
  ```
- `DatabaseManager.transaction()` (`async_models.py:57-62`) 用 `async with conn.transaction()` 包整个 loop
- PG fundamental：**事务 aborted 后所有命令失败直到 ROLLBACK**
- 同事务内的 keywords_service 失败污染 → save_harvest_records 写 DB 全失败

**影响**：179 条 ✅ 正常 URL 详情被吞（25%）

**修法**：每条 record 独立 transaction + try/except（不能用 savepoint，因为 conn 还是 aborted）

### Bug B：audit 数字 silent-killer 差 6.7x

**用户被误导的数字**（诊断报告 #27710）：
- "trade 缺 _1 = 617（7 天）"
- "cqggzy_root 141 条（7 天）"
- "trade 缺 _1 = 42607（全量）"
- "cqggzy_root 28396（全量）"

**真实数字**（双 SQL 交叉验证）：
- trade/014 总数 = **110,937**（不是 82,541）
- trade/014 缺 _1 = **71,045**（不是 42,607/617）
- trade/014 有 _1 = **39,892**
- xxhz 路径 = **261**
- **"cqggzy_root 其他" = 0**（不是 28,396！）

**根因**：
- `regex '~ /trade/01400[15]/[^/?]+'` greedy 匹配 `UUID_1` 整段，把"有 _1"也算成"缺 _1"
- `NOT LIKE 'https://www.cqggzy.com/trade/014%'` 排除 trade/014 后剩 261 = xxhz 数量，被错误命名为"根路径"
- 我前面 audit 的"trade 缺 _1"分类把 71,045 个缺 _1 URL 只算了 617（7 天）/ 42,607（全量），silent-killer 数字小 100x+ 误导工作量评估

**教训**：
- lesson 7+ silent-killer 警报**持续命中** — DB 完整性 + audit 数字一致性是同一类陷阱
- lesson 13（silent 假设错）又中招：617 → 71,045，差 **115 倍**！
- lesson 16（cron 排序陷阱）+ lesson 17（destructive 前必 diff）+ lesson 18（数字一致）= "审核期三大 silent-killer"

**规则**（lesson 18 增订）：
1. **任何 "X = N" 数字必须双 SQL 交叉验证** — 用不同 WHERE 子句看是否得到一致结果
2. **PG transaction 修法**：每条独立 transaction + try/except，**不能用 savepoint**（因为 conn 已 aborted）
3. **regex 边界**：`[^/?]+` greedy 陷阱，必须明确 `$` 或更严的 regex
4. **bug 影响估计必须用最严 regex** — 宁可漏报不要错报（差 115x 不可接受）
5. **诊断报告先审再行动** — 数字 silent-killer 比 silent-killer bug 更危险（让人以为工作量小）

**关系**：
- PR #77 (7-7 修 keywords_service import + `_get_conn()` rollback) **没修全** — 还有 `save_harvest_records` 路径未覆盖
- 类似的 contextmanager 模式可能还有：`app/services/keywords_service.py`、`app/api/harvest_api.py` 调用链

**关联文件**（待 audit 完动手修）：
- `app/database/async_models.py:626` (save_harvest_records)
- `app/database/async_models.py:295` (upsert_by_url)
- `app/database/async_models.py:57-62` (DatabaseManager.transaction)
- `app/crawlers/cqggzy.py:76` (full_url 拼接，无 _1 规范化)
- `app/api/harvest_api.py:278` (save_harvest_records 调用入口)

## 19. 批量 URL 修复前必先 HTTP 验证 (2026-07-17, 02:35)

**事件**：用户 02:28 反馈"不是所有链接都需要加_1，是否加_1 要通过链接验证是否能获取详情"。
- 我之前 mini-spec 直接 SQL `UPDATE ... url = REGEXP_REPLACE(...)` 给 71,045 条 trade 缺 _1 的 URL 加 `_1`。
- **silent-killer**：没验证链接有效性就批量改 — lesson 7+ 警报**第 3 次**命中（前 2 次：PR #77 keywords_service / lesson 18 audit 数字）。

**坑点**：
- **A 类**（不加 `_1` → 200）：网站自动重定向，`_1` 不是必需的
- **B 类**（加 `_1` → 200）：真正需要修复
- **C 类**（加 `_1` → 404）：永久死链（项目下架/UUID 不存在）— 加了也没用
- **D 类**（加 `_1` → 200 但无详情内容）：broken detail page — 加了也搜不到正文

**规则**：
1. **任何批量 URL 修复前必先抽样验证** — 抽 `N=200`，对每个 URL 同时 HEAD 测试原 URL 和加 `_1` 后 URL
2. **HTTP 验证用 HEAD 而非 GET** — 减少反爬压力（lesson 1）+ 加快速度
3. **限速 1-3 req/s** + retry + backoff，避免被目标站封 IP
4. **分类决策**：
   - A > 50% → 网站自动重定向，**不批量加 `_1`**，改其他修法
   - B > 70% 且 C+D < 30% → 批量加 `_1`（WHERE 子句只包含 B 类）
   - C+D > 30% → 不批量改，走逐条审核 + 人工
5. **不能用 savepoint 救 abort 的 conn** — PG fundamental（见 lesson 18）
6. **审计期双 SQL 交叉验证** — lesson 18 规则 1 同样适用本 lesson

**教训**：
- lesson 7+ silent-killer 警报持续命中：核心模块改动必须 5 smoke verify + 抽样验证
- lesson 18（audit 数字错）+ lesson 19（批量改前不验证）= "destructive 前必验证"系列
- lesson 13（silent 假设错）又中招：71,045 条全加 `_1` 是 silent 假设"加了就好"

**关联**：
- Phase 1 抽样验证脚本：`scripts/validate_cqggzy_urls.py`（新）
- 71,045 条缺 `_1` URL 中，实际只需修"B 类"（估算 60-80%）
- C 类死链可能是项目方主动下架（不归我们管），但要标记避免误导用户

## 20. silent DB 端口假设错 (2026-07-17, 02:40)

**事件**：写 `scripts/validate_cqggzy_urls.py` 时，DB_URL 默认值 silent 假设 `localhost:5432`（PG 默认端口），实际 **PG 容器端口映射是 `5435`**（前面 audit 已查证：lesson 13 silent 假设错）。
- 跑 smoke verify 1 → `asyncpg.exceptions.TimeoutError` 60s 超时
- **silent-killer**：lesson 7+ 警报**第 4 次**命中（前 3 次：PR #77 keywords_service / lesson 18 audit 数字 / lesson 19 批量改前不验证）

**坑点**：
- PG 默认端口 = 5432，但 Docker compose 可映射任意端口
- 我前面 audit 阶段用 `docker exec ... psql -U root -d tender_scraper` 成功，但 host 端 asyncpg 直连要走 `localhost:5435`
- silent 假设"5432 默认端口"是 **DB URL 配置的 silent-killer**

**规则**：
1. **任何 DB URL 配置前必查实际端口** — 用 `docker port <container>` 或 `docker inspect ... NetworkSettings.Ports`
2. **DB_URL 默认值用 env override** — `os.getenv("DATABASE_URL", default)` 但 default 必须是实际值
3. **脚本写完必跑 smoke verify** — lesson 7+ 第 1 规则
4. **silent-killer 警报累计 4 次** — 必须每条 lesson 即时落档 + 下次必先查

**教训**：
- lesson 13（silent 假设错）**核心案例**: audit 阶段查证端口是 5435，但写脚本时 silent 默认 5432
- lesson 7+ 系列 lesson 18/19/20 = "数据层 silent-killer" 三连击 (audit 数字 / 批量前验证 / DB 端口)
- lesson 1 铁律"用真实数据" — DB URL 也必须用真实端口

**关联文件**：
- `scripts/validate_cqggzy_urls.py` DB_URL 默认值已修（5432 → 5435）
- 其他 DB 调用是否也有 silent 5432 假设？待 audit: `app/database/async_models.py:24`, `app/database/db.py`, `scripts/`

## 21. silent-killer 5 连击 — 凌晨 D-2 不可行 (2026-07-17, 02:42)

**事件**: 按 D-1.5 mini-spec 执行 D-2 (commit 1: validate 脚本 + lessons), smoke verify 1 连续失败 3 次:
- **第 1 次**: `TimeoutError` → 端口错 (5432 → 5435) → lesson 20
- **第 2 次**: `InvalidPasswordError` → password 错, silent 假设 `root123`
- **第 3 次**: `InvalidPasswordError` → 即使改成 `root123` 还是错, **因为 PG 容器内部 localhost 用 trust auth, 真实密码是 initdb 时设置的, env var `POSTGRES_PASSWORD=root123` 不影响已有 PG 实例**

**真相**（刚发现，pg_hba.conf + docker exec 验证）:
```
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
host all all all scram-sha-256
```
- `localhost` (127.0.0.1) 走 `trust` (无密码)
- 其他 host 走 `scram-sha-256` (需 initdb 时设置的密码)
- **host 端 asyncpg 直连 = scram-sha-256, 需要真正的 initdb 密码 (不是 env var)**
- `docker exec` 在容器内 = `localhost` = `trust` = 无密码 ✓
- 所以 host 端要密码, 容器内不要 — 这是 silent-killer 来源

**坑点**:
- lesson 13 silent 假设错连中 3 次（端口 / password 长度 / PG 初始化机制）
- lesson 7+ silent-killer **5 连击**：
  1. PR #77 keywords_service import 缺失（历史 7-7）
  2. lesson 18: audit 数字 silent-killer (61x 误差)
  3. lesson 19: 批量改前不验证
  4. lesson 20: silent DB 端口假设 (5432→5435)
  5. **lesson 21**: PG initdb vs env var 机制 silent-killer
- 凌晨 02:32 已连续工作 7.5 小时（16:58 起到现在），5 次 silent-killer 远超阈值

**解决方案**（用户拍板前不动）:
- **A. docker exec 在容器内跑脚本** — 绕开 host 端 password，最稳（推荐）
- **B. 查 initdb 真实密码** — 找历史 docker-compose / .env / 容器启动命令
- **C. 改 pg_hba.conf 加 host trust** — 影响生产，不推荐
- **D. D-3 停手** — 今晚已超负荷，留明早（最安全）

**规则**（lesson 21 增订）:
1. **PG 容器 auth 配置必查 pg_hba.conf** — `trust` vs `scram-sha-256` 是 silent-killer 陷阱
2. **PG initdb 时设置的密码 = 真实密码，env var 修改不影响已有实例**
3. **连续 silent-killer ≥3 必停** — lesson 7+ 阈值，不能 silent 继续
4. **凌晨 02:00 后 D 选项（动手修）风险高** — 睡眠不足判断力下降，建议 D-3
5. **docker exec 容器内是 PG 无密码的稳路径** — 适用只读 + 容器内 Python 场景

**教训**:
- lesson 13（silent 假设错）+ lesson 7+（silent-killer）是同一类陷阱的两面：假设 vs 警报
- **5 次 silent-killer 警示**: PG/DB 类任务必须**先查 docker inspect + pg_hba.conf**，不能 silent 假设
- 凌晨 2:32 强行 D-2 = 高风险，建议 D-3 明早来

**当前状态**（02:42 停手）:
- ✅ 备份完整: `projects_cqggzy_2026_07_16_pre_url_fix` (111,198) + `projects_ccgp_2026_07_16_pre_url_fix` (58)
- ✅ 新分支: `fix/cqggzy-url-and-detail-2026-07-17` (HEAD = `6b51401` from `refactor/slim-agents-md`)
- ✅ 写完 `scripts/validate_cqggzy_urls.py` (6359 bytes, 含 DB_URL 自动探测)
- ✅ Lessons 19/20/21 全部 append 到 `notes/lessons-learned.md`
- ❌ commit 1 **未 commit**（smoke verify 1 失败，lesson 7+ 规则）
- ❌ commit 2/3 **未做**（按 lesson 7+ 第 5 次命中规则停手）
- 📁 `.trash-2026-07-17-untracked/` 保留 3 untracked backup（openclaw-workspace-state.json + 专业分布图.html/.png）

**关联**:
- `scripts/validate_cqggzy_urls.py` 当前依赖 host 端 password，需用户拍板 A/B 方案
- commit 1 (validate 脚本 + lesson 19/20/21) **等用户拍板**才 commit

## 22. harvest_records 表 + 孤儿 lifespan silent-killer (2026-07-17, 13:32)

**事件**: smoke 2 verify 暴露 harvest_records 表不存在 → 所有 save_harvest_records 调用 silent fail

### Root cause (双层 silent-killer)
1. **DB 层**: `harvest_records` + `source_configs` 表自部署以来**从未创建**
2. **代码层**: `app/api/harvest_api.py:335-370` 定义了 lifespan + `await init_tables()` 但:
   - 这个 lifespan 在 `harvest_api.py` 自己的孤儿 FastAPI app 里 (`app = FastAPI(lifespan=lifespan)`)
   - 孤儿 app 从未被 import/run (`grep "harvest_api:app\|uvicorn.*harvest_api"` = 0 结果)
   - `web_server.py:36` 主 app **没传 lifespan**
3. **触发链**: 每次 save_harvest_records 调用 → `UndefinedTableError: relation "harvest_records" does not exist` → 被外层 try/except 吞掉 → silent fail
4. **历史影响**: 自部署以来所有 crawl history 数据全部漏存 (lesson 18 的"179 条被吞"也是同类机制)

### Fix (2 步)
- **Step 1 (热修)**: 手动 psql 跑 INIT_TABLES_SQL 建表 (commit 2351d48 后 hot-fix, 不入 git)
- **Step 2 (根因修)**: web_server.py 加 lifespan → startup 时 init_tables() 幂等调用

### 教训 (lesson 7+ 第 6 次命中)
- **孤儿 init 模式**: "模块定义了 init 函数 + lifespan，但 lifespan 挂错了 app 对象" 是高发 silent-killer
- **DB 表创建责任不清**: 老的 `db.py:_init_tables()` 只建 `projects` 表，新 `async_models.py:init_tables()` 建 `harvest_records` — 两套 init 系统**解耦**，老 init 跑了，新 init 没跑
- **smoke verify 价值**: lesson 19 fix 直接暴露此 bug，没 smoke verify 永远不会发现 → **fix 的连锁价值**
- **修法原则**: Step 1 (热修立刻 unblock) + Step 2 (根因修防止再发) **必须配套**
- **检测**: `grep -rn "lifespan\|init_tables" --include="*.py"` + 检查每个 lifespan 是否真的会被运行

### 关联 lesson
- lesson 7+: silent-killer 警报**持续命中** (DB 完整性 + audit 数字一致性 + 孤儿 init 是同一类陷阱)
- lesson 19: lesson 19 fix 间接暴露此 bug — **fix 的连锁价值得到验证**
