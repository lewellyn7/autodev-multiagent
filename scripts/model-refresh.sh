#!/usr/bin/env bash
# =============================================================================
# Auto Model Refresh Script
# Run via cron: 0 6 * * * /home/lewellyn/aigateway/ai-gateway/scripts/model-refresh.sh
# =============================================================================
set -e

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-password}"

echo "[$(date)] Starting model refresh..."

# Login to get admin session
LOGIN_RESP=$(curl -s -c /tmp/ gateway_cookies.txt -X POST "${GATEWAY_URL}/login" \
    -d "username=${ADMIN_USER}&password=${ADMIN_PASS}" \
    -H "Content-Type: application/x-www-form-urlencoded")

if ! echo "$LOGIN_RESP" | grep -q "success"; then
    echo "[$(date)] ❌ Login failed"
    exit 1
fi

echo "[$(date)] ✅ Authenticated"

# Refresh each source
SOURCES="chatgpt claude qwen deepseek moonshot openai gemini"

for source in $SOURCES; do
    echo "[$(date)] Fetching models for: $source"
    RESP=$(curl -s -b /tmp/gateway_cookies.txt -X POST "${GATEWAY_URL}/api/models/fetch" \
        -d "source=${source}" \
        -H "Content-Type: application/x-www-form-urlencoded")
    
    if echo "$RESP" | grep -q '"status":"success"'; then
        echo "[$(date)] ✅ $source: $(echo $RESP | jq -r '.msg')"
    else
        echo "[$(date)] ⚠️  $source: $(echo $RESP | jq -r '.msg // "unknown error"')"
    fi
done

# Cleanup
rm -f /tmp/gateway_cookies.txt

echo "[$(date)] ✅ Model refresh complete"
