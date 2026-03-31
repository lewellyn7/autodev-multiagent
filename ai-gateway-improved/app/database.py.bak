from psycopg2.extras import RealDictCursor
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
    "host": os.getenv("POSTGRES_HOST", "postgres"),
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
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if db_type == "postgres":
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(**POSTGRES_CONFIG)
            conn.autocommit = True
            return conn
        except ImportError:
            logger.warning("psycopg2 not installed, falling back to SQLite")
            # Continue to SQLite fallback below
    
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

# =============================================================================
# OAuth Accounts Operations
# =============================================================================
def init_oauth_table():
    """Initialize OAuth accounts table."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS oauth_accounts (
                    id SERIAL PRIMARY KEY,
                    provider VARCHAR(50) NOT NULL,
                    provider_user_id VARCHAR(255) NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER,
                    email VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, provider_user_id)
                )
            """)
            conn.commit()
            cur.close()
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS oauth_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    provider_user_id TEXT NOT NULL,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, provider_user_id)
                )
            """)

def add_oauth_account(provider, provider_user_id, access_token, refresh_token=None, expires_at=None, email=None):
    """Add or update OAuth account."""
    try:
        with get_conn() as conn:
            if DB_TYPE == "postgres":
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO oauth_accounts (provider, provider_user_id, access_token, refresh_token, expires_at, email)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (provider, provider_user_id) DO UPDATE
                    SET access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token,
                        expires_at = EXCLUDED.expires_at,
                        email = EXCLUDED.email,
                        created_at = CURRENT_TIMESTAMP
                """, (provider, provider_user_id, access_token, refresh_token, expires_at, email))
                conn.commit()
                cur.close()
            else:
                conn.execute("""
                    INSERT OR REPLACE INTO oauth_accounts (provider, provider_user_id, access_token, refresh_token, expires_at, email, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (provider, provider_user_id, access_token, refresh_token, expires_at, email))
        return True
    except Exception as e:
        logger.error(f"Error adding OAuth account: {e}")
        return False

def get_oauth_account(provider, provider_user_id):
    """Get OAuth account by provider and user ID."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT * FROM oauth_accounts WHERE provider=%s AND provider_user_id=%s", (provider, provider_user_id))
            row = cur.fetchone()
            cur.close()
            return dict(row) if row else None
        else:
            row = conn.execute("SELECT * FROM oauth_accounts WHERE provider=? AND provider_user_id=?", (provider, provider_user_id)).fetchone()
            if row:
                return {
                    "id": row[0],
                    "provider": row[1],
                    "provider_user_id": row[2],
                    "access_token": row[3],
                    "refresh_token": row[4],
                    "expires_at": row[5],
                    "email": row[6],
                    "created_at": row[7]
                }
            return None

def get_all_oauth_accounts():
    """Get all OAuth accounts."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = get_cursor(conn)
            cur.execute("SELECT id, provider, provider_user_id, email, created_at FROM oauth_accounts ORDER BY created_at DESC")
            rows = cur.fetchall()
            cur.close()
            return [dict(r) for r in rows]
        else:
            rows = conn.execute("SELECT id, provider, provider_user_id, email, created_at FROM oauth_accounts ORDER BY created_at DESC").fetchall()
            return [
                {"id": r[0], "provider": r[1], "provider_user_id": r[2], "email": r[3], "created_at": r[4]}
                for r in rows
            ]

def delete_oauth_account(provider, provider_user_id):
    """Delete OAuth account."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM oauth_accounts WHERE provider=%s AND provider_user_id=%s", (provider, provider_user_id))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM oauth_accounts WHERE provider=? AND provider_user_id=?", (provider, provider_user_id))

