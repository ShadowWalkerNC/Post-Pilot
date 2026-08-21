"""
modules/models.py
Data models and query helpers for Post-Pilot.

Contains:
- InboxItem: Social media comments ingested from Facebook/Instagram
  with sentiment classification, AI draft replies, and moderation workflow.
"""

import time
import logging
from typing import Optional, List, Dict, Any

from modules.database import get_db

logger = logging.getLogger(__name__)


# SQLite DDL for inbox_items
CREATE_INBOX_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS inbox_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    platform_post_id TEXT,
    platform_comment_id TEXT NOT NULL,
    author_id TEXT,
    author_name TEXT,
    comment_text TEXT NOT NULL,
    comment_time TEXT,
    post_context TEXT,
    sentiment TEXT DEFAULT 'neutral',
    ai_draft_reply TEXT,
    final_reply TEXT,
    status TEXT DEFAULT 'pending',
    auto_replied INTEGER DEFAULT 0,
    replied_at INTEGER,
    hidden_at INTEGER,
    created_at INTEGER DEFAULT (strftime('%s','now')),
    updated_at INTEGER DEFAULT (strftime('%s','now')),
    UNIQUE(platform, platform_comment_id)
);
CREATE INDEX IF NOT EXISTS idx_inbox_user ON inbox_items (user_id);
CREATE INDEX IF NOT EXISTS idx_inbox_user_status ON inbox_items (user_id, status);
CREATE INDEX IF NOT EXISTS idx_inbox_user_sentiment ON inbox_items (user_id, sentiment);
CREATE INDEX IF NOT EXISTS idx_inbox_platform_comment ON inbox_items (platform, platform_comment_id);
"""


def init_inbox_db():
    """Ensure inbox_items table exists in the database."""
    db = get_db()
    db.execute(CREATE_INBOX_ITEMS_TABLE)
    db.commit()


class InboxItem:
    """
    Model representing an ingested comment from Facebook, Instagram, etc.
    """

    # Status Constants
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_AUTO_REPLIED = 'auto_replied'
    STATUS_HIDDEN = 'hidden'
    STATUS_SKIPPED = 'skipped'
    ALL_STATUSES = [
        STATUS_PENDING,
        STATUS_APPROVED,
        STATUS_AUTO_REPLIED,
        STATUS_HIDDEN,
        STATUS_SKIPPED,
    ]

    # Sentiment Constants
    SENTIMENT_POSITIVE = 'positive'
    SENTIMENT_NEUTRAL = 'neutral'
    SENTIMENT_NEGATIVE = 'negative'
    SENTIMENT_QUESTION = 'question'
    SENTIMENT_SPAM = 'spam'
    ALL_SENTIMENTS = [
        SENTIMENT_POSITIVE,
        SENTIMENT_NEUTRAL,
        SENTIMENT_NEGATIVE,
        SENTIMENT_QUESTION,
        SENTIMENT_SPAM,
    ]

    def __init__(self, row: dict):
        self.id = row.get('id')
        self.user_id = str(row.get('user_id', ''))
        self.platform = row.get('platform', '')
        self.platform_post_id = row.get('platform_post_id')
        self.platform_comment_id = str(row.get('platform_comment_id', ''))
        self.author_id = row.get('author_id')
        self.author_name = row.get('author_name')
        self.comment_text = row.get('comment_text', '')
        self.comment_time = row.get('comment_time')
        self.post_context = row.get('post_context')
        self.sentiment = row.get('sentiment') or self.SENTIMENT_NEUTRAL
        self.ai_draft_reply = row.get('ai_draft_reply')
        self.final_reply = row.get('final_reply')
        self.status = row.get('status') or self.STATUS_PENDING
        self.auto_replied = bool(row.get('auto_replied', 0))
        self.replied_at = row.get('replied_at')
        self.hidden_at = row.get('hidden_at')
        self.created_at = row.get('created_at')
        self.updated_at = row.get('updated_at')

    def to_dict(self) -> Dict[str, Any]:
        """Serialize model instance to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'platform': self.platform,
            'platform_post_id': self.platform_post_id,
            'platform_comment_id': self.platform_comment_id,
            'author_id': self.author_id,
            'author_name': self.author_name,
            'comment_text': self.comment_text,
            'comment_time': self.comment_time,
            'post_context': self.post_context,
            'sentiment': self.sentiment,
            'ai_draft_reply': self.ai_draft_reply,
            'final_reply': self.final_reply,
            'status': self.status,
            'auto_replied': self.auto_replied,
            'replied_at': self.replied_at,
            'hidden_at': self.hidden_at,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    # -----------------------------------------------------------------------
    # Database Queries
    # -----------------------------------------------------------------------

    @classmethod
    def get_by_id(cls, item_id: int, user_id: Optional[str] = None) -> Optional['InboxItem']:
        """Fetch a single inbox item by ID, optionally scoped to a user."""
        db = get_db()
        if user_id:
            row = db.execute(
                'SELECT * FROM inbox_items WHERE id = ? AND user_id = ?',
                (item_id, str(user_id))
            ).fetchone()
        else:
            row = db.execute(
                'SELECT * FROM inbox_items WHERE id = ?',
                (item_id,)
            ).fetchone()
        return cls(dict(row)) if row else None

    @classmethod
    def get_by_comment_id(cls, platform: str, platform_comment_id: str, user_id: Optional[str] = None) -> Optional['InboxItem']:
        """Fetch by unique platform + comment ID."""
        db = get_db()
        if user_id:
            row = db.execute(
                'SELECT * FROM inbox_items WHERE platform = ? AND platform_comment_id = ? AND user_id = ?',
                (platform, str(platform_comment_id), str(user_id))
            ).fetchone()
        else:
            row = db.execute(
                'SELECT * FROM inbox_items WHERE platform = ? AND platform_comment_id = ?',
                (platform, str(platform_comment_id))
            ).fetchone()
        return cls(dict(row)) if row else None

    @classmethod
    def list_by_user(
        cls,
        user_id: str,
        status: Optional[str] = None,
        sentiment: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List['InboxItem']:
        """Query paginated inbox items with optional status, sentiment, and platform filters."""
        db = get_db()
        query = 'SELECT * FROM inbox_items WHERE user_id = ?'
        params: List[Any] = [str(user_id)]

        if status:
            if status == 'replied':
                query += ' AND status IN (?, ?)'
                params.extend([cls.STATUS_APPROVED, cls.STATUS_AUTO_REPLIED])
            else:
                query += ' AND status = ?'
                params.append(status)

        if sentiment:
            query += ' AND sentiment = ?'
            params.append(sentiment)

        if platform:
            query += ' AND platform = ?'
            params.append(platform)

        query += ' ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?'
        params.extend([max(1, int(limit)), max(0, int(offset))])

        rows = db.execute(query, tuple(params)).fetchall()
        return [cls(dict(r)) for r in rows]

    @classmethod
    def count_by_user(
        cls,
        user_id: str,
        status: Optional[str] = None,
        sentiment: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> int:
        """Count inbox items matching criteria."""
        db = get_db()
        query = 'SELECT COUNT(*) as count FROM inbox_items WHERE user_id = ?'
        params: List[Any] = [str(user_id)]

        if status:
            if status == 'replied':
                query += ' AND status IN (?, ?)'
                params.extend([cls.STATUS_APPROVED, cls.STATUS_AUTO_REPLIED])
            else:
                query += ' AND status = ?'
                params.append(status)

        if sentiment:
            query += ' AND sentiment = ?'
            params.append(sentiment)

        if platform:
            query += ' AND platform = ?'
            params.append(platform)

        row = db.execute(query, tuple(params)).fetchone()
        if not row:
            return 0
        if isinstance(row, dict):
            return int(row.get('count', 0))
        return int(row[0])

    @classmethod
    def create(
        cls,
        user_id: str,
        platform: str,
        platform_comment_id: str,
        comment_text: str,
        platform_post_id: Optional[str] = None,
        author_id: Optional[str] = None,
        author_name: Optional[str] = None,
        comment_time: Optional[str] = None,
        post_context: Optional[str] = None,
        sentiment: str = 'neutral',
        ai_draft_reply: Optional[str] = None,
        final_reply: Optional[str] = None,
        status: str = 'pending',
        auto_replied: bool = False,
    ) -> 'InboxItem':
        """Insert a new inbox item, ignoring duplicates on (platform, platform_comment_id)."""
        existing = cls.get_by_comment_id(platform, platform_comment_id)
        if existing:
            return existing

        now_ts = int(time.time())
        db = get_db()
        sql = """
            INSERT INTO inbox_items (
                user_id, platform, platform_post_id, platform_comment_id,
                author_id, author_name, comment_text, comment_time, post_context,
                sentiment, ai_draft_reply, final_reply, status, auto_replied,
                replied_at, hidden_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        replied_at = now_ts if status in (cls.STATUS_APPROVED, cls.STATUS_AUTO_REPLIED) else None
        hidden_at = now_ts if status == cls.STATUS_HIDDEN else None

        db.execute(sql, (
            str(user_id),
            platform,
            platform_post_id,
            str(platform_comment_id),
            author_id,
            author_name,
            comment_text,
            comment_time,
            post_context,
            sentiment,
            ai_draft_reply,
            final_reply,
            status,
            1 if auto_replied else 0,
            replied_at,
            hidden_at,
            now_ts,
            now_ts,
        ))
        db.commit()

        created = cls.get_by_comment_id(platform, platform_comment_id)
        if not created:
            raise RuntimeError(f"Failed to create inbox item for comment {platform_comment_id}")
        return created

    @classmethod
    def update_draft(cls, item_id: int, user_id: str, new_draft: str) -> bool:
        """Update the AI draft reply for an item."""
        now_ts = int(time.time())
        db = get_db()
        db.execute(
            'UPDATE inbox_items SET ai_draft_reply = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (new_draft, now_ts, item_id, str(user_id))
        )
        db.commit()
        return True

    @classmethod
    def mark_replied(
        cls,
        item_id: int,
        user_id: str,
        final_reply: str,
        auto_replied: bool = False,
    ) -> bool:
        """Mark item as replied (approved / auto_replied)."""
        now_ts = int(time.time())
        new_status = cls.STATUS_AUTO_REPLIED if auto_replied else cls.STATUS_APPROVED
        db = get_db()
        db.execute(
            'UPDATE inbox_items SET status = ?, final_reply = ?, auto_replied = ?, replied_at = ?, updated_at = ? '
            'WHERE id = ? AND user_id = ?',
            (new_status, final_reply, 1 if auto_replied else 0, now_ts, now_ts, item_id, str(user_id))
        )
        db.commit()
        return True

    @classmethod
    def mark_hidden(cls, item_id: int, user_id: str) -> bool:
        """Mark item as hidden."""
        now_ts = int(time.time())
        db = get_db()
        db.execute(
            'UPDATE inbox_items SET status = ?, hidden_at = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (cls.STATUS_HIDDEN, now_ts, now_ts, item_id, str(user_id))
        )
        db.commit()
        return True

    @classmethod
    def mark_skipped(cls, item_id: int, user_id: str) -> bool:
        """Mark item as skipped / archived."""
        now_ts = int(time.time())
        db = get_db()
        db.execute(
            'UPDATE inbox_items SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            (cls.STATUS_SKIPPED, now_ts, item_id, str(user_id))
        )
        db.commit()
        return True
