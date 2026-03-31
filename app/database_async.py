"""
Async Database Layer - 异步数据库
支持 SQLite (aiosqlite) 和 PostgreSQL (asyncpg)
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger("ai-gateway.database")

# =============================================================================
# Database Configuration
# =============================================================================
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
DB_FILE = os.getenv("DB_FILE", "data/gateway.db")

POSTGRES_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "ai_gateway"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}


# =============================================================================
# Connection Management
# =============================================================================
@asynccontextmanager
async def get_conn() -> AsyncIterator:
    """Get async database connection based on DB_TYPE."""
    if DB_TYPE == "postgres":
        try:
            import asyncpg

            conn = await asyncpg.connect(**POSTGRES_CONFIG)
            try:
                yield conn
            finally:
                await conn.close()
        except ImportError:
            logger.warning("asyncpg not installed, falling back to aiosqlite")
            conn = await _async_sqlite_connect()
            try:
                yield conn
            finally:
                await conn.close()
    else:
        conn = await _async_sqlite_connect()
        try:
            yield conn
        finally:
            await conn.close()


async def _async_sqlite_connect():
    """Connect to SQLite using aiosqlite."""
    import aiosqlite

    os.makedirs(os.path.dirname(DB_FILE) if os.path.dirname(DB_FILE) else ".", exist_ok=True)
    return await aiosqlite.connect(DB_FILE)


# =============================================================================
# Initialization
# =============================================================================
async def init_db():
    """Initialize database tables."""
    if DB_TYPE == "postgres":
        await _init_postgres()
    else:
        await _init_sqlite()


async def _init_sqlite():
    """Initialize SQLite database."""
    async with get_conn() as conn:
        await conn.execute("""CREATE TABLE IF NOT EXISTS proxy_pool (
            source TEXT PRIMARY KEY,
            cookies TEXT,
            tokens TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        try:
            await conn.execute("ALTER TABLE proxy_pool ADD COLUMN status TEXT DEFAULT 'unknown'")
        except:
            pass

        await conn.execute("""CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS expired_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS client_keys (
            key TEXT PRIMARY KEY,
            name TEXT,
            enabled INTEGER DEFAULT 1,
            allowed_models TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            user_id TEXT
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS account_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT,
            account_id TEXT,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            avg_latency REAL DEFAULT 0,
            last_used TIMESTAMP,
            health_score REAL DEFAULT 100.0,
            consecutive_failures INTEGER DEFAULT 0,
            UNIQUE(channel, account_id)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            user_id TEXT,
            ip TEXT,
            method TEXT,
            path TEXT,
            body TEXT,
            status INTEGER,
            latency INTEGER
        )""")


async def _init_postgres():
    """Initialize PostgreSQL database."""
    import asyncpg

    conn = await asyncpg.connect(**POSTGRES_CONFIG)
    try:
        await conn.execute("""CREATE TABLE IF NOT EXISTS proxy_pool (
            source TEXT PRIMARY KEY,
            cookies TEXT,
            tokens TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS models (
            id SERIAL PRIMARY KEY,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS expired_models (
            id SERIAL PRIMARY KEY,
            name TEXT,
            source TEXT,
            UNIQUE(name, source)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS client_keys (
            key TEXT PRIMARY KEY,
            name TEXT,
            enabled INTEGER DEFAULT 1,
            allowed_models TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            user_id TEXT
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS account_stats (
            id SERIAL PRIMARY KEY,
            channel TEXT,
            account_id TEXT,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            avg_latency REAL DEFAULT 0,
            last_used TIMESTAMP,
            health_score REAL DEFAULT 100.0,
            consecutive_failures INTEGER DEFAULT 0,
            UNIQUE(channel, account_id)
        )""")

        await conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT,
            user_id TEXT,
            ip TEXT,
            method TEXT,
            path TEXT,
            body TEXT,
            status INTEGER,
            latency INTEGER
        )""")
    finally:
        await conn.close()


# =============================================================================
# Proxy Pool Operations
# =============================================================================
async def get_pool_data(source: str) -> dict | None:
    """Get pool data for a source."""
    async with get_conn() as conn:
        if DB_TYPE == "postgres":
            row = await conn.fetchrow("SELECT * FROM proxy_pool WHERE source = $1", source)
        else:
            async with conn.execute("SELECT * FROM proxy_pool WHERE source = ?", source) as cursor:
                row = await cursor.fetchone()

        if row:
            return dict(row)
        return None


async def update_pool_data(source: str, cookies: dict = None, tokens: dict = None, status: str = None):
    """Update pool data for a source."""
    async with get_conn() as conn:
        if cookies is not None:
            cookies = json.dumps(cookies)
        if tokens is not None:
            tokens = json.dumps(tokens)

        if DB_TYPE == "postgres":
            await conn.execute(
                """
                INSERT INTO proxy_pool (source, cookies, tokens, status, updated_at)
                VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
                ON CONFLICT (source) DO UPDATE SET
                    cookies = COALESCE($2, proxy_pool.cookies),
                    tokens = COALESCE($3, proxy_pool.tokens),
                    status = COALESCE($4, proxy_pool.status),
                    updated_at = CURRENT_TIMESTAMP
            """,
                source,
                cookies,
                tokens,
                status,
            )
        else:
            await conn.execute(
                """
                INSERT INTO proxy_pool (source, cookies, tokens, status, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(source) DO UPDATE SET
                    cookies = COALESCE(VALUES(cookies), proxy_pool.cookies),
                    tokens = COALESCE(VALUES(tokens), proxy_pool.tokens),
                    status = COALESCE(VALUES(status), proxy_pool.status),
                    updated_at = CURRENT_TIMESTAMP
            """,
                source,
                cookies,
                tokens,
                status,
            )


# =============================================================================
# Account Stats Operations
# =============================================================================
async def get_best_account(channel: str) -> dict | None:
    """Get best account for a channel based on health score."""
    async with get_conn() as conn:
        if DB_TYPE == "postgres":
            row = await conn.fetchrow(
                """
                SELECT * FROM account_stats
                WHERE channel = $1 AND consecutive_failures < 5
                ORDER BY health_score DESC, last_used ASC
                LIMIT 1
            """,
                channel,
            )
        else:
            async with conn.execute(
                """
                SELECT * FROM account_stats
                WHERE channel = ? AND consecutive_failures < 5
                ORDER BY health_score DESC, last_used ASC
                LIMIT 1
            """,
                channel,
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            return dict(row)
        return None


async def update_account_stats(
    account_id: int, success: bool = True, latency: float = None, cost: float = None, tokens: int = None
):
    """Update account statistics."""
    async with get_conn() as conn:
        if success:
            if DB_TYPE == "postgres":
                await conn.execute(
                    """
                    UPDATE account_stats SET
                        success_count = success_count + 1,
                        last_used = CURRENT_TIMESTAMP,
                        consecutive_failures = 0,
                        avg_latency = (avg_latency * success_count + $2) / (success_count + 1),
                        total_cost = total_cost + COALESCE($3, 0),
                        total_tokens = total_tokens + COALESCE($4, 0)
                    WHERE id = $1
                """,
                    account_id,
                    latency,
                    cost,
                    tokens,
                )
            else:
                await conn.execute(
                    """
                    UPDATE account_stats SET
                        success_count = success_count + 1,
                        last_used = CURRENT_TIMESTAMP,
                        consecutive_failures = 0,
                        avg_latency = (avg_latency * success_count + ?) / (success_count + 1),
                        total_cost = total_cost + COALESCE(?, 0),
                        total_tokens = total_tokens + COALESCE(?, 0)
                    WHERE id = ?
                """,
                    latency,
                    cost,
                    tokens,
                    account_id,
                )
        else:
            if DB_TYPE == "postgres":
                await conn.execute(
                    """
                    UPDATE account_stats SET
                        fail_count = fail_count + 1,
                        last_used = CURRENT_TIMESTAMP,
                        consecutive_failures = consecutive_failures + 1,
                        health_score = CASE
                            WHEN consecutive_failures >= 4 THEN 0
                            ELSE health_score * 0.8
                        END
                    WHERE id = $1
                """,
                    account_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE account_stats SET
                        fail_count = fail_count + 1,
                        last_used = CURRENT_TIMESTAMP,
                        consecutive_failures = consecutive_failures + 1,
                        health_score = CASE
                            WHEN consecutive_failures >= 4 THEN 0
                            ELSE health_score * 0.8
                        END
                    WHERE id = ?
                """,
                    account_id,
                )


