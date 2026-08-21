"""
user_manager.py — User accounts for Post-Pilot (pp schema on Supabase).

Auth is handled by Supabase Auth (magic links).
This module syncs/reads the users mirror table and related business/post data.

Canonical tables (match Alembic + automation):
  users, business_profiles, post_history, api_keys

All queries use `?` placeholders; db.py converts for PostgreSQL.
`::uuid` casts are stripped automatically on SQLite via adapt_schema.
"""

import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import datetime
from typing import Optional

from flask_login import UserMixin

from modules.database import get_db

logger = logging.getLogger(__name__)

_VALID_PLANS = frozenset({'free', 'starter', 'pro', 'agency'})


# ---------------------------------------------------------------------------
# Flask-Login User model
# ---------------------------------------------------------------------------
class User(UserMixin):
    """Lightweight user object that maps to users columns."""

    def __init__(self, row: dict):
        self.id                 = str(row['id'])
        self.email              = row['email']
        self.password_hash      = row.get('password_hash') or ''
        self.full_name          = row.get('full_name') or row.get('display_name') or ''
        self.business_name      = row.get('business_name') or ''
        # Accept either live `plan` or Alembic `subscription_tier`
        self.plan               = (
            row.get('plan')
            or row.get('subscription_tier')
            or 'free'
        )
        self.stripe_customer_id = row.get('stripe_customer_id')
        self.stripe_sub_id      = row.get('stripe_sub_id')
        self.sub_status         = row.get('sub_status') or 'active'
        self.sub_current_period_end = row.get('sub_current_period_end')
        self._is_active         = bool(row.get('is_active', True))
        self.is_verified        = bool(row.get('is_verified', True))
        self.created_at         = row.get('created_at', '')
        self.updated_at         = row.get('updated_at', '')

    def get_id(self) -> str:
        return self.id

    @property
    def is_active(self) -> bool:
        """Flask-Login uses this; must not collide with UserMixin's property."""
        return self._is_active

    @property
    def display_name(self) -> str:
        return self.full_name or self.business_name or self.email.split('@')[0]

    @property
    def subscription_tier(self) -> str:
        return self.plan

    @property
    def is_free(self) -> bool:
        return self.plan == 'free'

    @property
    def is_paid(self) -> bool:
        return self.plan in ('starter', 'pro', 'agency')

    def can_use_platform(self, platform: str) -> bool:
        if self.is_paid:
            return True
        return platform in {'fb', 'web'}

    def ai_captions_limit(self) -> int:
        limits = {'free': 5, 'starter': 30, 'pro': 999999, 'agency': 999999}
        return limits.get(self.plan, 5)

    def __repr__(self):
        return f'<User {self.email} [{self.plan}]>'


def _get_conn():
    return get_db()


def _normalize_plan(plan: Optional[str]) -> str:
    """Never accept arbitrary paid tiers from untrusted callers."""
    p = (plan or 'free').strip().lower()
    if p not in _VALID_PLANS:
        return 'free'
    return p


