"""
user_manager.py — Multi-User Accounts & DB Schema (Phase 5 Session 9)

Owns all four Phase 5 tables:
  users             — Flask-Login auth, subscription tier, Stripe IDs
  business_profiles — Per-user business info, subdomain, AI prefs
  api_keys          — Public API key hashes (Phase 5 Session 12)
  post_history      — Every published / scheduled post (analytics + repost)

Also owns the existing platform_tokens table created by auth_manager.py;
both modules share the same postpilot.db file via DB_PATH.

Usage:
    from modules.user_manager import UserManager, User
    user = UserManager.create_user('hello@example.com', 'password123')
    user = UserManager.get_user_by_email('hello@example.com')
    UserManager.verify_password(user, 'password123')  # → True
"""

import os
import uuid
import sqlite3
import hashlib
import secrets
import logging
from datetime import datetime
from typing import Optional

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

logger  = logging.getLogger(__name__)
DB_PATH = os.environ.get('DATABASE_URL', 'postpilot.db')


# ---------------------------------------------------------------------------
# Flask-Login User model
# ---------------------------------------------------------------------------
class User(UserMixin):
    """
    Lightweight user object loaded from the DB and stored in the Flask-Login
    session.  Matches the columns in the `users` table exactly.
    """

    def __init__(self, row: dict):
        self.id                     = row['id']
        self.email                  = row['email']
        self.password_hash          = row['password_hash']
        self.display_name           = row.get('display_name') or ''
        self.subscription_tier      = row.get('subscription_tier', 'free')
        self.stripe_customer_id     = row.get('stripe_customer_id')
        self.stripe_sub_id          = row.get('stripe_sub_id')
        self.sub_status             = row.get('sub_status', 'active')
        self.sub_current_period_end = row.get('sub_current_period_end')
        self.trial_ends_at          = row.get('trial_ends_at')
        self.is_admin               = bool(row.get('is_admin', 0))
        self.created_at             = row.get('created_at', '')
        self.last_login_at          = row.get('last_login_at')

    # Flask-Login requires get_id() to return a string
    def get_id(self) -> str:
        return self.id

    @property
    def is_free(self) -> bool:
        return self.subscription_tier == 'free'

    @property
    def is_paid(self) -> bool:
        return self.subscription_tier in ('starter', 'growth', 'pro', 'agency')

    def can_use_platform(self, platform: str) -> bool:
        """
        Tier gate: free users can only post to FB + website.
        All paid tiers get all platforms.
        """
        if self.is_paid:
            return True
        free_platforms = {'fb', 'web'}
        return platform in free_platforms

    def ai_captions_limit(self) -> int:
        """Monthly AI caption limit by tier."""
        limits = {'free': 5, 'starter': 30, 'growth': 150, 'pro': 999999, 'agency': 999999}
        return limits.get(self.subscription_tier, 5)

    def __repr__(self):
        return f'<User {self.email} [{self.subscription_tier}]>'


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------
def init_db():
    """
    Create all Phase 5 tables and indexes if they don't exist.
    Safe to call on every app start — uses IF NOT EXISTS throughout.
    """
    conn = _get_conn()

    # ── users ──────────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id                      TEXT PRIMARY KEY,
            email                   TEXT NOT NULL UNIQUE,
            password_hash           TEXT NOT NULL,
            display_name            TEXT,
            subscription_tier       TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id      TEXT,
            stripe_sub_id           TEXT,
            sub_status              TEXT DEFAULT 'active',
            sub_current_period_end  TEXT,
            trial_ends_at           TEXT,
            is_admin                INTEGER NOT NULL DEFAULT 0,
            created_at              TEXT NOT NULL,
            last_login_at           TEXT
        )
    ''')

    # ── business_profiles ─────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS business_profiles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       TEXT    NOT NULL UNIQUE REFERENCES users(id),
            name          TEXT    NOT NULL DEFAULT '',
            business_type TEXT    DEFAULT 'food_truck',
            location      TEXT    DEFAULT '',
            address       TEXT    DEFAULT '',
            lat           REAL,
            lng           REAL,
            hours         TEXT    DEFAULT '',
            phone         TEXT    DEFAULT '',
            website_url   TEXT    DEFAULT '',
            logo_url      TEXT    DEFAULT '',
            prompt_time   TEXT    DEFAULT '07:00',
            timezone      TEXT    DEFAULT 'US/Eastern',
            ai_tone       TEXT    DEFAULT 'friendly',
            ai_keywords   TEXT    DEFAULT '',
            subdomain     TEXT    UNIQUE,
            custom_domain TEXT,
            updated_at    TEXT    NOT NULL
        )
    ''')

    # ── api_keys ───────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT    NOT NULL REFERENCES users(id),
            key_hash     TEXT    NOT NULL UNIQUE,
            label        TEXT    DEFAULT 'Default key',
            is_active    INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT,
            created_at   TEXT    NOT NULL
        )
    ''')

    # ── post_history ───────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS post_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT    NOT NULL REFERENCES users(id),
            caption      TEXT    NOT NULL,
            content_type TEXT    DEFAULT 'text',
            image_url    TEXT,
            video_url    TEXT,
            platforms    TEXT,
            results      TEXT,
            scheduled_at TEXT,
            posted_at    TEXT    NOT NULL,
            status       TEXT    DEFAULT 'published'
        )
    ''')

    # ── indexes ────────────────────────────────────────────────────────────
    conn.execute('CREATE INDEX IF NOT EXISTS idx_biz_user      ON business_profiles(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_api_user      ON api_keys(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_user  ON post_history(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_date  ON post_history(posted_at)')

    conn.commit()
    conn.close()
    logger.info('user_manager: DB schema initialised')


