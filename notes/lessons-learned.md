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