def delete_oauth_account_by_provider(provider):
    """Delete all OAuth accounts for a provider."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM oauth_accounts WHERE provider=%s", (provider,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM oauth_accounts WHERE provider=?", (provider,))

def update_oauth_token(provider, provider_user_id, access_token, refresh_token=None, expires_at=None):
    """Update OAuth tokens."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("""
                UPDATE oauth_accounts
                SET access_token=%s, refresh_token=%s, expires_at=%s
                WHERE provider=%s AND provider_user_id=%s
            """, (access_token, refresh_token, expires_at, provider, provider_user_id))
            conn.commit()
            cur.close()
        else:
            conn.execute("""
                UPDATE oauth_accounts
                SET access_token=?, refresh_token=?, expires_at=?
                WHERE provider=? AND provider_user_id=?
            """, (access_token, refresh_token, expires_at, provider, provider_user_id))

# =============================================================================
# Proxy Account Pool - Multi-account polling support
# =============================================================================

def init_proxy_accounts_table():
    """Create proxy_accounts table if not exists."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS proxy_accounts (
                    id SERIAL PRIMARY KEY,
                    source VARCHAR(32) NOT NULL,
                    account_index INTEGER DEFAULT 0,
                    cookies TEXT DEFAULT '{}',
                    tokens TEXT DEFAULT '{}',
                    status VARCHAR(16) DEFAULT 'active',
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP NULL,
                    last_success TIMESTAMP NULL,
                    avg_latency REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cur.close()
        else:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proxy_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source VARCHAR(32) NOT NULL,
                    account_index INTEGER DEFAULT 0,
                    cookies TEXT DEFAULT '{}',
                    tokens TEXT DEFAULT '{}',
                    status VARCHAR(16) DEFAULT 'active',
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_used TIMESTAMP NULL,
                    last_success TIMESTAMP NULL,
                    avg_latency REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

def add_proxy_account(source, account_index, cookies=None, tokens=None):
    """Add a proxy account to the pool."""
    import json
    cookies = json.dumps(cookies or {})
    tokens = json.dumps(tokens or {})
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO proxy_accounts (source, account_index, cookies, tokens, status)
                VALUES (%s, %s, %s, %s, 'active')
                ON CONFLICT (source, account_index) DO UPDATE SET
                    cookies=EXCLUDED.cookies, tokens=EXCLUDED.tokens, status='active'
            """, (source, account_index, cookies, tokens))
            conn.commit()
            cur.close()
        else:
            conn.execute("""
                INSERT OR REPLACE INTO proxy_accounts (source, account_index, cookies, tokens, status)
                VALUES (?, ?, ?, ?, 'active')
            """, (source, account_index, cookies, tokens))

def get_proxy_accounts(source, status_filter='active'):
    """Get all proxy accounts for a source."""
    import json
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            if status_filter:
                cur.execute("SELECT * FROM proxy_accounts WHERE source=%s AND status=%s ORDER BY account_index", (source, status_filter))
            else:
                cur.execute("SELECT * FROM proxy_accounts WHERE source=%s ORDER BY account_index", (source,))
            rows = cur.fetchall()
            cur.close()
        else:
            if status_filter:
                rows = conn.execute("SELECT * FROM proxy_accounts WHERE source=? AND status=? ORDER BY account_index", (source, status_filter)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM proxy_accounts WHERE source=? ORDER BY account_index", (source,)).fetchall()
        
        cols = ['id','source','account_index','cookies','tokens','status','success_count','fail_count','last_used','last_success','avg_latency','created_at']
        result = []
        for r in rows:
            row_dict = dict(zip(cols, r))
            row_dict['cookies'] = json.loads(row_dict['cookies'] or '{}')
            row_dict['tokens'] = json.loads(row_dict['tokens'] or '{}')
            result.append(row_dict)
        return result

def get_pool_by_strategy(source, strategy='round_robin'):
    """Get next available account based on polling strategy.
    
    Strategies:
    - round_robin: Cyclic rotation based on last_used timestamp
    - random: Random selection
    - weighted: Selection weighted by success rate
    - circuit_breaker: Skip accounts with fail_count > threshold
    """
    import json, random, time
    accounts = get_proxy_accounts(source, status_filter='active')
    if not accounts:
        return None
    
    if strategy == 'random':
        chosen = random.choice(accounts)
        _mark_used(chosen['id'])
        return chosen
    
    elif strategy == 'weighted':
        # Weight by success ratio
        weighted = []
        for acc in accounts:
            total = acc['success_count'] + acc['fail_count']
            if total == 0:
                weight = 1.0
            else:
                weight = acc['success_count'] / total
            weighted.append((weight, acc))
        if not weighted:
            return None
        total_weight = sum(w for w, _ in weighted)
        r = random.uniform(0, total_weight)
        cumsum = 0
        for w, acc in weighted:
            cumsum += w
            if r <= cumsum:
                _mark_used(acc['id'])
                return acc
        _mark_used(weighted[-1][1]['id'])
        return weighted[-1][1]
    
    elif strategy == 'circuit_breaker':
        # Skip accounts with >5 recent failures
        valid = [a for a in accounts if a['fail_count'] < 5]
        if not valid:
            return None
        # Pick least recently used among valid
        valid.sort(key=lambda x: x['last_used'] or '')
        chosen = valid[0]
        _mark_used(chosen['id'])
        return chosen
    
    else:  # round_robin (default)
        # Pick account with oldest last_used (or never used)
        accounts.sort(key=lambda x: x['last_used'] or '')
        chosen = accounts[0]
        _mark_used(chosen['id'])
        return chosen

def _mark_used(account_id):
    """Mark account as just used."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("UPDATE proxy_accounts SET last_used=CURRENT_TIMESTAMP WHERE id=%s", (account_id,))
            conn.commit()
            cur.close()
        else:
            conn.execute("UPDATE proxy_accounts SET last_used=CURRENT_TIMESTAMP WHERE id=?", (account_id,))