# ---------------------------------------------------------------------------
# UserManager — all user CRUD operations
# ---------------------------------------------------------------------------
class UserManager:

    # ── Create ─────────────────────────────────────────────────────────────
    @staticmethod
    def create_user(
        email: str,
        password: str,
        display_name: str = '',
        tier: str = 'free',
    ) -> Optional['User']:
        """
        Register a new user.  Returns the User object, or None if the
        email is already taken.

        Args:
            email:        Must be unique.
            password:     Plain-text — hashed with bcrypt before storage.
            display_name: Optional human name / business name.
            tier:         Subscription tier (default 'free').
        """
        email = email.strip().lower()
        try:
            conn  = _get_conn()
            uid   = str(uuid.uuid4())
            phash = generate_password_hash(password)
            now   = datetime.utcnow().isoformat()
            conn.execute(
                '''
                INSERT INTO users
                    (id, email, password_hash, display_name, subscription_tier, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (uid, email, phash, display_name, tier, now),
            )
            # Create empty business profile so it always exists
            conn.execute(
                'INSERT INTO business_profiles (user_id, updated_at) VALUES (?, ?)',
                (uid, now),
            )
            conn.commit()
            conn.close()
            logger.info('User created: %s [%s]', email, uid)
            return UserManager.get_user(uid)
        except sqlite3.IntegrityError:
            logger.warning('create_user: email already exists: %s', email)
            return None
        except Exception as e:
            logger.error('create_user error: %s', e)
            return None

    # ── Read ───────────────────────────────────────────────────────────────
    @staticmethod
    def get_user(user_id: str) -> Optional['User']:
        """Load a user by UUID. Returns None if not found."""
        conn = _get_conn()
        row  = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        return User(dict(row)) if row else None

    @staticmethod
    def get_user_by_email(email: str) -> Optional['User']:
        """Load a user by email (case-insensitive). Returns None if not found."""
        conn = _get_conn()
        row  = conn.execute(
            'SELECT * FROM users WHERE LOWER(email) = ?', (email.strip().lower(),)
        ).fetchone()
        conn.close()
        return User(dict(row)) if row else None

    @staticmethod
    def verify_password(user: 'User', password: str) -> bool:
        """Returns True if password matches the stored hash."""
        return check_password_hash(user.password_hash, password)

    @staticmethod
    def touch_login(user_id: str):
        """Update last_login_at timestamp — called on successful login."""
        conn = _get_conn()
        conn.execute(
            'UPDATE users SET last_login_at = ? WHERE id = ?',
            (datetime.utcnow().isoformat(), user_id),
        )
        conn.commit()
        conn.close()

    # ── Subscription ───────────────────────────────────────────────────────
    @staticmethod
    def update_subscription(
        user_id: str,
        tier: str,
        stripe_customer_id: str = None,
        stripe_sub_id: str = None,
        sub_status: str = 'active',
        period_end: str = None,
    ):
        """
        Update subscription tier and Stripe metadata.
        Called by billing_manager.py on Stripe webhook events.

        Args:
            tier:               'free' | 'starter' | 'growth' | 'pro' | 'agency'
            stripe_customer_id: Stripe customer ID (cus_xxx)
            stripe_sub_id:      Stripe subscription ID (sub_xxx)
            sub_status:         'active' | 'past_due' | 'cancelled'
            period_end:         ISO datetime string of current period end
        """
        conn = _get_conn()
        conn.execute(
            '''
            UPDATE users SET
                subscription_tier      = ?,
                stripe_customer_id     = COALESCE(?, stripe_customer_id),
                stripe_sub_id          = COALESCE(?, stripe_sub_id),
                sub_status             = ?,
                sub_current_period_end = COALESCE(?, sub_current_period_end)
            WHERE id = ?
            ''',
            (tier, stripe_customer_id, stripe_sub_id, sub_status, period_end, user_id),
        )
        conn.commit()
        conn.close()
        logger.info('Subscription updated: user=%s tier=%s status=%s', user_id, tier, sub_status)

    # ── Business Profile ───────────────────────────────────────────────────
    @staticmethod
    def get_business_profile(user_id: str) -> dict:
        """
        Fetch the business profile for a user.
        Always returns a dict (empty defaults if profile not yet filled in).
        """
        conn = _get_conn()
        row  = conn.execute(
            'SELECT * FROM business_profiles WHERE user_id = ?', (user_id,)
        ).fetchone()
        conn.close()
        if not row:
            return {}
        d = dict(row)
        # Parse hours JSON if stored as JSON string
        import json
        if d.get('hours') and d['hours'].startswith('{'):
            try:
                d['hours'] = json.loads(d['hours'])
            except Exception:
                pass
        return d

    @staticmethod
    def save_business_profile(user_id: str, data: dict):
        """
        Upsert business profile fields.  Only updates fields present in `data`.

        Args:
            data: Any subset of business_profiles columns.
                  hours may be passed as a dict — it will be JSON-encoded.
        """
        import json
        if isinstance(data.get('hours'), dict):
            data['hours'] = json.dumps(data['hours'])

        allowed = {
            'name', 'business_type', 'location', 'address', 'lat', 'lng',
            'hours', 'phone', 'website_url', 'logo_url', 'prompt_time',
            'timezone', 'ai_tone', 'ai_keywords', 'subdomain', 'custom_domain',
        }
        fields = {k: v for k, v in data.items() if k in allowed}
        if not fields:
            return

        fields['updated_at'] = datetime.utcnow().isoformat()
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values     = list(fields.values()) + [user_id]

        conn = _get_conn()
        conn.execute(
            f'UPDATE business_profiles SET {set_clause} WHERE user_id = ?',
            values,
        )
        conn.commit()
        conn.close()
        logger.info('Business profile updated for user=%s', user_id)

    # ── Post History ───────────────────────────────────────────────────────
    @staticmethod
    def log_post(
        user_id:      str,
        caption:      str,
        content_type: str = 'text',
        image_url:    str = None,
        video_url:    str = None,
        platforms:    dict = None,
        results:      dict = None,
        scheduled_at: str = None,
        status:       str = 'published',
    ) -> int:
        """
        Save a post to history.  Returns the new row id.
        Called by the /api/push_all and /api/publish routes after every push.
        """
        import json
        conn = _get_conn()
        cur  = conn.execute(
            '''
            INSERT INTO post_history
                (user_id, caption, content_type, image_url, video_url,
                 platforms, results, scheduled_at, posted_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id, caption, content_type, image_url, video_url,
                json.dumps(platforms) if platforms else None,
                json.dumps(results)   if results   else None,
                scheduled_at,
                datetime.utcnow().isoformat(),
                status,
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    @staticmethod
    def get_post_history(
        user_id:  str,
        limit:    int = 50,
        offset:   int = 0,
        status:   str = None,
    ) -> list[dict]:
        """
        Retrieve recent post history for a user.

        Args:
            limit:  Max rows to return (default 50).
            offset: Pagination offset.
            status: Filter by 'published' | 'scheduled' | 'failed' | None (all).

        Returns:
            List of dicts, newest first.
        """
        import json
        conn   = _get_conn()
        where  = 'WHERE user_id = ?'
        params = [user_id]
        if status:
            where  += ' AND status = ?'
            params.append(status)
        rows = conn.execute(
            f'SELECT * FROM post_history {where} ORDER BY posted_at DESC LIMIT ? OFFSET ?',
            params + [limit, offset],
        ).fetchall()
        conn.close()

        result = []
        for row in rows:
            d = dict(row)
            for field in ('platforms', 'results'):
                if d.get(field):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception:
                        pass
            result.append(d)
        return result

    # ── API Key management (stub — fully built in Session 12) ─────────────
    @staticmethod
    def create_api_key(user_id: str, label: str = 'Default key') -> str:
        """
        Generate a new API key, store its SHA-256 hash, return the raw key.
        The raw key is shown ONCE and never stored — same pattern as GitHub.

        Returns:
            The raw key string (e.g. 'pp_live_abc123...').
        """
        raw_key  = 'pp_live_' + secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        now      = datetime.utcnow().isoformat()
        conn     = _get_conn()
        conn.execute(
            'INSERT INTO api_keys (user_id, key_hash, label, created_at) VALUES (?, ?, ?, ?)',
            (user_id, key_hash, label, now),
        )
        conn.commit()
        conn.close()
        logger.info('API key created for user=%s label=%s', user_id, label)
        return raw_key

    @staticmethod
    def lookup_api_key(raw_key: str) -> Optional['User']:
        """
        Verify a raw API key and return the owning User.
        Used by the /v1/* API routes (Session 12).
        Updates last_used_at on hit.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn     = _get_conn()
        row      = conn.execute(
            'SELECT user_id FROM api_keys WHERE key_hash = ? AND is_active = 1',
            (key_hash,),
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?',
                (datetime.utcnow().isoformat(), key_hash),
            )
            conn.commit()
        conn.close()
        return UserManager.get_user(row['user_id']) if row else None


# ---------------------------------------------------------------------------
# Bootstrap on import
# ---------------------------------------------------------------------------
try:
    init_db()
except Exception as e:
    logger.error('user_manager init_db failed: %s', e)
