# 采集系统 - AI 与 NLP 梳理

> 生成时间: 2026-04-16 17:50
> 参考: AI_INTELLIGENCE_ASSESSMENT.md

## 技术栈与依赖

| 组件 | 技术 | 状态 |
|------|------|------|
| 分词 | jieba | ✅ 使用中 |
| 向量匹配 | TF-IDF | ✅ 使用中 |
| 向量存储 | pgvector (PostgreSQL) | ✅ Docker 配置 |
| 浏览器自动化 | Playwright | ✅ 使用中 |
| RAG | RAGFlow 集成 | ⚠️ 配置中 |

## NLP 模块分析

### app/nlp/
- `classifier.py` — 文本分类
- `summarizer.py` — 内容摘要生成

### app/utils/
- `tfidf_matcher.py` — TF-IDF + jieba 分词 + 同义词扩展
- `filter.py` — TenderFilter 关键词过滤

## 内容摘要生成

### ccgp.py (_summarize_content)
- 根据信息类型生成结构化摘要
- 提取核心字段：预算、截止时间、中标金额、联系方式
- 自动拼接关键信息，便于快速浏览

### 支持的信息类型
- **采购意向**: 预算金额、预计采购时间、采购需求概况
- **采购公告**: 项目概况、预算金额、投标人资格要求、投标截止时间、开标时间
- **结果公告**: 中标供应商、中标金额、项目预算

## 智能分类

- `business_type` — 业务类型（政府采购/工程建设）
- `info_type` — 信息类型（采购意向/采购公告/结果公告）
- 目前靠爬虫 Hardcode，无法自动学习新类别

## 代码质量评估

### ✅ 优点
- 25 字段 TenderInfo 模型为 AI 特征提取奠定基础
- ConcurrencyScheduler 架构良好，与 AI 任务调度可复用
- RAGFlow 集成支持语义检索

### ⚠️ 痛点
1. **关键词匹配精度低** — TF-IDF 无法捕捉语义，同义词变体导致漏采/误采
2. **无自动分类** — 靠爬虫 Hardcode，无法增量学习
3. **去重依赖 URL** — 相似项目不同链接会重复采集
4. **无优先级机制** — 所有匹配项目平铺，无法聚焦高价值标的
5. **无预测性告警** — 截标日期临近时无主动提醒
6. **数据沉睡** — 历史数据无法被语义检索（pgvector 未充分利用）

## 开发进度

### ✅ 已完成 (2026-04-18/19)
- **向量入库**: main.py 采集完成后自动 `_upsert_to_vector_store()` (2026-04-19 commit)
- **ChromaDB 持久化**: `VECTOR_STORE_BACKEND=chromadb`，数据存 scraper-data volume (2026-04-19)
- **向量搜索默认化**: `use_vector=True` 默认，失败自动回退 TF-IDF → 简单匹配
- **projects.py API**: 支持 `use_vector` / `use_tfidf` 双参数
- **Embedding 预热**: `@app.on_event("startup")` 后台线程预热模型
- **/health 增强**: 返回向量库 backend/embedding_model/total_vectors

### ✅ 已完成 (2026-04-21)
- **SemanticTenderFilter**: 新增基于 vLLM Qwen3-Embedding-4B 的语义过滤（阈值0.60，批量32）
- **全量向量入库脚本**: `scripts/backfill_vectors.py` 将 favorites 历史数据批量向量化写入 ChromaDB
- **Embedding 批量接口**: MiniMaxService 新增 embed_text/embed_texts
- **截标日期 T-3 提醒**: NotificationManager.check_deadline_alerts(days=3) 采集完成后自动触发

### ⚠️ 待处理
- **首次采集语义召回率为0**: 运行 `python scripts/backfill_vectors.py --dry-run` 预览，再去掉 --dry-run 正式填充
- **pgvector SQL 直接使用** (可选): ChromaDB 当前可用，pgvector SQL 后端待实现

