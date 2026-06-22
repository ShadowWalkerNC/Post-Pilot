"""
modules/scheduler_worker.py
APScheduler background job runner for Post-Pilot.

Polls post_history for rows with status='scheduled' and scheduled_at <= now(),
then publishes them via UniversalPublisher and marks them published or failed.

Started automatically when app.py is imported (via init_scheduler()).
Safe to call multiple times -- idempotent guard prevents double-start.

Dependency: APScheduler>=3.10.4 (in requirements.txt)

Design notes:
  - _get_tokens() is imported from blueprints.utils -- single source of truth.
  - PostScheduler (the per-request helper for scheduling a single post via the
    Meta API) lives here too so modules/scheduler.py and modules/post_scheduler.py
    can be thin shims that re-export it without breaking old import sites.
"""

import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from modules.db import get_connection, placeholder

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning('APScheduler not installed -- scheduled posts will not auto-publish.')

_scheduler = None


# ---------------------------------------------------------------------------
# Optimal post times (previously duplicated in scheduler.py / post_scheduler.py)
# ---------------------------------------------------------------------------

OPTIMAL_TIMES: Dict[str, Dict[str, int]] = {
    'instagram_location':   {'hour': 8,  'minute': 0},
    'instagram_menu':       {'hour': 11, 'minute': 0},
    'instagram_engagement': {'hour': 17, 'minute': 0},
    'instagram_team':       {'hour': 8,  'minute': 0},
    'facebook_giveaway':    {'hour': 11, 'minute': 0},
}

DAY_MAP: Dict[str, int] = {
    'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
    'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6,
}


# ---------------------------------------------------------------------------
# Token helper -- delegates to blueprints.utils (single source of truth)
# ---------------------------------------------------------------------------

def _get_tokens_for_user(uid: str) -> dict:
    """
    Load all OAuth tokens for uid from the DB.
    Delegates to blueprints.utils._get_tokens so there is one implementation.
    """
    # Imported here to avoid a circular import at module load time
    # (blueprints.utils -> modules.auth_manager; no cycle through app.py)
    from blueprints.utils import _get_tokens
    return _get_tokens(uid)


# ---------------------------------------------------------------------------
# PostScheduler -- per-request helper for scheduling a single post via Meta API
# (kept here so scheduler.py / post_scheduler.py shims stay thin)
# ---------------------------------------------------------------------------

