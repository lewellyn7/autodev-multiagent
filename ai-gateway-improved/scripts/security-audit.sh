#!/usr/bin/env bash
# =============================================================================
# Security Audit Script for AI Gateway
# Run: bash scripts/security-audit.sh
# =============================================================================
set -e

echo "=========================================="
echo "🔒 AI Gateway Security Audit"
echo "=========================================="

ERRORS=0

# Check 1: Default admin credentials
echo ""
echo "[1/6] Checking default credentials..."
if grep -q 'ADMIN_PASSWORD", "password"' app/main.py 2>/dev/null; then
    echo "❌ FAIL: Default admin password detected in source"
    ERRORS=$((ERRORS+1))
else
    echo "✅ PASS: No default password hardcoded"
fi

# Check 2: CORS allow_origins=["*"]
echo ""
echo "[2/6] Checking CORS configuration..."
if grep -q 'allow_origins=\["\*"\]' app/main.py 2>/dev/null; then
    echo "⚠️  WARN: CORS allows all origins in production"
    echo "   Consider restricting to your domain"
else
    echo "✅ PASS: CORS appears restricted"
fi

# Check 3: DEBUG mode
echo ""
echo "[3/6] Checking DEBUG flag..."
if grep -q 'DEBUG.*=.*"true"' app/main.py 2>/dev/null; then
    echo "⚠️  WARN: DEBUG mode may be enabled"
else
    echo "✅ PASS: DEBUG mode appears off"
fi

# Check 4: API key exposure in logs
echo ""
echo "[4/6] Checking for key leakage in logs..."
if grep -r "Authorization.*Bearer" app/ --include="*.py" | grep -v "test" | grep -v "#"; then
    if ! grep -q "logger" app/main.py; then
        echo "⚠️  WARN: Authorization header present without structured logging"
    else
        echo "✅ PASS: Structured logging in place"
    fi
else
    echo "✅ PASS: No obvious key leakage"
fi

# Check 5: SQL injection (simple check for string formatting in queries)
echo ""
echo "[5/6] Checking for SQL injection risks..."
if grep -r "execute\|cursor\|sqlite" app/ --include="*.py" | grep -v "db\." | grep -v "#" | grep -q "."; then
    echo "⚠️  WARN: Raw SQL execution detected - ensure parameterized queries"
else
    echo "✅ PASS: Database operations appear safe"
fi

# Check 6: Sensitive data in git
echo ""
echo "[6/6] Checking .gitignore for sensitive files..."
if [ -f .gitignore ]; then
    if grep -q "\.env$" .gitignore && grep -q "\.gitignore" .gitignore; then
        echo "✅ PASS: .env in .gitignore"
    else
        echo "⚠️  WARN: Check .gitignore includes .env and .env.example"
    fi
else
    echo "❌ FAIL: No .gitignore found"
    ERRORS=$((ERRORS+1))
fi

echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo "✅ Audit complete - No critical issues"
else
    echo "❌ Audit complete - $ERRORS critical issue(s) found"
fi
echo "=========================================="
exit $ERRORS