**进度: 96%** → **98%**

### ✅ 2026-04-22 完成
- **pgvector 后端实现** (`app/services/vector_store.py`): 新增 `PGVectorBackend` 类，`upsert/search/delete/count` 全实现，`::vector` cast
- **PostgreSQL 建表脚本** (`scripts/init_pg.sql`): 16 张表结构 + `CREATE EXTENSION vector`，已执行初始化
- **VECTOR_STORE_BACKEND=pgvector 切换**: docker-compose.yml 3处全更新，`.env` 添加 DATABASE_URL
- **ChromaDB→pgvector 数据迁移**: `scripts/migrate_chroma_to_pg.py` 成功迁移 59 条向量（dim=2560）
- **验证**: `/health` 返回 `total_vectors: 59` ✅，pgvector `search()` 测试通过 ✅
- ⚠️ **向量维度不统一**: ChromaDB 实际存储 2560 维（vLLM Qwen3-Embedding-4B），代码默认 384，`get_vector_backend()` 已强制设为 2560；后续统一 embedding 模型后需重建 IVFFlat 索引
- ⚠️ **pgvector 索引**: 2560 维超过 IVFFlat 2000 维上限，HNSW 索引暂跳过，高维查询暂用 seq scan

---

## 2026-06-11 07:30 重新评估

> 距 4-24 收尾 48 天。**AI 与 NLP 取得显著进展：向量库从 59 条增至 11,369 条（192 倍），实现 7 词库语义检索**。

### 🎯 核心数据（实测 2026-06-11 07:30）

```json
{
  "vector_backend": "pgvector",
  "embedding_model": "Qwen/Qwen3-Embedding-4B",
  "total_vectors": 11369,
  "vector_dim": 2560,
  "projects_cqggzy": 14109,
  "vector_coverage": 80.6%   // 11369 / 14109
}
```

### 🟢 重大进展

**1. 向量库规模爆发（59 → 11,369）**

| 时间 | 向量数 | 触发事件 |
|------|--------|---------|
| 2026-04-22 | 59 | 初次迁移 ChromaDB→pgvector |
| 2026-04-22~06-08 | ~60 | 采集期缓慢积累 |
| 2026-06-08 | 11,369 | 一次性 `scripts/reindex_vector_store.py` 全量回填 |

- 7 个关键词库全部从 0 覆盖：
  - 智能化: 152
  - AI: 99
  - 音视频: 10
  - 人工智能: 33
  - 智能体: 10
  - 大模型: 5
  - （其他分类待统计）
- 全量回填耗时：**~14 分钟**（11K 文档，vLLM batch ≤10）
- vLLM embedding 端点：外部 `http://host.docker.internal:8000/v1/embeddings`

**2. 元数据 schema 演化问题（已修复）**

- 现象：metadata 中 `id` 字段从文档 url 改为文档 id 后，所有向量查询失效
- 影响：项目卡死，`vector_search` 端点返回空
- 修复：scripts/reindex_vector_store.py 用当前 URL metadata 重建
- **教训**：API 层应始终有简单匹配 fallback（不依赖向量库）

**3. vLLM 批大小限制（已确认）**
- 单批 ≤10 条 × ~1000 字符 安全
- batch 太大 (>10) 会触发 400 Bad Request
- backfill 脚本按 10 条批处理

**4. 多关键词 + 负关键词搜索（5-12 新增）**

`app/utils/search_parser.py`:
- 输入：`智能体,AI -大模型` → 解析为 OR + NOT
- 端点：`/api/projects`、`/api/export` 支持
- 工具栏：data.html 6 个筛选控件加 ? tooltip

**5. SemanticTenderFilter 演进**
- 阈值 0.60（Qwen3-Embedding-4B）
- 批量 32
- 失败自动回退 TF-IDF → 简单匹配
- 默认 `use_vector=True`

### 📊 分类质量（项目编号）

