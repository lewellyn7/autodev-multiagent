import os
import json
import sqlite3
import logging

logger = logging.getLogger("ai-gateway.database")

# =============================================================================
# Database Configuration
# Supports SQLite (default/local) and PostgreSQL (production)
# =============================================================================

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
DB_FILE = os.getenv("DB_FILE", "data/gateway.db")

# PostgreSQL connection (when DB_TYPE=postgres)
POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "ai_gateway"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

# =============================================================================
# Database Abstraction Layer
# =============================================================================

def get_conn():
    """Get database connection based on DB_TYPE."""
    if DB_TYPE == "postgres":
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(**POSTGRES_CONFIG)
            conn.autocommit = True
            return conn
        except ImportError:
            logger.warning("psycopg2 not installed, falling back to SQLite")
            DB_TYPE = "sqlite"
    
    # SQLite default
    os.makedirs(os.path.dirname(DB_FILE) if os.path.dirname(DB_FILE) else ".", exist_ok=True)
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def get_cursor(conn):
    """Get appropriate cursor based on DB_TYPE."""
    if DB_TYPE == "postgres":
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()


# =============================================================================
# Initialization
# =============================================================================

def init_db():
    """Initialize database tables."""
    if DB_TYPE == "postgres":
        _init_postgres()
    else:
        _init_sqlite()


def _init_sqlite():
    """Initialize SQLite database."""
    with get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS proxy_pool (
            source TEXT PRIMARY KEY,
            cookies TEXT, 
            tokens TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
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


def _init_postgres():
    """Initialize PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 required for PostgreSQL. Install with: pip install psycopg2-binary")
        return
    
    conn = get_conn()
    cur = conn.cursor()
    
    # Create tables
    cur.execute('''CREATE TABLE IF NOT EXISTS proxy_pool (
        source VARCHAR(255) PRIMARY KEY,
        cookies TEXT, 
        tokens TEXT,
        status VARCHAR(50) DEFAULT 'unknown',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS models (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255),
        source VARCHAR(255),
        UNIQUE(name, source)
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS expired_models (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255),
        source VARCHAR(255),
        UNIQUE(name, source)
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS client_keys (
        key VARCHAR(255) PRIMARY KEY,
        name VARCHAR(255),
        allowed_models TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    cur.close()
    conn.close()
    logger.info("PostgreSQL database initialized")


# =============================================================================
# Proxy Pool Operations
# =============================================================================

def update_pool(source, cookies, tokens):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO proxy_pool (source, cookies, tokens, status, updated_at)
                VALUES (%s, %s, %s, 'unknown', CURRENT_TIMESTAMP)
                ON CONFLICT (source) DO UPDATE SET
                    cookies = EXCLUDED.cookies,
                    tokens = EXCLUDED.tokens,
                    status = 'unknown',
                    updated_at = CURRENT_TIMESTAMP
            """, (source, json.dumps(cookies), json.dumps(tokens)))
            conn.commit()
            cur.close()
        else:
            conn.execute(
                "INSERT OR REPLACE INTO proxy_pool (source, cookies, tokens, updated_at, status) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'unknown')",
                (source, json.dumps(cookies), json.dumps(tokens))
            )


def update_pool_status(source, status):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("UPDATE proxy_pool SET status=%s WHERE source=%s", (status, source))
            conn.commit()
            cur.close()
        else:
            conn.execute("UPDATE proxy_pool SET status=? WHERE source=?", (status, source))


def delete_pool_data(source):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM proxy_pool WHERE source=%s", (source,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM proxy_pool WHERE source=?", (source,))


def get_pool_data(source):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT cookies, tokens FROM proxy_pool WHERE source=%s", (source,))
            row = cur.fetchone()
            cur.close()
            if row:
                return {"cookies": json.loads(row["cookies"]), "tokens": json.loads(row["tokens"])}
            return None
        else:
            row = conn.execute("SELECT cookies, tokens FROM proxy_pool WHERE source=?", (source,)).fetchone()
            if row:
                return {"cookies": json.loads(row[0]), "tokens": json.loads(row[1])}
            return None


def get_all_pool_status():
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT source, updated_at, cookies, status FROM proxy_pool")
            rows = cur.fetchall()
            cur.close()
            data = []
            for r in rows:
                cookie_count = len(json.loads(r["cookies"])) if r["cookies"] else 0
                data.append({
                    "source": r["source"],
                    "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
                    "cookie_count": cookie_count,
                    "status": r["status"] or "unknown"
                })
            return data
        else:
            rows = conn.execute("SELECT source, updated_at, cookies, status FROM proxy_pool").fetchall()
            data = []
            for r in rows:
                cookie_count = len(json.loads(r[2])) if r[2] else 0
                data.append({
                    "source": r[0],
                    "updated_at": r[1],
                    "cookie_count": cookie_count,
                    "status": r[3] if len(r) > 3 and r[3] else "unknown"
                })
            return data


