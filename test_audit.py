#!/usr/bin/env python3
"""
Test script for audit logging functionality.
Run this to verify the audit system is working correctly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import database as db

def test_audit_functions():
    """Test audit logging functions."""
    print("Testing audit logging functions...")
    
    # Test 1: Log a request
    print("\n1. Testing log_request()...")
    try:
        db.log_request(
            action="TEST_ACTION",
            user_id="test_user",
            ip="127.0.0.1",
            method="GET",
            path="/test/path",
            body="{'test': 'data'}",
            status=200,
            latency=42
        )
        print("   ✓ Request logged successfully")
    except Exception as e:
        print(f"   ✗ Failed to log request: {e}")
        return False
    
    # Test 2: Get audit logs
    print("\n2. Testing get_audit_logs()...")
    try:
        logs = db.get_audit_logs(limit=10)
        print(f"   ✓ Retrieved {len(logs)} audit log(s)")
        if logs:
            print(f"   Latest log: {logs[0]['action']} - {logs[0]['path']}")
    except Exception as e:
        print(f"   ✗ Failed to get audit logs: {e}")
        return False
    
    # Test 3: Get audit stats
    print("\n3. Testing get_audit_stats()...")
    try:
        stats = db.get_audit_stats()
        print(f"   ✓ Statistics retrieved")
        print(f"   Total requests: {stats.get('total_requests', 0)}")
        print(f"   Error rate: {stats.get('error_rate', 0)}%")
    except Exception as e:
        print(f"   ✗ Failed to get stats: {e}")
        return False
    
    # Test 4: Cleanup old logs
    print("\n4. Testing cleanup_old_logs()...")
    try:
        deleted = db.cleanup_old_logs(days_to_keep=1)
        print(f"   ✓ Cleanup completed ({deleted} records deleted)")
    except Exception as e:
        print(f"   ✗ Failed to cleanup: {e}")
        return False
    
    print("\n✓ All tests passed!")
    return True

if __name__ == "__main__":
    try:
        success = test_audit_functions()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