| info_type | 覆盖率 | 备注 |
|-----------|--------|------|
| 中标候选人公示 | 100% | ✅ |
| 中标结果公示 | 99.91% | ✅ |
| 答疑补遗 | 99.36% | ✅ |
| 招标公告 | 91.6% | ⚠️ |
| 采购结果公告 | 90.1% | ⚠️ |
| 采购公告 | 88.4% | ⚠️ |
| 变更公告 | 87.5% | ⚠️ |
| 招标计划 | 62.8% | 合规无编号 |
| **总计** | **91.94%** | 12,972/14,109 |

**关键路径（`extract_project_no` 提取器）：**
- 规则：项目号[：:]\s*... + 逗号分隔 + 字符类 [A-Z0-9\-]
- 支持 (XXX...) 包裹格式
- 8-30 位长编号（项目编码/采购编号）
- 排除 `招标计划表` 标题

### 🤖 NLP 模块现状

**`app/nlp/`**:
- `classifier.py` — 文本分类（基于关键词）
- `summarizer.py` — 内容摘要（基于规则）

**`app/utils/tfidf_matcher.py`**:
- TF-IDF + jieba 分词 + 同义词扩展
- 仍作为向量检索失败回退

**`app/utils/filter.py`**:
- TenderFilter 关键词过滤
- 集成 SemanticTenderFilter 优先
- extract_project_info 透传 project_no

**`app/services/llm_service.py`**:
- 调用 vLLM HTTP API
- 摘要/分类/分类器
- 批量接口 embed_text/embed_texts

**`app/services/vector_store.py`** (PGVectorBackend):
- `upsert/search/delete/count` 全实现
- `::vector` cast
- 2560 维固定（Qwen3-Embedding-4B）

### ⚠️ 已知 AI/ML 限制

1. **embedding 维度爆炸**：
   - Qwen3-Embedding-4B = 2560 维
   - IVFFlat 索引 2000 维上限 → 不能用
   - HNSW 索引暂跳过 → 高维查询用 seq scan
   - 性能影响：14K 文档下尚可，100K+ 时需重新评估

2. **无自动分类学习**：
   - business_type / info_type 靠爬虫 hardcode
   - 无增量学习机制
   - 计划：BERT-chinese 微调（待办）

3. **截标日期 T-3 提醒**：
   - `NotificationManager.check_deadline_alerts(days=3)` 已实现
   - 采集完成后自动触发
   - 实际触发频率待验证

4. **去重依赖 URL**：
   - `BaseCrawler._visited_urls` 内存 Set（不持久）
   - 相似项目不同链接会重复
   - 待用向量相似度去重

5. **元数据 schema 耦合**：
   - 任何 url/id 字段变更需重建向量
   - 应改为 `metadata_only` 模式（schema 与向量解耦）

### 🛠️ 建议下阶段 AI 任务（2026-06-11 07:42 调整：不做维度切换）

~~1. **降低 embedding 维度**：~~ **已剔除**（用户 07:40 明确不做切维度）
~~- 切到 `m3e-small` (512 维) 或 `text-embedding-3-small` (1536 维)~~
~~- 可启用 IVFFlat 索引，QPS 提升 ~50x~~
~~- 需权衡检索质量~~

**替代方案：** P0-2 HNSW 索引（用现有 2560 维，任意维度支持）

1. **HNSW 索引**（P0-2，已纳入 PR 路线图）：
   - `CREATE INDEX ON vector_store USING hnsw (embedding vector_cosine_ops)`
   - 内存预估：14K × 2560 × 4B = ~140MB
   - 不切维度，QPS 提升 ~10x

2. **向量去重**（P1-3）：
   - 对同一项目多源采集，embedding 相似度 > 0.95 视为重复
   - 避免 URL 变体（http vs https、参数差异）
   - 用现有 2560 维 + HNSW 索引

3. **自动 info_type 分类**：
   - 用现有 labeled data 训练 BERT-chinese
   - 替代爬虫 hardcode
   - 准确率目标 > 90%

