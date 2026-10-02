"""
mcp/tools/hours.py — hours.get (read-only).

Delegates to: hours_overrides table via modules.db (same source as blueprints/hours.py).
"""

from typing import Optional

SPEC_HOURS_GET = {
    'name': 'hours.get',
    'description': 'List hours overrides / closure announcements for a user, upcoming first.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'status': 'Optional filter: pending | posted | failed',
        'limit': 'Max rows (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

VALID_STATUSES = {'pending', 'posted', 'failed'}


def hours_get(user_id: str, status: Optional[str] = None, limit: int = 25) -> list:
    """Return hours_overrides rows for user_id, upcoming first."""
    from modules.db import execute_all
    if not user_id:
        raise ValueError('user_id is required')
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f'status must be one of {sorted(VALID_STATUSES)}')
    limit = max(1, min(int(limit or 25), 100))
    if status:
        return execute_all(
            'SELECT * FROM hours_overrides WHERE user_id = ? AND status = ? '
            'ORDER BY post_date ASC, post_time ASC LIMIT ?',
            (user_id, status, limit),
        )
    return execute_all(
        'SELECT * FROM hours_overrides WHERE user_id = ? '
        'ORDER BY post_date ASC, post_time ASC LIMIT ?',
        (user_id, limit),
    )
