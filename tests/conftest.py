"""
conftest.py -- pytest fixtures for Post-Pilot.

Forces SQLite so no real DB is needed to run tests.
Disables CSRF so form posts work in tests (unless a test re-enables it).
"""

import hashlib
import os
import time
from unittest.mock import MagicMock, patch

# Set env before any app imports.
# Force a file-backed SQLite DB — CI previously set DATABASE_PATH=:memory:, which
# gives each connection a separate empty DB and breaks platform_tokens init.
os.environ['DATABASE_URL'] = ''
os.environ['DATABASE_PATH'] = 'test_postpilot.db'
try:
    if os.path.exists('test_postpilot.db'):
        os.remove('test_postpilot.db')
except Exception:
    pass
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-key-for-ci-only')
os.environ.setdefault('TOKEN_ENCRYPTION_KEY', 'nZeXTE9lxj2Vt5nUWGvfeVacq9+sz5XPLBuiA9wqjy4=')

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('APP_ENV', 'development')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')
os.environ.setdefault('STRIPE_SECRET_KEY', 'dummy')
os.environ.setdefault('FACEBOOK_APP_ID', 'dummy')
os.environ.setdefault('FACEBOOK_APP_SECRET', 'dummy')
os.environ.setdefault('GOOGLE_CLIENT_ID', 'dummy')
os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'dummy')
os.environ.setdefault('TIKTOK_CLIENT_KEY', 'dummy')
os.environ.setdefault('TIKTOK_CLIENT_SECRET', 'dummy')
os.environ.setdefault('SRN_SECRET', 'test_srn_secret_12345')

import pytest

