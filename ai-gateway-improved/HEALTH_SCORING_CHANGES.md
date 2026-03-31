# 多维度健康评分系统实现说明

## 概述
为 FastAPI AI Gateway 添加了完整的多维度健康评分系统，用于智能评估和选择最优账户。

## 数据库变更

### proxy_accounts 表新增字段

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `concurrent_requests` | INTEGER | 0 | 当前并发请求数 |
| `max_concurrent` | INTEGER | 10 | 最大并发限制 |
| `priority` | INTEGER | 1 | 优先级权重 |
| `last_error` | TEXT | NULL | 最后错误信息 |

## 健康评分算法

### 计算公式
```
score = (success_rate * 0.4) + (latency_score * 0.3) + (availability * 0.3)
```

### 组成部分
1. **success_rate** (成功率): `success_count / (success_count + fail_count)`
   - 无记录时默认为 1.0
   - 权重：40%

2. **latency_score** (延迟评分): `max(0, 1 - (avg_latency / max_latency_threshold))`
   - 默认阈值：5000ms
   - 权重：30%

3. **availability** (可用性): `1 if status='active' else 0`
   - 权重：30%

## 新增 API 端点

### 1. 获取账户健康评分
```http
GET /api/pool/{source}/score?max_latency=5000
```
**响应示例:**
```json
{
  "status": "success",
  "data": {
    "source": "chatgpt",
    "health_scores": [
      {
        "account_id": 1,
        "score": 0.85,
        "success_rate": 0.95,
        "latency_score": 0.82,
        "availability": 1,
        "concurrent_requests": 2,
        "max_concurrent": 10,
        "priority": 1,
        "last_error": null,
        "account_info": {
          "id": 1,
          "source": "chatgpt",
          "account_index": 0,
          "status": "active",
          "success_count": 100,
          "fail_count": 5,
          "avg_latency": 245.5
        }
      }
    ]
  }
}
```

### 2. 获取最优账户
```http
GET /api/pool/{source}/best?strategy=health_score
```
**策略选项:**
- `health_score`: 按健康评分选择 (默认)
- `priority`: 按优先级权重选择
- `round_robin`: 传统轮询选择

**响应示例:**
```json
{
  "status": "success",
  "data": {
    "account": {
      "id": 1,
      "source": "chatgpt",
      "account_index": 0,
      "status": "active"
    },
    "health_score": 0.85,
    "strategy_used": "health_score"
  }
}
```

### 3. 更新并发计数
```http
POST /api/pool/{source}/account/{account_id}/concurrent
Content-Type: application/x-www-form-urlencoded

delta=1  # +1 增加，-1 减少
```

### 4. 更新账户配置
```http
PUT /api/pool/{source}/account/{account_id}/config
Content-Type: application/json

{
  "max_concurrent": 20,
  "priority": 5
}
```

## 新增数据库函数

### database.py 新增函数

1. **`calculate_account_health(account_id, max_latency_threshold=5000)`**
   - 计算单个账户的健康评分
   - 返回详细评分细目

2. **`get_best_account(source, strategy='health_score')`**
   - 根据策略获取最优账户
   - 支持多种选择策略

3. **`get_account_health_batch(source, max_latency_threshold=5000)`**
   - 批量获取所有账户的健康评分

4. **`increment_concurrent(account_id, delta=1)`**
   - 增减并发计数

5. **`update_account_error(account_id, error_message)`**
   - 更新账户错误信息

6. **`update_account_concurrent_limit(account_id, max_concurrent)`**
   - 更新最大并发限制

7. **`update_account_priority(account_id, priority)`**
   - 更新优先级权重

## 使用示例

### Python 示例
```python
import requests

# 获取账户健康评分
response = requests.get(
    'http://localhost:8000/api/pool/chatgpt/score',
    headers={'Authorization': 'Bearer YOUR_API_KEY'}
)
scores = response.json()

# 获取最优账户
response = requests.get(
    'http://localhost:8000/api/pool/chatgpt/best?strategy=health_score',
    headers={'Authorization': 'Bearer YOUR_API_KEY'}
)
best_account = response.json()

# 更新并发计数 (请求开始时 +1, 结束时 -1)
requests.post(
    f'http://localhost:8000/api/pool/chatgpt/account/{account_id}/concurrent',
    data={'delta': 1},
    headers={'Authorization': 'Bearer YOUR_API_KEY'}
)
```

## 文件位置
- 源代码：`/home/lewellyn/aigateway/ai-gateway/app/database.py`
- 源代码：`home/lewellyn/aigateway/ai-gateway/app/main.py`
- 同步副本：`/home/lewellyn/.openclaw/workspace/ai-gateway-improved/`

## 注意事项
1. 健康评分系统自动集成到现有的代理池管理中
2. 所有新字段在数据库表创建时自动添加
3. 现有账户的新字段使用默认值
4. 建议在生产环境部署前进行充分测试
