"""
mcp/tools/events.py — events.list (read-only).

Delegates to: events table via modules.db (same source as blueprints/events.py).
"""

from typing import Optional

SPEC_EVENTS_LIST = {
    'name': 'events.list',
    'description': 'List events for a user, optionally filtered by status.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'status': 'Optional filter: pending | posted | failed',
        'limit': 'Max rows (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_EVENTS_GET = {
    'name': 'events.get',
    'description': 'Get one event by id ({} when not found or owned by another user).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'event_id': 'Event row id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

VALID_STATUSES = {'pending', 'posted', 'failed'}


def events_get(user_id: str, event_id: int) -> dict:
    """Return one event row for user_id ({} when missing)."""
    from modules.db import execute_one
    if not user_id:
        raise ValueError('user_id is required')
    if event_id is None:
        raise ValueError('event_id is required')
    return execute_one(
        'SELECT * FROM events WHERE id = ? AND user_id = ?',
        (event_id, user_id),
    ) or {}


def events_list(user_id: str, status: Optional[str] = None, limit: int = 25) -> list:
    """Return event rows for user_id, newest first."""
    from modules.db import execute_all
    if not user_id:
        raise ValueError('user_id is required')
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f'status must be one of {sorted(VALID_STATUSES)}')
    limit = max(1, min(int(limit or 25), 100))
    if status:
        return execute_all(
            'SELECT * FROM events WHERE user_id = ? AND status = ? '
            'ORDER BY event_date DESC LIMIT ?',
            (user_id, status, limit),
        )
    return execute_all(
        'SELECT * FROM events WHERE user_id = ? ORDER BY event_date DESC LIMIT ?',
        (user_id, limit),
    )
