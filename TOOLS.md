# TOOLS.md - Tool Configuration & Notes

> Document tool-specific configurations, gotchas, and credentials here.

---

## Credentials Location

All credentials stored in `.credentials/` (gitignored):
- `example-api.txt` — Example API key

---

## RAGFlow

**Status:** ⚙️ 配置中

**Configuration:**
```
URL: http://localhost:8080 (本地实例)
凭证：.credentials/ragflow.txt
API Key 位置：RAGFlow Web 界面 → 用户头像 → API Keys
```

**功能:**
- 创建和管理知识库 (datasets)
- 上传文档到知识库
- 执行 RAG 查询
- 文档分块和解析

**常用命令:**
```bash
# 列出所有知识库
node scripts/ragflow.js datasets

# 创建知识库
node scripts/ragflow.js create-dataset --name "My Knowledge Base"

# 上传文档
node scripts/ragflow.js upload --dataset DATASET_ID --file article.md

# 查询
node scripts/ragflow.js chat --dataset DATASET_ID --query "查询内容"
```

**Gotchas:**
- 确保 RAGFlow 服务已启动并可访问
- API Key 需要从 RAGFlow Web 界面获取
- 文档上传后需要触发解析才能查询

---

## Writing Preferences

[Document any preferences about writing style, voice, etc.]

---

## What Goes Here

- Tool configurations and settings
- Credential locations (not the credentials themselves!)
- Gotchas and workarounds discovered
- Common commands and patterns
- Integration notes

## Why Separate?

Skills define *how* tools work. This file is for *your* specifics — the stuff that's unique to your setup.

---

*Add whatever helps you do your job. This is your cheat sheet.*
