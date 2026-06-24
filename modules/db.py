"""
db.py — Unified database abstraction for Post-Pilot.

Supports SQLite (local dev) and PostgreSQL (production).
Detects DATABASE_URL: if it starts with 'postgres', uses psycopg2.
Otherwise falls back to sqlite3.

Usage:
    from modules.db import get_connection, placeholder, adapt_schema

    conn = get_connection()
    cur  = conn.cursor()
    cur.execute(f'SELECT * FROM users WHERE id = {placeholder}', (uid,))
    rows = cur.fetchall()
    conn.commit()
    conn.close()

Notes:
    - Always call conn.close() or use a context manager.
    - Use `placeholder` (? for SQLite, %s for Postgres) in all queries.
    - Use row_to_dict() for portable row access across both backends.

To migrate from SQLite to Postgres on Railway:
    1. Add the Railway PostgreSQL plugin to your project.
    2. Railway auto-sets DATABASE_URL in your environment.
    3. Redeploy — db.py detects it and switches automatically.
    4. Run: python -c "from modules.db import init_core_tables; init_core_tables()"
       to create all tables in the new database.
"""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Railway/Heroku serve postgres:// URLs; psycopg2 needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

USE_POSTGRES = DATABASE_URL.startswith('postgresql://')

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        logger.info('db.py: PostgreSQL mode (%s...)', DATABASE_URL[:40])
    except ImportError as exc:
        raise RuntimeError(
            'DATABASE_URL points to Postgres but psycopg2 is not installed. '
            'Run: pip install psycopg2-binary'
        ) from exc
else:
    SQLITE_PATH = os.environ.get('DATABASE_PATH', 'postpilot.db')
    logger.info('db.py: SQLite mode (%s)', SQLITE_PATH)

# Query placeholder differs between backends
placeholder = '%s' if USE_POSTGRES else '?'


from flask import has_request_context

class DBConnectionWrapper:
    """
    Wrapper around sqlite3 or psycopg2 connection to provide a unified API.
    Enables calling connection.execute(...) directly on PostgreSQL and SQLite,
    and automatically translates placeholders (?) to (%s) for PostgreSQL.
    """
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        if USE_POSTGRES:
            import psycopg2.extras
            return self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        return self.conn.cursor()

    def execute(self, sql: str, params: tuple = ()):
        # Auto-translate SQLite syntax to Postgres compatible syntax
        sql_adapted = adapt_schema(sql)
        if USE_POSTGRES:
            sql_adapted = sql_adapted.replace('?', '%s')
            cur = self.cursor()
            cur.execute(sql_adapted, params)
            return cur
        else:
            # For SQLite, ensure it uses standard sqlite Row/cursor execution
            return self.conn.execute(sql_adapted, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        try:
            self.conn.rollback()
        except Exception:
            pass

    def close(self):
        if getattr(self, 'request_scoped', False):
            return
        self.conn.close()



def get_connection():
    """Return a unified DB connection wrapper. Caller is responsible for closing it."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
    return DBConnectionWrapper(conn)


def row_to_dict(row) -> dict:
    """Convert a sqlite3.Row or psycopg2 RealDictRow to a plain dict."""
    if row is None:
        return {}
    if isinstance(row, sqlite3.Row):
        return dict(row)
    if isinstance(row, dict):
        return row
    # psycopg2 tuple row — caller should use RealDictCursor instead
    return dict(enumerate(row))


def adapt_schema(sql: str) -> str:
    """
    Translate SQLite-flavoured DDL to PostgreSQL-compatible DDL.
    Called at table creation time in each module's init_db().
    """
    if not USE_POSTGRES:
        return sql
    # Replace primary key syntax
    sql = sql.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
    # Replace default epoch syntax
    sql = sql.replace("DEFAULT (strftime('%s','now'))",
                      'DEFAULT (EXTRACT(EPOCH FROM NOW())::BIGINT)')
    # Postgres uses EXCLUDED (uppercase) and requires ON CONFLICT (...) with space
    sql = sql.replace('ON CONFLICT(user_id, platform) DO UPDATE SET',
                      'ON CONFLICT (user_id, platform) DO UPDATE SET')
    sql = sql.replace('ON CONFLICT(user_id) DO UPDATE SET',
                      'ON CONFLICT (user_id) DO UPDATE SET')
    return sql


def execute_one(sql: str, params: tuple = (), commit: bool = False):
    """Run a single statement, optionally commit. Returns cursor.fetchone()."""
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        if commit:
            conn.commit()
        try:
            row = cur.fetchone()
            return row_to_dict(row) if row else None
        except Exception:
            return None
    finally:
        conn.close()


def execute_all(sql: str, params: tuple = ()) -> list:
    """Run a SELECT and return all rows as a list."""
    conn = get_connection()
    try:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()
