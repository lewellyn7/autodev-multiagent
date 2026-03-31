# 多维度健康评分系统 - 实现完成

## ✅ 已完成的任务

### 1. 数据库表扩展 (proxy_accounts)
已添加以下字段：
- `concurrent_requests INTEGER DEFAULT 0` - 当前并发请求数
- `max_concurrent INTEGER DEFAULT 10` - 最大并发限制
- `priority INTEGER DEFAULT 1` - 优先级权重
- `last_error TEXT` - 最后错误信息

### 2. 健康评分算法实现
```python
score = (success_rate * 0.4) + (latency_score * 0.3) + (availability * 0.3)
```
- **success_rate**: success_count / (success_count + fail_count)
- **latency_score**: max(0, min(1, 1 - (avg_latency / max_latency_threshold)))
- **availability**: 1 if status='active' else 0

### 3. 新增数据库函数 (database.py)
- `calculate_account_health(account_id, max_latency_threshold=5000)` - 计算账户健康评分
- `get_best_account(source, strategy='health_score')` - 获取最优账户
- `get_account_health_batch(source, max_latency_threshold=5000)` - 批量获取健康评分
- `increment_concurrent(account_id, delta=1)` - 更新并发计数
- `update_account_error(account_id, error_message)` - 更新错误信息
- `update_account_concurrent_limit(account_id, max_concurrent)` - 更新并发限制
- `update_account_priority(account_id, priority)` - 更新优先级

### 4. 新增 API 端点 (main.py)

#### GET /api/pool/{source}/score
获取账户池健康评分
```bash
curl -X GET "http://localhost:8000/api/pool/chatgpt/score" \
  -H "Authorization: Bearer YOUR_KEY"
```

#### GET /api/pool/{source}/best
获取最优账户
```bash
curl -X GET "http://localhost:8000/api/pool/chatgpt/best?strategy=health_score" \
  -H "Authorization: Bearer YOUR_KEY"
```

#### POST /api/pool/{source}/account/{account_id}/concurrent
更新并发计数
```bash
curl -X POST "http://localhost:8000/api/pool/chatgpt/account/1/concurrent" \
  -H "Authorization: Bearer YOUR_KEY" \
  -d "delta=1"
```

#### PUT /api/pool/{source}/account/{account_id}/config
更新账户配置
```bash
curl -X PUT "http://localhost:8000/api/pool/chatgpt/account/1/config" \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_concurrent": 20, "priority": 5}'
```

## 📁 文件位置
- 主代码：`/home/lewellyn/aigateway/ai-gateway/app/database.py`
- 主代码：`/home/lewellyn/aigateway/ai-gateway/app/main.py`
- 工作区备份：`/home/lewellyn/.openclaw/workspace/ai-gateway-improved/`

## 🔍 验证
- ✅ 语法检查通过
- ✅ 数据库表结构已更新
- ✅ 健康评分函数已实现
- ✅ API 端点已添加
- ✅ 文件已同步到工作区

## 📝 使用说明

### 示例：获取并使用最优账户
```python
import requests

# 1. 获取健康评分
response = requests.get(
    'http://localhost:8000/api/pool/chatgpt/score',
    headers={'Authorization': 'Bearer YOUR_KEY'}
)
scores = response.json()['data']['health_scores']
print(f"账户数量：{len(scores)}")
for s in scores:
    print(f"账户 {s['account_info']['account_index']}: 评分 {s['score']}")

# 2. 获取最优账户
response = requests.get(
    'http://localhost:8000/api/pool/chatgpt/best?strategy=health_score',
    headers={'Authorization': 'Bearer YOUR_KEY'}
)
best = response.json()['data']
print(f"最优账户 ID: {best['account']['id']}, 健康分：{best['health_score']}")

# 3. 请求开始时增加并发计数
requests.post(
    f'http://localhost:8000/api/pool/chatgpt/account/{best["account"]["id"]}/concurrent',
    data={'delta': 1},
    headers={'Authorization': 'Bearer YOUR_KEY'}
)

# ... 执行业务请求 ...

# 4. 请求结束时减少并发计数
requests.post(
    f'http://localhost:8000/api/pool/chatgpt/account/{best["account"]["id"]}/concurrent',
    data={'delta': -1},
    headers={'Authorization': 'Bearer YOUR_KEY'}
)
```

## ⚠️ 注意事项
1. 首次运行会自动创建新字段
2. 现有账户的新字段使用默认值
3. 建议在生产环境部署前充分测试
4. 健康评分阈值可通过参数调整

---
实现完成时间：2026-03-31