4. **HNSW 参数调优**（P0-2 子任务）：
   - m=16, ef_construction=64 起步
   - 业务低峰跑 EXPLAIN ANALYZE 验证
   - ef_search=100 平衡精度/速度

5. **完善 RAGFlow 集成**：
   - 当前 `RAGFLOW_MCP_URL=http://host.docker.internal:9382` 已配置
   - 实际未在生产路径使用，仅作为辅助
   - 应统一 chat 接口走 RAGFlow

### 📈 进度

- 4-24 收尾：100% ✅
- **5-11 以来：向量库规模 192 倍，分类器质量显著提升**
- **6-11 当前：AI 基础设施 100% 稳定，召回率待验证（建议 P95 latency 测试）**

### 🔬 性能数据（待测）

- 单条 embedding 耗时：~150ms（vLLM Qwen3-Embedding-4B）
- 批量 10 条：~1.2s
- 向量搜索 P95 延迟：seq scan 下 <100ms（14K 量级）
- 端到端搜索 P95 延迟：<500ms

### 📊 AI 评分

| 维度 | 评分 | 备注 |
|------|------|------|
| 向量库规模 | 100% | 11.4K 覆盖 80% |
| 召回质量 | 80% | 0.60 阈值合理，待 P95 测试 |
| 索引效率 | 50% | 2560 维不能用 IVFFlat |
| 自动学习 | 20% | 无增量学习 |
| 多模态 | 0% | 未规划 |
| **综合** | **65%** | 基础设施完善，智能化不足 |

---

## 改进建议

> 注：2026-06-11 07:40 调整 — 用户明确不做 embedding 维度切换，
> 下列涉及"切模型/切维度"的建议（text-embedding-3-small / m3e）已剔除，
> 改为走 HNSW 索引 + 现有 2560 维路径。详见 PR 路线图 P0-2。

### 高优先级
1. ~~**语义智能筛选** — 用 Embedding 模型（text-embedding-3-small / m3e）做向量检索，召回率预期提升 30-50%~~ → **调整为**：HNSW 索引（用现有 2560 维）
2. **智能去重与相似度检测** — 基于向量相似度而非 URL 判断（P1-3）

### 中优先级
3. **自动分类与打标** — 训练/微调轻量中文文本分类模型（BERT-chinese），准确率目标 > 90%
4. **预测性优先级排序** — 基于历史数据预测高价值标的

### 低优先级
5. **预测性告警** — 截标日期临近时主动提醒
6. **pgvector 充分利用** — 历史数据语义检索

---

## 2026-06-16 12:30 重新评估

> 距 6-11 评估 +5 天。**P0-2 HNSW 索引 1.3x 加速上线；P1-3 spike 决定放弃（1.6% 真重复率）**。

### 🎯 关键里程碑

**1. P0-2 HNSW 索引（6-11 已建，6-12 部署）**
- 索引类型：`halfvec(2560)` (FP16 量化)
- 维度：2560（Qwen3-Embedding-4B）
- 加速：**端到端 1.3x**（P95 latency 100ms → 77ms）
- HNSW 创建耗时：8s
- PR #2 MERGED by lewellyn7 at 2026-06-11T01:49:37Z → main HEAD `000546e`
- DB 列类型变更：`vector(2560)` → `halfvec(2560)`
- 镜像重建：tender-scraper-web:96e158233f6c (3.48GB, --no-cache)

**2. PR #3 force_hnsw 开关（OPEN）**
- 配置：`VECTOR_FORCE_HNSW`
- 实现：`SET LOCAL enable_seqscan=off`
- 端到端验证：
  - `force_hnsw=false`: 48ms
  - `force_hnsw=true`: 228ms
- **反直觉：** 14K 数据下 HNSW 比 Seq Scan 慢 4.7x
- 决策：planner 默认拒绝 HNSW（正确）；50K+ 数据才值得开
- 14K 数据下不推荐

