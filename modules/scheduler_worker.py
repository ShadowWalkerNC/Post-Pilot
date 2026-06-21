"""
scheduler_worker.py -- APScheduler background job runner for Post-Pilot.

Polls post_history for rows with status='scheduled' and scheduled_at <= now(),
then publishes them via UniversalPublisher and marks them published or failed.

Started automatically when app.py is imported (via init_scheduler()).
Safe to call multiple times -- idempotent guard prevents double-start.

Dependency: APScheduler>=3.10.4 (in requirements.txt)
"""

import json
import time
import logging
from modules.db import get_connection, placeholder
from modules.auth_manager import load_token

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning('APScheduler not installed -- scheduled posts will not auto-publish.')

_scheduler = None


def _get_tokens_for_user(uid: str) -> dict:
    """Rebuild the tokens dict from DB for a given user (mirrors app.py _get_tokens)."""
    tokens = {}
    platform_map = {
        'facebook': ['facebook_token', 'facebook_page_id'],
        'google':   ['google_token',   'google_location_id'],
        'tiktok':   ['tiktok_token'],
        'youtube':  ['youtube_token'],
    }
    for platform, keys in platform_map.items():
        rec = load_token(platform, uid)
        if rec:
            tokens[keys[0]] = rec['access_token']
            if len(keys) > 1 and rec.get('meta'):
                if platform == 'facebook':
                    tokens['facebook_page_id'] = rec['meta'].get('page_id', '')
                    tokens['instagram_token']  = rec['access_token']
                    tokens['instagram_id']     = rec['meta'].get('ig_id', '')
                elif platform == 'google':
                    tokens['google_location_id'] = rec['meta'].get('location_id', '')
                    tokens['youtube_token']       = rec['access_token']
    return tokens


def _publish_scheduled_posts():
    """Core job: find due scheduled posts and publish them."""
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
            post_id      = row['id']
            user_id      = row['user_id']
            caption      = row['caption']
            content_type = row['content_type']
            image_url    = row['image_url']
            video_url    = row['video_url']
            platforms    = row['platforms']
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
        trigger=IntervalTrigger(minutes=1),
        id='publish_scheduled',
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.start()
    logger.info('scheduler_worker: APScheduler started (1-min poll interval)')


def shutdown_scheduler():
    """Gracefully stop the scheduler on app teardown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info('scheduler_worker: APScheduler stopped')