# =============================================================================
# Audit Logging
# =============================================================================
async def log_request(
    action: str,
    user_id: str,
    ip: str,
    method: str,
    path: str,
    body: str = None,
    status: int = None,
    latency: int = None,
):
    """Log an API request for audit."""
    async with get_conn() as conn:
        if DB_TYPE == "postgres":
            await conn.execute(
                """
                INSERT INTO audit_log (action, user_id, ip, method, path, body, status, latency)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
                action,
                user_id,
                ip,
                method,
                path,
                body,
                status,
                latency,
            )
        else:
            await conn.execute(
                """
                INSERT INTO audit_log (action, user_id, ip, method, path, body, status, latency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                action,
                user_id,
                ip,
                method,
                path,
                body,
                status,
                latency,
            )


# =============================================================================
# Client Keys
# =============================================================================
async def verify_key(key: str) -> dict | None:
    """Verify a client API key."""
    async with get_conn() as conn:
        if DB_TYPE == "postgres":
            row = await conn.fetchrow("SELECT * FROM client_keys WHERE key = $1 AND enabled = 1 AND banned = 0", key)
        else:
            async with conn.execute(
                "SELECT * FROM client_keys WHERE key = ? AND enabled = 1 AND banned = 0", key
            ) as cursor:
                row = await cursor.fetchone()

        if row:
            return dict(row)
        return None


# =============================================================================
# Backward Compatibility Layer
# For sync code that hasn't been converted yet
# =============================================================================
import asyncio


def get_pool_data_sync(source: str) -> dict | None:
    """Sync wrapper for get_pool_data."""
    return asyncio.get_event_loop().run_until_complete(get_pool_data(source))


def update_pool_data_sync(source: str, cookies: dict = None, tokens: dict = None, status: str = None):
    """Sync wrapper for update_pool_data."""
    return asyncio.get_event_loop().run_until_complete(update_pool_data(source, cookies, tokens, status))


def get_best_account_sync(channel: str) -> dict | None:
    """Sync wrapper for get_best_account."""
    return asyncio.get_event_loop().run_until_complete(get_best_account(channel))


def update_account_stats_sync(account_id: int, success: bool = True, latency: float = None):
    """Sync wrapper for update_account_stats."""
    return asyncio.get_event_loop().run_until_complete(update_account_stats(account_id, success, latency))


def log_request_sync(*args, **kwargs):
    """Sync wrapper for log_request."""
    return asyncio.get_event_loop().run_until_complete(log_request(*args, **kwargs))


def verify_key_sync(key: str) -> dict | None:
    """Sync wrapper for verify_key."""
    return asyncio.get_event_loop().run_until_complete(verify_key(key))


def init_db_sync():
    """Sync wrapper for init_db."""
    return asyncio.get_event_loop().run_until_complete(init_db())
