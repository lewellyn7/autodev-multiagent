#!/usr/bin/env python3
"""
Simple test to verify audit logging code syntax.
"""
import ast
import sys

def check_file_syntax(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        ast.parse(source)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def check_function_exists(filepath, function_name):
    """Check if a function exists in a Python file."""
    try:
        with open(filepath, 'r') as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                return True, f"Function '{function_name}' found"
        return False, f"Function '{function_name}' not found"
    except Exception as e:
        return False, f"Error: {e}"

def main():
    print("Audit Logging System - Syntax Verification")
    print("=" * 50)
    
    all_ok = True
    
    # Check database.py
    print("\n1. Checking app/database.py...")
    ok, msg = check_file_syntax('app/database.py')
    print(f"   {'✓' if ok else '✗'} {msg}")
    all_ok = all_ok and ok
    
    # Check main.py
    print("\n2. Checking app/main.py...")
    ok, msg = check_file_syntax('app/main.py')
    print(f"   {'✓' if ok else '✗'} {msg}")
    all_ok = all_ok and ok
    
    # Check for required functions in database.py
    print("\n3. Checking required database functions...")
    required_funcs = [
        'init_audit_log_table',
        'log_request',
        'get_audit_logs',
        'cleanup_old_logs',
        'get_audit_stats'
    ]
    
    for func in required_funcs:
        ok, msg = check_function_exists('app/database.py', func)
        print(f"   {'✓' if ok else '✗'} {msg}")
        all_ok = all_ok and ok
    
    # Check for AuditMiddleware class
    print("\n4. Checking AuditMiddleware class...")
    with open('app/main.py', 'r') as f:
        source = f.read()
    if 'class AuditMiddleware' in source:
        print("   ✓ AuditMiddleware class found")
    else:
        print("   ✗ AuditMiddleware class not found")
        all_ok = False
    
    # Check for audit API endpoints
    print("\n5. Checking audit API endpoints...")
    endpoints = [
        '/api/audit/logs',
        '/api/audit/stats',
        '/api/audit/cleanup'
    ]
    
    for endpoint in endpoints:
        if endpoint in source:
            print(f"   ✓ Endpoint {endpoint} found")
        else:
            print(f"   ✗ Endpoint {endpoint} not found")
            all_ok = False
    
    print("\n" + "=" * 50)
    if all_ok:
        print("✓ All checks passed!")
        return 0
    else:
        print("✗ Some checks failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