SQLITE_TABLES_DDL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id                     TEXT PRIMARY KEY,
        email                  TEXT UNIQUE NOT NULL,
        password_hash          TEXT,
        full_name              TEXT,
        display_name           TEXT,
        business_name          TEXT,
        subscription_tier      TEXT NOT NULL DEFAULT 'free',
        plan                   TEXT NOT NULL DEFAULT 'free',
        stripe_customer_id     TEXT,
        stripe_sub_id          TEXT,
        sub_status             TEXT DEFAULT 'active',
        sub_current_period_end TEXT,
        trial_ends_at          TEXT,
        is_admin               INTEGER NOT NULL DEFAULT 0,
        is_active              INTEGER NOT NULL DEFAULT 1,
        is_verified            INTEGER NOT NULL DEFAULT 1,
        created_at             INTEGER,
        updated_at             INTEGER,
        last_login_at          INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS business_profiles (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       TEXT NOT NULL UNIQUE,
        name          TEXT DEFAULT '',
        business_type TEXT DEFAULT 'food_truck',
        location      TEXT DEFAULT '',
        address       TEXT DEFAULT '',
        lat           REAL,
        lng           REAL,
        hours         TEXT DEFAULT '',
        phone         TEXT DEFAULT '',
        website_url   TEXT DEFAULT '',
        logo_url      TEXT DEFAULT '',
        prompt_time   TEXT DEFAULT '07:00',
        timezone      TEXT DEFAULT 'US/Eastern',
        ai_tone       TEXT DEFAULT 'friendly',
        ai_keywords   TEXT DEFAULT '',
        subdomain     TEXT UNIQUE,
        custom_domain TEXT,
        updated_at    TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS post_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      TEXT NOT NULL,
        caption      TEXT,
        content_type TEXT DEFAULT 'text',
        image_url    TEXT,
        video_url    TEXT,
        platforms    TEXT,
        results      TEXT,
        status       TEXT DEFAULT 'published',
        post_url     TEXT,
        scheduled_at INTEGER,
        created_at   INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS platform_tokens (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       TEXT NOT NULL DEFAULT 'default',
        platform      TEXT NOT NULL,
        access_token  TEXT NOT NULL,
        refresh_token TEXT,
        expires_at    TEXT,
        token_meta    TEXT,
        updated_at    TEXT NOT NULL,
        UNIQUE (user_id, platform)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS platform_settings (
        user_id  TEXT NOT NULL,
        platform TEXT NOT NULL,
        enabled  INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (user_id, platform)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS specials (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        item_name       TEXT NOT NULL,
        description     TEXT,
        post_date       TEXT NOT NULL,
        post_time       TEXT NOT NULL,
        platforms       TEXT,
        content_type    TEXT DEFAULT 'daily_special',
        tone            TEXT DEFAULT 'friendly',
        image_url       TEXT,
        status          TEXT DEFAULT 'pending',
        post_history_id INTEGER,
        created_at      INTEGER,
        updated_at      INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        title           TEXT NOT NULL,
        description     TEXT,
        event_date      TEXT NOT NULL,
        event_end_date  TEXT,
        post_date       TEXT NOT NULL,
        post_time       TEXT NOT NULL,
        event_type      TEXT DEFAULT 'event',
        platforms       TEXT,
        tone            TEXT DEFAULT 'hype',
        image_url       TEXT,
        ticket_url      TEXT,
        status          TEXT DEFAULT 'pending',
        post_history_id INTEGER,
        created_at      INTEGER,
        updated_at      INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS hours_overrides (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        title           TEXT NOT NULL,
        message         TEXT,
        override_type   TEXT DEFAULT 'closure',
        post_date       TEXT NOT NULL,
        post_time       TEXT NOT NULL,
        platforms       TEXT,
        tone            TEXT DEFAULT 'friendly',
        status          TEXT DEFAULT 'pending',
        post_history_id INTEGER,
        created_at      INTEGER,
        updated_at      INTEGER
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      TEXT NOT NULL,
        label        TEXT NOT NULL DEFAULT 'My Key',
        key_hash     TEXT,
        key_value    TEXT,
        key_preview  TEXT,
        is_active    INTEGER NOT NULL DEFAULT 1,
        active       INTEGER NOT NULL DEFAULT 1,
        created_at   INTEGER,
        expires_at   INTEGER,
        last_used_at INTEGER,
        last_used    INTEGER,
        call_count   INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS websites (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL UNIQUE,
        config     TEXT,
        published  INTEGER NOT NULL DEFAULT 0,
        subdomain  TEXT UNIQUE,
        updated_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS inbox_items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             TEXT NOT NULL,
        platform            TEXT NOT NULL,
        platform_post_id    TEXT,
        platform_comment_id TEXT NOT NULL,
        author_id           TEXT,
        author_name         TEXT,
        comment_text        TEXT NOT NULL,
        comment_time        TEXT,
        post_context        TEXT,
        sentiment           TEXT DEFAULT 'neutral',
        ai_draft_reply      TEXT,
        final_reply         TEXT,
        status              TEXT DEFAULT 'pending',
        auto_replied        INTEGER DEFAULT 0,
        replied_at          INTEGER,
        hidden_at           INTEGER,
        created_at          INTEGER DEFAULT (strftime('%s','now')),
        updated_at          INTEGER DEFAULT (strftime('%s','now')),
        UNIQUE(platform, platform_comment_id)
    );
    """,
]


@pytest.fixture(scope='session')
def app():
    import app as flask_app
    flask_app.app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'LOGIN_DISABLED': False,
    })
    with flask_app.app.app_context():
        from modules.database import get_db
        db = get_db()
        for ddl in SQLITE_TABLES_DDL:
            try:
                db.execute(ddl)
            except Exception:
                pass
        db.commit()

        # Seed default test user in users table
        db.execute(
            """
            INSERT OR REPLACE INTO users (id, email, full_name, display_name, subscription_tier, plan, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            ('00000000-0000-4000-8000-000000000001', 'testuser@postpilot.dev', 'Test User', 'Test User', 'starter', 'starter'),
        )
        db.commit()

    yield flask_app.app
    try:
        import gc
        gc.collect()
        if os.path.exists('test_postpilot.db'):
            os.remove('test_postpilot.db')
    except Exception:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_mock_user(uid='00000000-0000-4000-8000-000000000001',
                    email='testuser@postpilot.dev',
                    tier='starter'):
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_anonymous = False
    user.id = uid
    user.email = email
    user.subscription_tier = tier
    user.plan = tier
    user.get_id = lambda: uid
    return user


@pytest.fixture()
def registered_user():
    return {
        'email': 'testuser@postpilot.dev',
        'password': 'unused',
        'id': '00000000-0000-4000-8000-000000000001',
    }


@pytest.fixture()
def logged_in_client(client, registered_user, app):
    """
    Authenticated test client. Magic-link auth has no password login,
    so we stub flask-login's user_loader for the session.
    """
    user = _make_mock_user(registered_user['id'], registered_user['email'], 'starter')

    def _loader(uid):
        if str(uid) == registered_user['id']:
            return user
        return None

    with patch.object(app.login_manager, '_user_callback', _loader):
        with client.session_transaction() as sess:
            sess['_user_id'] = registered_user['id']
            sess['_fresh'] = True
        client._test_user = user
        yield client


@pytest.fixture()
def valid_api_key(app, registered_user):
    """Create and return a valid active Bearer API key in DB."""
    raw_key = 'pp_live_testvalidkey1234567890abcdef'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO api_keys
              (id, user_id, label, key_hash, key_value, key_preview, is_active, active, created_at, expires_at, call_count)
            VALUES (1001, ?, 'Test Valid Key', ?, ?, 'pp_live_test...', 1, 1, ?, NULL, 0)
            """,
            (registered_user['id'], key_hash, raw_key, int(time.time())),
        )
        db.commit()
    return raw_key


@pytest.fixture()
def expired_api_key(app, registered_user):
    """Create and return an expired Bearer API key in DB."""
    raw_key = 'pp_live_testexpiredkey1234567890abcdef'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO api_keys
              (id, user_id, label, key_hash, key_value, key_preview, is_active, active, created_at, expires_at, call_count)
            VALUES (1002, ?, 'Test Expired Key', ?, ?, 'pp_live_test...', 1, 1, ?, ?, 0)
            """,
            (registered_user['id'], key_hash, raw_key, int(time.time()) - 1000, int(time.time()) - 100),
        )
        db.commit()
    return raw_key


@pytest.fixture()
def revoked_api_key(app, registered_user):
    """Create and return an inactive/revoked Bearer API key in DB."""
    raw_key = 'pp_live_testrevokedkey1234567890abcdef'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO api_keys
              (id, user_id, label, key_hash, key_value, key_preview, is_active, active, created_at, expires_at, call_count)
            VALUES (1003, ?, 'Test Revoked Key', ?, ?, 'pp_live_test...', 0, 0, ?, NULL, 0)
            """,
            (registered_user['id'], key_hash, raw_key, int(time.time())),
        )
        db.commit()
    return raw_key
