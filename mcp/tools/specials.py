"""
mcp/tools/specials.py — specials.list (read-only).

Delegates to: specials table via modules.db (same source as blueprints/specials.py).
"""

from typing import Optional

SPEC_SPECIALS_LIST = {
    'name': 'specials.list',
    'description': 'List daily specials for a user, optionally filtered by status.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'status': 'Optional filter: pending | posted | failed',
        'limit': 'Max rows (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_SPECIALS_GET = {
    'name': 'specials.get',
    'description': 'Get one special by id ({} when not found or owned by another user).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'special_id': 'Special row id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

VALID_STATUSES = {'pending', 'posted', 'failed'}


def specials_get(user_id: str, special_id: int) -> dict:
    """Return one special row for user_id ({} when missing)."""
    from modules.db import execute_one
    if not user_id:
        raise ValueError('user_id is required')
    if special_id is None:
        raise ValueError('special_id is required')
    return execute_one(
        'SELECT * FROM specials WHERE id = ? AND user_id = ?',
        (special_id, user_id),
    ) or {}


def specials_list(user_id: str, status: Optional[str] = None, limit: int = 25) -> list:
    """Return specials rows for user_id, newest first."""
    from modules.db import execute_all
    if not user_id:
        raise ValueError('user_id is required')
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f'status must be one of {sorted(VALID_STATUSES)}')
    limit = max(1, min(int(limit or 25), 100))
    if status:
        return execute_all(
            'SELECT * FROM specials WHERE user_id = ? AND status = ? '
            'ORDER BY post_date DESC, post_time DESC LIMIT ?',
            (user_id, status, limit),
        )
    return execute_all(
        'SELECT * FROM specials WHERE user_id = ? '
        'ORDER BY post_date DESC, post_time DESC LIMIT ?',
        (user_id, limit),
    )
