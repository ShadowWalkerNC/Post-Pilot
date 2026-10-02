"""
mcp/tools/automation.py — automation.run + automation.status.

automation.run delegates to modules.automation_agent per-user processing
(same code path as the hourly Vercel Cron job, scoped to one user).
automation.status reads the automation_log audit table ([] when the table
does not exist yet on older schemas).
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SPEC_AUTOMATION_RUN = {
    'name': 'automation.run',
    'description': 'Run the content automation agent now for one user (queues due posts).',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; '
            'generates captions (consumes plan AI quota) and queues post_history rows.',
    'inputs': {'user_id': 'Post-Pilot user ID (required)'},
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_AUTOMATION_STATUS = {
    'name': 'automation.status',
    'description': 'Recent automation_log audit rows for a user, newest first.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'limit': 'Max rows (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def automation_run(user_id: str) -> dict:
    """Process one user through the automation agent. Returns {success, queued}."""
    from modules.db import get_connection
    from modules.user_manager import UserManager
    from modules.automation_agent import _process_user
    if not user_id:
        raise ValueError('user_id is required')
    profile = UserManager.get_business_profile(user_id) or {}
    if not (profile.get('name') or '').strip():
        return {'success': False, 'error': 'No business profile for this user'}
    agent_profile = {
        'user_id': str(user_id),
        'name': profile.get('name'),
        'business_type': profile.get('business_type'),
        'location': profile.get('location'),
        'hours': profile.get('hours'),
        'ai_tone': profile.get('ai_tone'),
    }
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    conn = get_connection()
    try:
        queued = _process_user(conn, agent_profile, today)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {'success': True, 'queued': int(queued or 0)}


def automation_status(user_id: str, limit: int = 25) -> list:
    """Return automation_log rows for user_id, newest first ([] if table missing)."""
    from modules.db import execute_all
    if not user_id:
        raise ValueError('user_id is required')
    limit = max(1, min(int(limit or 25), 100))
    try:
        return execute_all(
            'SELECT * FROM automation_log WHERE user_id = ? '
            'ORDER BY created_at DESC LIMIT ?',
            (user_id, limit),
        )
    except Exception as exc:
        logger.warning('automation_status(%s) falling back to empty: %s', user_id, exc)
        return []