class PostScheduler:
    """
    Thin helper that schedules a single post through the Meta (FB/IG) API
    and supports bulk-scheduling a week of content at optimal times.

    For the background DB-poll runner that auto-publishes due posts, see
    init_scheduler() / _publish_scheduled_posts() below.
    """

    def __init__(self):
        # Each instance starts its own BackgroundScheduler only if APScheduler
        # is available; callers that only use schedule() / bulk_schedule_week()
        # don't strictly need it, but we keep the interface consistent.
        if APSCHEDULER_AVAILABLE:
            self._sched = BackgroundScheduler(daemon=True)
            self._sched.start()
        else:
            self._sched = None

    # ------------------------------------------------------------------
    # Single-post schedule
    # ------------------------------------------------------------------

    def schedule(self, data: Dict) -> Dict:
        """Schedule one post via the Meta API (Facebook or Instagram)."""
        try:
            from modules.meta_client import MetaAPI
        except ImportError:
            try:
                from modules.meta_api import MetaAPI  # legacy fallback
            except ImportError:
                return {'success': False, 'error': 'MetaAPI module not found'}

        try:
            publish_dt = datetime.fromisoformat(data.get('publish_time'))
            api = MetaAPI(
                access_token = data.get('access_token'),
                page_id      = data.get('page_id'),
                instagram_id = data.get('instagram_id'),
            )
            platform  = data.get('platform', 'instagram')
            caption   = data.get('caption', '')
            image_url = data.get('image_url')

            if platform == 'facebook':
                result = api.schedule_facebook_post(caption, publish_dt, image_url)
            else:
                result = api.schedule_instagram_post(caption, image_url, publish_dt)

            return {'success': True, 'scheduled_for': publish_dt.isoformat(), 'result': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Bulk weekly schedule
    # ------------------------------------------------------------------

    def bulk_schedule_week(
        self,
        posts:      List[Dict],
        tokens:     Dict,
        start_date: datetime = None,
    ) -> List[Dict]:
        """Schedule a full week of posts starting from start_date (defaults to next Monday)."""
        if start_date is None:
            today = datetime.now()
            days_until_monday = (7 - today.weekday()) % 7 or 7
            start_date = (today + timedelta(days=days_until_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        weekly_plan = [
            ('instagram_location',   'Monday'),
            ('instagram_menu',       'Tuesday'),
            ('instagram_engagement', 'Wednesday'),
            ('instagram_team',       'Thursday'),
            ('facebook_giveaway',    'Friday'),
            ('instagram_location',   'Saturday'),
            ('instagram_engagement', 'Sunday'),
        ]

        results = []
        for post, (template, day_name) in zip(posts, weekly_plan):
            opt        = OPTIMAL_TIMES[template]
            publish_dt = (start_date + timedelta(days=DAY_MAP[day_name])).replace(
                hour=opt['hour'], minute=opt['minute']
            )
            results.append(self.schedule({
                **tokens,
                'caption':      post.get('caption'),
                'image_url':    post.get('image_url'),
                'platform':     post.get('platform', 'instagram'),
                'publish_time': publish_dt.isoformat(),
            }))
        return results

    # ------------------------------------------------------------------
    # Job inspection helpers
    # ------------------------------------------------------------------

    def get_jobs(self) -> List[Dict]:
        if not self._sched:
            return []
        return [{'id': j.id, 'next_run': str(j.next_run_time)} for j in self._sched.get_jobs()]

    # Legacy alias used in old tests / blueprints
    def get_scheduled_jobs(self) -> List[Dict]:
        return self.get_jobs()

    def cancel_job(self, job_id: str) -> Dict:
        if not self._sched:
            return {'success': False, 'error': 'Scheduler not running'}
        try:
            self._sched.remove_job(job_id)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Background DB-poll runner
# ---------------------------------------------------------------------------

def _publish_scheduled_posts():
    """Core background job: find due scheduled posts and publish them."""
    from modules.publisher import UniversalPublisher  # avoid circular import at module level

    now_ts = int(time.time())
    p      = placeholder
    conn   = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT id, user_id, caption, content_type, image_url, video_url, platforms '
            f'FROM post_history '
            f'WHERE status = {p} AND scheduled_at <= {p} AND scheduled_at IS NOT NULL',
            ('scheduled', now_ts)
        )
        rows = cur.fetchall()
    except Exception as e:
        logger.error('scheduler_worker: DB query failed: %s', e)
        conn.close()
        return

    for row in rows:
        # Support both sqlite3.Row and psycopg2 RealDictRow
        if isinstance(row, dict):
            post_id, user_id       = row['id'],           row['user_id']
            caption, content_type  = row['caption'],      row['content_type']
            image_url, video_url   = row['image_url'],    row['video_url']
            platforms              = row['platforms']
        else:
            post_id, user_id, caption, content_type, image_url, video_url, platforms = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6]
            )

        try:
            platform_list = json.loads(platforms or '[]')
            tokens        = _get_tokens_for_user(user_id)
            publisher     = UniversalPublisher(tokens, user_id=user_id)
            results       = publisher.push_all(
                caption      = caption or '',
                content_type = content_type or 'text',
                image_url    = image_url,
                video_url    = video_url,
                platforms    = platform_list,
            )
            any_ok     = any(
                (v.get('success') if isinstance(v, dict) else True)
                for v in (results.values() if isinstance(results, dict) else [])
            )
            new_status = 'published' if any_ok else 'failed'
            cur.execute(
                f'UPDATE post_history SET status={p}, results={p} WHERE id={p}',
                (new_status, json.dumps(results), post_id)
            )
            conn.commit()
            logger.info('scheduler_worker: post %s -> %s', post_id, new_status)
        except Exception as e:
            logger.error('scheduler_worker: failed to publish post %s: %s', post_id, e)
            try:
                cur.execute(f'UPDATE post_history SET status={p} WHERE id={p}', ('failed', post_id))
                conn.commit()
            except Exception:
                pass

    conn.close()


def init_scheduler():
    """Start the APScheduler background job. Safe to call multiple times."""
    global _scheduler
    if not APSCHEDULER_AVAILABLE:
        logger.warning('APScheduler not available -- skipping scheduler init.')
        return
    if _scheduler is not None and _scheduler.running:
        return
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _publish_scheduled_posts,
        trigger  = IntervalTrigger(minutes=1),
        id       = 'publish_scheduled',
        replace_existing   = True,
        misfire_grace_time = 60,
    )
    _scheduler.start()
    logger.info('scheduler_worker: APScheduler started (1-min poll interval)')


def shutdown_scheduler():
    """Gracefully stop the scheduler on app teardown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info('scheduler_worker: APScheduler stopped')