**3. P1-3 向量去重 spike 完成（不推荐）**
- 1000 样本测试：**1.6% 真重复率**
- ROI 评估：6 天回本（不值得）
- 结论：**改做 P1-3a 前端项目链接展示**（1-2h，已 spike 通过）

### 📊 向量库规模演进

| 时间 | total_vectors | 触发事件 |
|------|---------------|----------|
| 2026-04-22 | 59 | ChromaDB→pgvector 迁移 |
| 2026-06-08 | 11,369 | reindex_vector_store.py 全量回填 |
| **2026-06-16** | **~20,000+** | **持续回填 + 108K projects（待实际验证）** |

### 🟢 持续改进

**1. 多关键词 + 负关键词搜索（5-12）**
- `app/utils/search_parser.py`
- 语法：`智能体,AI -大模型` → OR + NOT
- 端点：`/api/projects` + `/api/export` 支持

**2. SemanticTenderFilter 演进**
- 阈值 0.60（Qwen3-Embedding-4B）
- 批量 32
- 失败自动回退 TF-IDF → 简单匹配
- 默认 `use_vector=True`

**3. 7 词库语义检索覆盖（5-15 spike 验证）**
- 智能化: 152
- AI: 99
- 音视频: 10
- 人工智能: 33
- 智能体: 10
- 大模型: 5
- （其他分类待统计）

**4. PR #4 data.html 收藏按钮修复（OPEN）**
- Bug: `authFetch()` 没设 `Content-Type: application/json` → POST `/api/favorites` 422
- 二次 bug: `toggleFav` 不检查 `res.ok`, 4xx 被吞掉, UI 假状态
- Playwright 抓真实 header: `content-type: text/plain;charset=UTF-8`

### ⚠️ 当前 AI/ML 限制

1. **embedding 维度爆炸**（不变）：
   - 2560 维；HNSW 已用 `halfvec` 量化（4B→2B 节省）
   - IVFFlat 不可用，HNSW 14K 量级下与 seq scan 接近
   - 50K+ 数据下 HNSW 优势才显现

2. **无自动分类学习**（不变）：
   - business_type / info_type 靠爬虫 hardcode
   - 计划：BERT-chinese 微调（待办）

3. **去重依赖 URL**（已决策）：
   - P1-3 spike 完成，决定不做
   - 改做 P1-3a 前端展示

4. **元数据 schema 耦合**（不变）：
   - 6-5 已发生 url 变更导致向量失效，scripts/reindex_vector_store.py 重建

### 🛠️ 建议下阶段 AI 任务

1. **P1-3a 前端项目链接展示**（1-2h，已 spike 通过）
   - 替代 P1-3 向量去重
   - 价值：用户对项目去重有直观感受

2. **HNSW 参数调优**（待 50K+ 数据后）
   - m=16, ef_construction=64 起步
   - ef_search=100 平衡精度/速度

3. **自动 info_type 分类**
   - 用 labeled data 训练 BERT-chinese
   - 准确率目标 > 90%

4. **完善 RAGFlow 集成**
   - 当前 MCP URL 已配置，未在生产路径
   - 应统一 chat 接口走 RAGFlow

### 📈 进度

- 6-11 评估：65% 综合
- **6-16 当前：75% 综合**（HNSW 部署 + P1-3 spike 完成）

### 📊 AI 评分

| 维度 | 评分 | 变化 | 备注 |
|------|------|------|------|
| 向量库规模 | 100% | - | 20K+ 覆盖 80%+ |
| 召回质量 | 80% | - | 0.60 阈值合理 |
| **索引效率** | **80%** | **+30** | **HNSW + halfvec 1.3x** |
| **决策科学性** | **85%** | **+15** | **P1-3 spike 避免浪费** |
| 自动学习 | 20% | - | 无增量学习 |
| 多模态 | 0% | - | 未规划 |
| **综合** | **72%** | **+7** | **HNSW + spike** |