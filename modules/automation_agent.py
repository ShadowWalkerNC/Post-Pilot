"""
modules/automation_agent.py
Post-Pilot Autonomous Content Agent

This module is the brain of Post-Pilot's autonomous publishing loop.
It runs on a schedule (via Vercel Cron -> POST /api/cron/generate) and:

  1. Loads each active user's business_profile from the DB.
  2. Inspects post_history to avoid content repetition.
  3. Decides which content type is due (daily_special, location, general).
  4. Calls ai_generator.generate_with_adaptations() -> Claude/OpenAI.
  5. Writes a scheduled post_history row (status='scheduled').
  6. Writes an automation_log row with the full decision audit trail.

The cron job at /api/cron/publish (runs every minute) picks up the
scheduled rows and pushes them live via UniversalPublisher.

Active platforms (LinkedIn and Pinterest excluded -- not yet implemented):
    fb, ig, tt, yt, yts, tw, gb, web

Design notes:
  - One agent run per user per scheduled interval.
  - Content rotation: cycles daily_special -> location -> general -> repeat.
  - Minimum gap between posts: 4 hours (configurable via MIN_POST_GAP_HOURS).
  - All decisions are logged to automation_log for auditability.
  - Agent is stateless -- all state is read from the DB on each run.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from modules.db import get_connection, placeholder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Platforms the agent will generate content for.
# LinkedIn and Pinterest are excluded until their publishers are implemented.
ACTIVE_PLATFORMS: List[str] = ['fb', 'ig', 'tt', 'yt', 'yts', 'tw', 'gb', 'web']

# Content type rotation order
CONTENT_ROTATION: List[str] = ['daily_special', 'location', 'general']

# Minimum hours between autonomous posts per user
MIN_POST_GAP_HOURS: int = 4

# Optimal post times per content type (24h UTC)
OPTIMAL_SCHEDULE: Dict[str, Dict[str, int]] = {
    'daily_special': {'hour': 11, 'minute': 0},   # 11 AM -- lunch decision window
    'location':      {'hour': 8,  'minute': 0},   # 8 AM  -- morning commute
    'general':       {'hour': 17, 'minute': 0},   # 5 PM  -- evening engagement peak
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_for_all_users() -> Dict:
    """
    Entry point called by POST /api/cron/generate.
    Iterates all users with complete business profiles and runs the agent.

    Returns a summary dict for the cron endpoint to log/return.
    """
    conn = get_connection()
    summary = {'processed': 0, 'scheduled': 0, 'skipped': 0, 'errors': 0}

    try:
        cur = conn.cursor()
        # Only users who have completed onboarding (name is set)
        cur.execute(
            "SELECT user_id, name, business_type, location, hours, "
            "ai_tone, ai_keywords, timezone "
            "FROM business_profiles "
            "WHERE name IS NOT NULL AND name != ''"
        )
        rows = cur.fetchall()
    except Exception as e:
        logger.error('automation_agent: failed to load business profiles: %s', e)
        conn.close()
        return {**summary, 'error': str(e)}

    for row in rows:
        profile = _row_to_dict(row, [
            'user_id', 'name', 'business_type', 'location',
            'hours', 'ai_tone', 'ai_keywords', 'timezone',
        ])
        summary['processed'] += 1
        try:
            result = _run_for_user(conn, profile)
            if result == 'scheduled':
                summary['scheduled'] += 1
            else:
                summary['skipped'] += 1
        except Exception as e:
            logger.error('automation_agent: error for user %s: %s', profile.get('user_id'), e)
            summary['errors'] += 1

    conn.close()
    logger.info('automation_agent: run complete %s', summary)
    return summary


# ---------------------------------------------------------------------------
# Per-user agent logic
# ---------------------------------------------------------------------------

def _run_for_user(conn, profile: Dict) -> str:
    """
    Run the agent for a single user.
    Returns 'scheduled' if a post was queued, 'skipped' otherwise.
    """
    user_id = profile['user_id']
    p       = placeholder

    # 1. Check minimum gap -- don't post if we posted recently
    last_post_ts = _get_last_post_ts(conn, user_id)
    now_ts       = int(time.time())
    if last_post_ts and (now_ts - last_post_ts) < (MIN_POST_GAP_HOURS * 3600):
        logger.info('automation_agent: skipping user %s -- last post was < %dh ago', user_id, MIN_POST_GAP_HOURS)
        return 'skipped'

    # 2. Decide content type (rotate based on recent history)
    content_type = _decide_content_type(conn, user_id)

    # 3. Build business_info dict for ai_generator
    business_info = {
        'name':     profile.get('name', 'Our Business'),
        'type':     profile.get('business_type', 'restaurant'),
        'location': profile.get('location', ''),
        'hours':    profile.get('hours', ''),
        'special':  'Today\'s Special',   # TODO: pull from a specials table in a future phase
    }
    tone     = profile.get('ai_tone') or 'friendly'
    keywords = _parse_keywords(profile.get('ai_keywords', ''))

    # 4. Generate per-platform captions via OpenAI
    try:
        from modules.ai_generator import generate_with_adaptations
        result  = generate_with_adaptations(
            business_info = business_info,
            content_type  = content_type,
            tone          = tone,
            keywords      = keywords,
            platforms     = ACTIVE_PLATFORMS,
        )
        master   = result['master']
        captions = result['adapted']   # {platform_key: text}
    except Exception as e:
        logger.error('automation_agent: generation failed for user %s: %s', user_id, e)
        return 'skipped'

    # 5. Calculate optimal scheduled_at timestamp
    scheduled_at = _next_optimal_time(content_type)

    # 6. Write post_history row (status='scheduled')
    try:
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO post_history '
            f'(user_id, caption, content_type, platforms, status, scheduled_at, results, created_at) '
            f'VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})',
            (
                user_id,
                master,
                content_type,
                json.dumps(ACTIVE_PLATFORMS),
                'scheduled',
                scheduled_at,
                json.dumps({'captions': captions}),   # store per-platform captions in results
                now_ts,
            )
        )
        post_id = cur.lastrowid
        conn.commit()
        logger.info('automation_agent: scheduled post %s for user %s at %s', post_id, user_id, scheduled_at)
    except Exception as e:
        logger.error('automation_agent: failed to write post_history for user %s: %s', user_id, e)
        return 'skipped'

    # 7. Write automation_log audit row
    _write_log(conn, user_id, post_id, content_type, tone, keywords, master, scheduled_at)

    return 'scheduled'


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def _decide_content_type(conn, user_id: str) -> str:
    """
    Choose the next content type by rotating through CONTENT_ROTATION
    based on what was most recently posted.
    """
    p = placeholder
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT content_type FROM post_history '
            f'WHERE user_id = {p} AND status IN (\'scheduled\', \'published\') '
            f'ORDER BY created_at DESC LIMIT 5',
            (user_id,)
        )
        recent = [r[0] if not isinstance(r, dict) else r['content_type'] for r in cur.fetchall()]
    except Exception:
        recent = []

    # Find the last used content type and advance one step in the rotation
    for content_type in reversed(recent):
        if content_type in CONTENT_ROTATION:
            idx = CONTENT_ROTATION.index(content_type)
            return CONTENT_ROTATION[(idx + 1) % len(CONTENT_ROTATION)]

    return CONTENT_ROTATION[0]   # default: start with daily_special


def _get_last_post_ts(conn, user_id: str) -> Optional[int]:
    """Return Unix timestamp of the user's most recent post (any status)."""
    p = placeholder
    try:
        cur = conn.cursor()
        cur.execute(
            f'SELECT MAX(created_at) FROM post_history WHERE user_id = {p}',
            (user_id,)
        )
        row = cur.fetchone()
        val = row[0] if row else None
        return int(val) if val else None
    except Exception:
        return None


