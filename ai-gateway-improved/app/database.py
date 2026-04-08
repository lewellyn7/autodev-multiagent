"""
Database module - Sync wrapper for database operations.
This provides a synchronous interface for use in main.py.
"""
import sqlite3
import os
from pathlib import Path
import threading

# Thread-local storage for connections
_local = threading.local()

DB_PATH = os.getenv("DB_FILE", "data/gateway.db")

def _get_db_path():
    """Get database path, creating data directory if needed."""
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)

def get_db_connection():
    """Get or create a thread-local database connection."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        return conn
    return _local.conn

def init_db():
    """Initialize database tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            rate_limit INTEGER DEFAULT 60,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxy_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            cookies TEXT,
            tokens TEXT,
            status TEXT DEFAULT 'unknown',
            last_checked TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            user_id TEXT,
            ip TEXT,
            method TEXT,
            path TEXT,
            body TEXT,
            status INTEGER,
            latency INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()

def get_key_info(key: str):
    """Get API key information."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM api_keys WHERE key = ? AND is_active = 1', (key,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None

def list_keys():
    """List all API keys."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM api_keys ORDER BY created_at DESC')
    return [dict(row) for row in cursor.fetchall()]

def get_all_pool_status():
    """Get all proxy pool status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM proxy_pool ORDER BY source')
    return [dict(row) for row in cursor.fetchall()]

def get_pool_data(source: str):
    """Get proxy pool data for a source."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM proxy_pool WHERE source = ?', (source,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None

def update_pool(source: str, cookies: dict, tokens: dict):
    """Update or insert proxy pool data."""
    import json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO proxy_pool (source, cookies, tokens, status, last_checked)
        VALUES (?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ON CONFLICT(source) DO UPDATE SET
            cookies = excluded.cookies,
            tokens = excluded.tokens,
            status = 'active',
            last_checked = CURRENT_TIMESTAMP
    ''', (source, json.dumps(cookies), json.dumps(tokens)))
    conn.commit()

def delete_pool_data(source: str):
    """Delete proxy pool data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM proxy_pool WHERE source = ?', (source,))
    conn.commit()

def get_models():
    """Get all models."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM models WHERE is_active = 1 ORDER BY name')
    return [dict(row) for row in cursor.fetchall()]

def get_all_models_sync():
    """Get all models (sync version)."""
    return get_models()

def get_expired_models():
    """Get expired models."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM models WHERE expires_at < CURRENT_TIMESTAMP')
    return [dict(row) for row in cursor.fetchall()]

def update_pool_status(source: str, status: str):
    """Update proxy pool status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE proxy_pool SET status = ?, last_checked = CURRENT_TIMESTAMP WHERE source = ?
    ''', (status, source))
    conn.commit()

def log_request(action: str, user_id: str, ip: str, method: str, path: str, body: str, status: int, latency: int):
    """Log API request."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO request_logs (action, user_id, ip, method, path, body, status, latency)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (action, user_id, ip, method, path, body, status, latency))
    conn.commit()