# ---------------------------------------------------------------------------
# UserManager
# ---------------------------------------------------------------------------
class UserManager:

    # -- Upsert (called after successful magic link confirm) -----------------
    @staticmethod
    def upsert_user(
        user_id: str,
        email: str,
        full_name: str = '',
        business_name: str = '',
        plan: str = 'free',
    ) -> Optional[User]:
        """
        Insert a new user or return existing after Supabase OTP verify.
        New users always start on free — paid tiers come only from Stripe webhooks.
        """
        plan = 'free'  # ignore client-supplied plan (anti privilege-escalation)
        try:
            conn = _get_conn()
            conn.execute(
                '''
                INSERT INTO users (id, email, full_name, business_name, plan, is_verified)
                VALUES (?::uuid, ?, ?, ?, ?, TRUE)
                ON CONFLICT (id) DO UPDATE SET
                    email         = EXCLUDED.email,
                    updated_at    = NOW()
                ''',
                (str(user_id), email.strip().lower(), full_name, business_name, plan),
            )
            conn.commit()
            logger.info('User upserted: %s [%s]', email, user_id)
            return UserManager.get_user(user_id)
        except Exception as exc:
            logger.error('upsert_user failed for %s: %s', email, exc)
            return None

    # -- Read ---------------------------------------------------------------
    @staticmethod
    def get_user(user_id: str) -> Optional[User]:
        if not user_id:
            return None
        try:
            conn = _get_conn()
            try:
                cur = conn.execute(
                    'SELECT * FROM users WHERE id = ?',
                    (str(user_id),),
                )
            except Exception:
                cur = conn.execute(
                    'SELECT * FROM users WHERE id = ?::uuid',
                    (str(user_id),),
                )
            row = cur.fetchone()
            return User(dict(row)) if row else None
        except Exception as exc:
            logger.error('get_user(%s) failed: %s', user_id, exc)
            return None

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        try:
            conn = _get_conn()
            cur  = conn.execute(
                'SELECT * FROM users WHERE LOWER(email) = ?',
                (email.strip().lower(),),
            )
            row = cur.fetchone()
            return User(dict(row)) if row else None
        except Exception as exc:
            logger.error('get_user_by_email(%s) failed: %s', email, exc)
            return None

    @staticmethod
    def touch_login(user_id: str):
        try:
            conn = _get_conn()
            conn.execute(
                'UPDATE users SET updated_at = NOW() WHERE id = ?::uuid',
                (str(user_id),),
            )
            conn.commit()
        except Exception as exc:
            logger.warning('touch_login(%s) failed (non-fatal): %s', user_id, exc)

    # -- Update -------------------------------------------------------------
    @staticmethod
    def update_profile(user_id: str, full_name: str = None, business_name: str = None):
        fields, values = [], []
        if full_name is not None:
            fields.append('full_name = ?')
            values.append(full_name)
        if business_name is not None:
            fields.append('business_name = ?')
            values.append(business_name)
        if not fields:
            return
        values.append(str(user_id))
        conn = _get_conn()
        conn.execute(
            f"UPDATE users SET {', '.join(fields)}, updated_at = NOW() WHERE id = ?::uuid",
            values,
        )
        conn.commit()

    @staticmethod
    def update_subscription(
        user_id: str,
        plan: str = None,
        tier: str = None,
        stripe_customer_id: str = None,
        stripe_sub_id: str = None,
        sub_status: str = None,
        period_end=None,
    ):
        """
        Persist Stripe-driven subscription state.
        Accepts both `plan` and `tier` (BillingManager uses tier=).
        """
        resolved = _normalize_plan(plan if plan is not None else tier)
        period_val = None
        if period_end is not None:
            period_val = period_end if isinstance(period_end, str) else str(period_end)

        conn = _get_conn()
        conn.execute(
            '''
            UPDATE users SET
                plan                   = ?,
                stripe_customer_id     = COALESCE(?, stripe_customer_id),
                stripe_sub_id          = COALESCE(?, stripe_sub_id),
                sub_status             = COALESCE(?, sub_status),
                sub_current_period_end = COALESCE(?, sub_current_period_end),
                updated_at             = NOW()
            WHERE id = ?::uuid
            ''',
            (
                resolved,
                stripe_customer_id,
                stripe_sub_id,
                sub_status,
                period_val,
                str(user_id),
            ),
        )
        conn.commit()
        logger.info(
            'Subscription updated: user=%s plan=%s status=%s',
            user_id, resolved, sub_status,
        )

    # -- Business profile (what automation_agent reads) ---------------------
    @staticmethod
    def save_business_profile(user_id: str, info: dict) -> bool:
        """Upsert business_profiles for the user."""
        if not isinstance(info, dict):
            info = {}
        name          = (info.get('name') or info.get('business_name') or '').strip()
        business_type = (info.get('business_type') or info.get('type') or 'food_truck').strip()
        location      = (info.get('location') or '').strip()
        hours         = (info.get('hours') or '').strip()
        prompt_time   = (info.get('prompt_time') or '07:00').strip()
        timezone      = (info.get('timezone') or 'US/Eastern').strip()
        ai_tone       = (info.get('ai_tone') or 'friendly').strip()
        ai_keywords   = (info.get('ai_keywords') or '').strip()
        updated_at    = datetime.utcnow().isoformat()

        try:
            conn = _get_conn()
            conn.execute(
                '''
                INSERT INTO business_profiles
                    (user_id, name, business_type, location, hours,
                     prompt_time, timezone, ai_tone, ai_keywords, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name          = excluded.name,
                    business_type = excluded.business_type,
                    location      = excluded.location,
                    hours         = excluded.hours,
                    prompt_time   = excluded.prompt_time,
                    timezone      = excluded.timezone,
                    ai_tone       = excluded.ai_tone,
                    ai_keywords   = excluded.ai_keywords,
                    updated_at    = excluded.updated_at
                ''',
                (
                    str(user_id), name, business_type, location, hours,
                    prompt_time, timezone, ai_tone, ai_keywords, updated_at,
                ),
            )
            conn.commit()
            # Keep users.business_name in sync when provided
            if name:
                try:
                    UserManager.update_profile(user_id, business_name=name)
                except Exception:
                    pass
            return True
        except Exception as exc:
            logger.error('save_business_profile(%s) failed: %s', user_id, exc)
            return False

    @staticmethod
    def get_business_profile(user_id: str) -> dict:
        try:
            conn = _get_conn()
            cur = conn.execute(
                'SELECT * FROM business_profiles WHERE user_id = ? LIMIT 1',
                (str(user_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        except Exception as exc:
            logger.warning('get_business_profile(%s) failed: %s', user_id, exc)
            return {}

    # -- Post history -------------------------------------------------------
    @staticmethod
    def log_post(
        user_id: str,
        caption: str = None,
        content: str = None,
        platform: str = None,
        content_type: str = 'text',
        image_url: str = None,
        video_url: str = None,
        platforms: list = None,
        results: dict = None,
        status: str = 'published',
        scheduled_at=None,
        media_urls: list = None,
        platform_post_id: str = None,
        **_extra,
    ) -> str:
        """
        Insert into post_history.
        Accepts API-style kwargs (caption/platforms/results) and legacy
        (content/platform) so callers do not need dual paths.
        """
        body = caption if caption is not None else (content or '')
        plats = platforms
        if plats is None and platform:
            plats = [platform]
        plats = plats or []

        # scheduled_at: store unix int when possible (scheduler_worker)
        sched_val = None
        if scheduled_at not in (None, ''):
            if isinstance(scheduled_at, (int, float)):
                sched_val = int(scheduled_at)
            else:
                try:
                    # ISO or "YYYY-MM-DD HH:MM" → best-effort
                    sched_val = int(datetime.fromisoformat(str(scheduled_at).replace('Z', '')).timestamp())
                except Exception:
                    sched_val = None

        created = int(time.time())
        conn = _get_conn()
        cur = conn.execute(
            '''
            INSERT INTO post_history
                (user_id, caption, content_type, image_url, video_url,
                 platforms, results, status, scheduled_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                str(user_id),
                body,
                content_type or 'text',
                image_url,
                video_url,
                json.dumps(plats),
                json.dumps(results or {}),
                status or 'published',
                sched_val,
                created,
            ),
        )
        conn.commit()
        try:
            row_id = cur.lastrowid
        except Exception:
            row_id = None
        return str(row_id or created)

    @staticmethod
    def count_posts_this_month(user_id: str) -> int:
        """Count post_history rows created in the current UTC month."""
        try:
            conn = _get_conn()
            # Unix range for current month
            now = datetime.utcnow()
            start = datetime(now.year, now.month, 1)
            start_ts = int(start.timestamp())
            cur = conn.execute(
                '''
                SELECT COUNT(*) AS n FROM post_history
                WHERE user_id = ? AND created_at >= ?
                ''',
                (str(user_id), start_ts),
            )
            row = cur.fetchone()
            if not row:
                return 0
            d = dict(row) if not isinstance(row, dict) else row
            return int(d.get('n') or d.get('count') or list(d.values())[0] or 0)
        except Exception as exc:
            logger.warning('count_posts_this_month(%s) failed: %s', user_id, exc)
            return 0

    @staticmethod
    def get_post_history(
        user_id: str, limit: int = 50, offset: int = 0, status: str = None,
    ) -> list:
        conn   = _get_conn()
        where  = 'WHERE user_id = ?'
        params = [str(user_id)]
        if status:
            where += ' AND status = ?'
            params.append(status)
        cur  = conn.execute(
            f'SELECT * FROM post_history {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
            params + [limit, offset],
        )
        result = []
        for row in cur.fetchall():
            d = dict(row)
            for key in ('platforms', 'results'):
                if d.get(key) and isinstance(d[key], str):
                    try:
                        d[key] = json.loads(d[key])
                    except Exception:
                        pass
            result.append(d)
        return result

    # -- API Keys -----------------------------------------------------------
    @staticmethod
    def create_api_key(user_id: str, label: str = 'Default key') -> str:
        raw_key  = 'pp_live_' + secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn     = _get_conn()
        conn.execute(
            'INSERT INTO api_keys (id, user_id, key_hash, label) VALUES (?::uuid, ?::uuid, ?, ?)',
            (str(uuid.uuid4()), str(user_id), key_hash, label),
        )
        conn.commit()
        logger.info('API key created for user=%s', user_id)
        return raw_key

    @staticmethod
    def lookup_api_key(raw_key: str) -> Optional[User]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        conn     = _get_conn()
        cur      = conn.execute(
            'SELECT user_id FROM api_keys WHERE key_hash = ? AND is_active = TRUE',
            (key_hash,),
        )
        row = cur.fetchone()
        if row:
            conn.execute(
                'UPDATE api_keys SET last_used = NOW() WHERE key_hash = ?',
                (key_hash,),
            )
            conn.commit()
        return UserManager.get_user(str(dict(row)['user_id'])) if row else None