# =============================================================================
# Models Operations
# =============================================================================

def get_models():
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT id, name, source FROM models ORDER BY source DESC, name ASC")
            return [dict(r) for r in cur.fetchall()]
        else:
            return [{"id": r[0], "name": r[1], "source": r[2]} 
                    for r in conn.execute("SELECT * FROM models ORDER BY source DESC, name ASC").fetchall()]


def get_model_by_id(id):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT name, source FROM models WHERE id=%s", (id,))
            r = cur.fetchone()
            cur.close()
            return {"name": r["name"], "source": r["source"]} if r else None
        else:
            r = conn.execute("SELECT name, source FROM models WHERE id=?", (id,)).fetchone()
            return {"name": r[0], "source": r[1]} if r else None


def add_model(name, source):
    try:
        with get_conn() as conn:
            if DB_TYPE == "postgres":
                cur = conn.cursor()
                cur.execute("INSERT INTO models (name, source) VALUES (%s, %s) ON CONFLICT DO NOTHING", (name, source))
                conn.commit()
                cur.close()
            else:
                conn.execute("INSERT INTO models (name, source) VALUES (?, ?)", (name, source))
        return True
    except:
        return False


def bulk_add_models(models_list):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.executemany("INSERT INTO models (name, source) VALUES (%s, %s) ON CONFLICT DO NOTHING", models_list)
            conn.commit()
            cur.close()
        else:
            conn.executemany("INSERT OR IGNORE INTO models (name, source) VALUES (?, ?)", models_list)


def del_model(id):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM models WHERE id=%s", (id,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM models WHERE id=?", (id,))


def get_expired_models():
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT id, name, source FROM expired_models ORDER BY source DESC, name ASC")
            return [dict(r) for r in cur.fetchall()]
        else:
            return [{"id": r[0], "name": r[1], "source": r[2]} 
                    for r in conn.execute("SELECT * FROM expired_models ORDER BY source DESC, name ASC").fetchall()]


def add_expired_model(name, source):
    try:
        with get_conn() as conn:
            if DB_TYPE == "postgres":
                cur = conn.cursor()
                cur.execute("INSERT INTO expired_models (name, source) VALUES (%s, %s) ON CONFLICT DO NOTHING", (name, source))
                conn.commit()
                cur.close()
            else:
                conn.execute("INSERT OR IGNORE INTO expired_models (name, source) VALUES (?, ?)", (name, source))
        return True
    except:
        return False


def del_expired_model(id):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM expired_models WHERE id=%s", (id,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM expired_models WHERE id=?", (id,))


def get_all_expired_set():
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT name, source FROM expired_models")
            return set((r["name"], r["source"]) for r in cur.fetchall())
        else:
            return set((r[0], r[1]) for r in conn.execute("SELECT name, source FROM expired_models").fetchall())


# =============================================================================
# API Keys Operations
# =============================================================================

def add_key(key, name, models):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("INSERT INTO client_keys (key, name, allowed_models) VALUES (%s, %s, %s)", (key, name, models))
            conn.commit()
            cur.close()
        else:
            conn.execute("INSERT INTO client_keys (key, name, allowed_models) VALUES (?, ?, ?)", (key, name, models))


def list_keys():
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT key, name, allowed_models, created_at FROM client_keys ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]
        else:
            return [{"key": r[0], "name": r[1], "allowed_models": r[2], "created_at": r[3]} 
                    for r in conn.execute("SELECT * FROM client_keys ORDER BY created_at DESC").fetchall()]


def update_key(key, name, models):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("UPDATE client_keys SET name=%s, allowed_models=%s WHERE key=%s", (name, models, key))
            conn.commit()
            cur.close()
        else:
            conn.execute("UPDATE client_keys SET name=?, allowed_models=? WHERE key=?", (name, models, key))


def del_key(key):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM client_keys WHERE key=%s", (key,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM client_keys WHERE key=?", (key,))


def get_key_info(key):
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT allowed_models FROM client_keys WHERE key=%s", (key,))
            r = cur.fetchone()
            cur.close()
            return {"allowed_models": r["allowed_models"]} if r else None
        else:
            r = conn.execute("SELECT allowed_models FROM client_keys WHERE key=?", (key,)).fetchone()
            return {"allowed_models": r[0]} if r else None
