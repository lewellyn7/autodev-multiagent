import sqlite3
import time
import json

DB_FILE = "data/gateway.db"

def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS proxy_pool (
            source TEXT PRIMARY KEY,
            cookies TEXT, 
            tokens TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # [v4.4 更新] 尝试增加 status 字段
        try:
            conn.execute("ALTER TABLE proxy_pool ADD COLUMN status TEXT DEFAULT 'unknown'")
        except:
            pass

        conn.execute('''CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS expired_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS client_keys (
            key TEXT PRIMARY KEY,
            name TEXT,
            allowed_models TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        if conn.execute("SELECT count(*) FROM models").fetchone()[0] == 0:
            defaults = [("gpt-4o", "chatgpt"), ("gpt-4o-mini", "chatgpt")]
            conn.executemany("INSERT OR IGNORE INTO models (name, source) VALUES (?, ?)", defaults)

# --- Proxy Pool ---
def update_pool(source, cookies, tokens):
    with get_conn() as conn:
        # 更新时重置状态为 unknown，等待检测
        conn.execute("INSERT OR REPLACE INTO proxy_pool (source, cookies, tokens, updated_at, status) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'unknown')", 
                     (source, json.dumps(cookies), json.dumps(tokens)))

def update_pool_status(source, status):
    with get_conn() as conn:
        conn.execute("UPDATE proxy_pool SET status=? WHERE source=?", (status, source))

def delete_pool_data(source):
    with get_conn() as conn: conn.execute("DELETE FROM proxy_pool WHERE source=?", (source,))

def get_pool_data(source):
    with get_conn() as conn:
        row = conn.execute("SELECT cookies, tokens FROM proxy_pool WHERE source=?", (source,)).fetchone()
        if row: return {"cookies": json.loads(row[0]), "tokens": json.loads(row[1])}
        return None

def get_all_pool_status():
    with get_conn() as conn:
        data = []
        # 获取 status 字段
        rows = conn.execute("SELECT source, updated_at, cookies, status FROM proxy_pool").fetchall()
        for r in rows:
            cookie_count = len(json.loads(r[2])) if r[2] else 0
            # 兼容旧数据，如果没有 status 则默认为 unknown
            status = r[3] if len(r) > 3 and r[3] else 'unknown'
            data.append({"source": r[0], "updated_at": r[1], "cookie_count": cookie_count, "status": status})
        return data

# --- Models / Keys (保持不变) ---
def get_models():
    with get_conn() as conn: return [{"id":r[0], "name":r[1], "source":r[2]} for r in conn.execute("SELECT * FROM models ORDER BY source DESC, name ASC").fetchall()]
def get_model_by_id(id):
    with get_conn() as conn: row = conn.execute("SELECT name, source FROM models WHERE id=?", (id,)).fetchone(); return {"name": row[0], "source": row[1]} if row else None
def add_model(name, source):
    try:
        with get_conn() as conn: conn.execute("INSERT INTO models (name, source) VALUES (?, ?)", (name, source)); return True
    except: return False
def bulk_add_models(models_list):
    with get_conn() as conn: conn.executemany("INSERT OR IGNORE INTO models (name, source) VALUES (?, ?)", models_list)
def del_model(id):
    with get_conn() as conn: conn.execute("DELETE FROM models WHERE id=?", (id,))
def get_expired_models():
    with get_conn() as conn: return [{"id":r[0], "name":r[1], "source":r[2]} for r in conn.execute("SELECT * FROM expired_models ORDER BY source DESC, name ASC").fetchall()]
def add_expired_model(name, source):
    try:
        with get_conn() as conn: conn.execute("INSERT OR IGNORE INTO expired_models (name, source) VALUES (?, ?)", (name, source)); return True
    except: return False
def del_expired_model(id):
    with get_conn() as conn: conn.execute("DELETE FROM expired_models WHERE id=?", (id,))
def get_all_expired_set():
    with get_conn() as conn: return set((r[0], r[1]) for r in conn.execute("SELECT name, source FROM expired_models").fetchall())
def add_key(key, name, models):
    with get_conn() as conn: conn.execute("INSERT INTO client_keys (key, name, allowed_models) VALUES (?, ?, ?)", (key, name, models))
def list_keys():
    with get_conn() as conn: return [{"key":r[0], "name":r[1], "allowed_models":r[2], "created_at":r[3]} for r in conn.execute("SELECT * FROM client_keys ORDER BY created_at DESC").fetchall()]
def update_key(key, name, models):
    with get_conn() as conn: conn.execute("UPDATE client_keys SET name=?, allowed_models=? WHERE key=?", (name, models, key))
def del_key(key):
    with get_conn() as conn: conn.execute("DELETE FROM client_keys WHERE key=?", (key,))
def get_key_info(key):
    with get_conn() as conn:
        row = conn.execute("SELECT allowed_models FROM client_keys WHERE key=?", (key,)).fetchone()
        return {"allowed_models": row[0]} if row else None