def update_account_stats(account_id, success, latency=None):
    """Update account statistics after a request."""
    with get_conn() as conn:
        if success:
            if DB_TYPE == "postgres":
                cur = conn.cursor()
                cur.execute("""
                    UPDATE proxy_accounts
                    SET success_count=success_count+1, last_success=CURRENT_TIMESTAMP,
                        status='active', avg_latency=((avg_latency*success_count)+%s)/(success_count+1)
                    WHERE id=%s
                """, (latency or 0, account_id))
                conn.commit()
                cur.close()
            else:
                conn.execute("""
                    UPDATE proxy_accounts
                    SET success_count=success_count+1, last_success=CURRENT_TIMESTAMP,
                        status='active', avg_latency=((avg_latency*success_count)+?)/(success_count+1)
                    WHERE id=?
                """, (latency or 0, account_id))
        else:
            if DB_TYPE == "postgres":
                cur = conn.cursor()
                cur.execute("""
                    UPDATE proxy_accounts
                    SET fail_count=fail_count+1, status=CASE WHEN fail_count+1>=10 THEN 'expired' ELSE 'warning' END
                    WHERE id=%s
                """, (account_id,))
                conn.commit()
                cur.close()
            else:
                conn.execute("""
                    UPDATE proxy_accounts
                    SET fail_count=fail_count+1, status=CASE WHEN fail_count+1>=10 THEN 'expired' ELSE 'warning' END
                    WHERE id=?
                """, (account_id,))

def get_account_health(source):
    """Get health summary for a source pool."""
    accounts = get_proxy_accounts(source, status_filter=None)
    if not accounts:
        return {"total": 0, "active": 0, "warning": 0, "expired": 0, "avg_success_rate": 0}
    
    active = sum(1 for a in accounts if a['status'] == 'active')
    warning = sum(1 for a in accounts if a['status'] == 'warning')
    expired = sum(1 for a in accounts if a['status'] == 'expired')
    
    total_success = sum(a['success_count'] for a in accounts)
    total_fail = sum(a['fail_count'] for a in accounts)
    total = total_success + total_fail
    success_rate = (total_success / total * 100) if total > 0 else 0
    
    return {
        "total": len(accounts),
        "active": active,
        "warning": warning,
        "expired": expired,
        "avg_success_rate": round(success_rate, 1),
        "accounts": [
            {"id": a['id'], "index": a['account_index'], "status": a['status'],
             "success": a['success_count'], "fail": a['fail_count'],
             "last_used": str(a['last_used']), "avg_latency": round(a['avg_latency'], 1)}
            for a in accounts
        ]
    }

def delete_proxy_account(account_id):
    """Delete a proxy account."""
    with get_conn() as conn:
        if DB_TYPE == "postgres":
            cur = conn.cursor()
            cur.execute("DELETE FROM proxy_accounts WHERE id=%s", (account_id,))
            conn.commit()
            cur.close()
        else:
            conn.execute("DELETE FROM proxy_accounts WHERE id=?", (account_id,))

# Initialize on import
init_proxy_accounts_table()