def _next_optimal_time(content_type: str) -> int:
    """
    Return Unix timestamp for the next optimal posting window
    for the given content type.
    If today's window has already passed, schedule for tomorrow.
    """
    opt  = OPTIMAL_SCHEDULE.get(content_type, {'hour': 12, 'minute': 0})
    now  = datetime.utcnow()
    target = now.replace(hour=opt['hour'], minute=opt['minute'], second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int(target.timestamp())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_keywords(raw: str) -> List[str]:
    """Parse comma-separated ai_keywords string into a list."""
    if not raw:
        return []
    return [k.strip() for k in raw.split(',') if k.strip()]


def _row_to_dict(row, keys: List[str]) -> Dict:
    """Normalise a DB row (sqlite3.Row or psycopg2 RealDictRow) to a plain dict."""
    if isinstance(row, dict):
        return dict(row)
    return dict(zip(keys, row))


def _write_log(
    conn,
    user_id:      str,
    post_id:      int,
    content_type: str,
    tone:         str,
    keywords:     List[str],
    master:       str,
    scheduled_at: int,
) -> None:
    """Write an audit row to automation_log. Failure is non-fatal."""
    p = placeholder
    try:
        cur = conn.cursor()
        cur.execute(
            f'INSERT INTO automation_log '
            f'(user_id, post_id, content_type, tone, keywords, master_caption, scheduled_at, created_at) '
            f'VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})',
            (
                user_id,
                post_id,
                content_type,
                tone,
                json.dumps(keywords),
                master,
                scheduled_at,
                int(time.time()),
            )
        )
        conn.commit()
    except Exception as e:
        logger.warning('automation_agent: failed to write automation_log: %s', e)
