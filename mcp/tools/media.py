"""
mcp/tools/media.py — media.list + media.get (read-only).

Delegates to: post_history rows via modules.db (image_url/video_url attached
to published or scheduled posts). There is no standalone media library table;
media is whatever was attached to posts.
"""

SPEC_MEDIA_LIST = {
    'name': 'media.list',
    'description': 'List media attachments (image/video URLs) from a user post history.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'limit': 'Max rows (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_MEDIA_GET = {
    'name': 'media.get',
    'description': 'Get one post_history media row by id ({} when not found).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'media_id': 'post_history row id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

_MEDIA_COLUMNS = 'id, caption, image_url, video_url, platforms, status, created_at'


def media_list(user_id: str, limit: int = 25) -> list:
    """Return post_history rows with media for user_id, newest first."""
    from modules.db import execute_all
    if not user_id:
        raise ValueError('user_id is required')
    limit = max(1, min(int(limit or 25), 100))
    return execute_all(
        f'SELECT {_MEDIA_COLUMNS} FROM post_history WHERE user_id = ? '
        'AND (image_url IS NOT NULL AND image_url != \'\' '
        'OR video_url IS NOT NULL AND video_url != \'\') '
        'ORDER BY created_at DESC LIMIT ?',
        (user_id, limit),
    )


def media_get(user_id: str, media_id: int) -> dict:
    """Return one post_history row for user_id ({} when missing)."""
    from modules.db import execute_one
    if not user_id:
        raise ValueError('user_id is required')
    if media_id is None:
        raise ValueError('media_id is required')
    return execute_one(
        f'SELECT {_MEDIA_COLUMNS} FROM post_history WHERE id = ? AND user_id = ?',
        (media_id, user_id),
    ) or {}
