# Audit Logging System Implementation

## Overview
This document describes the audit logging system added to the FastAPI AI Gateway.

## Changes Made

### 1. Database Layer (app/database.py)

#### New Table: `audit_log`
```sql
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,  -- INTEGER PRIMARY KEY AUTOINCREMENT for SQLite
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    action VARCHAR(255),
    user_id VARCHAR(255),
    ip_address VARCHAR(45),
    method VARCHAR(10),
    path TEXT,
    request_body TEXT,
    response_status INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

#### New Functions:
- `init_audit_log_table()` - Initializes the audit_log table
- `log_request(action, user_id, ip, method, path, body, status, latency)` - Logs a request
- `get_audit_logs(filters, limit, offset)` - Retrieves audit logs with filtering
- `cleanup_old_logs(days_to_keep)` - Removes old audit logs
- `get_audit_stats(start_date, end_date)` - Gets statistics about audit logs

### 2. Application Layer (app/main.py)

#### AuditMiddleware Class
- Intercepts all HTTP requests
- Captures request metadata (method, path, IP, user)
- Logs requests to audit trail
- Calculates request latency
- Supports sensitive field detection

#### Sensitive Field Redaction
The `sanitize_request_body()` function redacts sensitive fields:
- password, passwd, pwd
- secret, token, api_key, apikey
- access_token, refresh_token
- auth, authorization
- credential, private_key, secret_key

#### API Endpoints Added:

1. **GET /api/audit/logs** - Get audit logs
   - Query parameters: action, user_id, method, path, status, start_date, end_date, limit, offset
   - Requires admin authentication
   - Returns paginated list of audit logs

2. **GET /api/audit/stats** - Get audit statistics
   - Query parameters: start_date, end_date
   - Returns: total_requests, by_action, by_method, avg_latency_ms, min_latency_ms, max_latency_ms, error_count, error_rate
   - Requires admin authentication

3. **POST /api/audit/cleanup** - Clean up old logs
   - Form parameter: days_to_keep (default: 30)
   - Requires admin authentication
   - Returns number of deleted entries

## Usage Examples

### Get all audit logs (last 100)
```bash
curl -H "Cookie: admin_token=YOUR_TOKEN" http://localhost:8000/api/audit/logs
```

### Get logs filtered by action
```bash
curl -H "Cookie: admin_token=YOUR_TOKEN" "http://localhost:8000/api/audit/logs?action=API_CALL"
```

### Get audit statistics
```bash
curl -H "Cookie: admin_token=YOUR_TOKEN" http://localhost:8000/api/audit/stats
```

### Clean up logs older than 7 days
```bash
curl -X POST -H "Cookie: admin_token=YOUR_TOKEN" -F "days_to_keep=7" http://localhost:8000/api/audit/cleanup
```

## Security Considerations

1. All audit endpoints require admin authentication
2. Sensitive fields in request bodies are automatically redacted
3. IP addresses are logged for security auditing
4. The audit system itself logs failures without breaking the main request flow

## Performance Notes

- Audit logging is non-blocking
- Health check endpoints (/health, /) are excluded from logging to reduce noise
- Request body content is not captured (only size) to minimize overhead
- Latency is calculated for each request

## Database Compatibility

The audit logging system supports both:
- SQLite (default for local development)
- PostgreSQL (production deployments)

## File Locations

- Source: `/home/lewellyn/aigateway/ai-gateway/app/`
- Backup: `/home/lewellyn/aigateway/ai-gateway/app/main.py.backup`
- Workspace: `/home/lewellyn/.openclaw/workspace/ai-gateway-improved/app/`
