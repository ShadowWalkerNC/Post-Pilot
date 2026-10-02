"""
mcp/tools/publish.py — post.publish (publishes to live social platforms).

Delegates to: modules.publisher.UniversalPublisher.
"""

from typing import Dict, Optional

SPEC_POST_PUBLISH = {
    'name': 'post.publish',
    'description': 'Publish a caption now to the user connected platforms (or a subset).',
    'permission': 'publish',
    'auth': 'Caller must be the account owner or a team member with publish rights. '
            'Publishes ONLY to platforms connected by user_id. Plan limits enforced by plan_guard at the API layer; '
            'MCP callers must confirm quota before invoking.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'caption': 'Post text, or per-platform {key: text} via captions',
        'captions': 'Optional per-platform caption map (Option B)',
        'content_type': 'Routing hint (default general)',
        'platforms': 'Optional platform list or {key: bool} map',
        'image_url': 'Optional image URL (required for Instagram)',
        'video_url': 'Optional video URL',
        'link_url': 'Optional link URL',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def post_publish(
    user_id: str,
    caption: Optional[str] = None,
    captions: Optional[Dict] = None,
    content_type: str = 'general',
    platforms=None,
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
    link_url: Optional[str] = None,
) -> dict:
    """Publish immediately via UniversalPublisher. Returns per-platform results."""
    from modules.publisher import UniversalPublisher
    from modules.db import execute_all
    from modules.auth_manager import _decrypt
    if not user_id:
        raise ValueError('user_id is required')
    if not caption and not captions:
        raise ValueError('caption or captions is required')
    tokens = _load_decrypted_tokens(user_id)
    publisher = UniversalPublisher(tokens, user_id=user_id)
    return publisher.push_all(
        caption=caption,
        captions=captions,
        content_type=content_type,
        platforms=platforms,
        image_url=image_url,
        video_url=video_url,
        link_url=link_url,
    )


SPEC_POST_CANCEL = {
    'name': 'post.cancel',
    'description': 'Cancel a scheduled job by id (in-memory scheduler jobs only).',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Only cancels jobs owned by this server process; Meta-direct schedules cannot be recalled.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'job_id': 'Scheduler job id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_POST_STATUS = {
    'name': 'post.status',
    'description': 'Check whether a scheduled job id is still pending.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'job_id': 'Scheduler job id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def post_cancel(user_id: str, job_id: str) -> dict:
    """Cancel a scheduled job. Returns the PostScheduler result dict."""
    from modules.scheduler_worker import PostScheduler
    if not user_id:
        raise ValueError('user_id is required')
    if not job_id:
        raise ValueError('job_id is required')
    return PostScheduler().cancel_job(job_id)


def post_status(user_id: str, job_id: str) -> dict:
    """Return {found, status, next_run} for a job id ('unknown' when absent)."""
    from modules.scheduler_worker import PostScheduler
    if not user_id:
        raise ValueError('user_id is required')
    if not job_id:
        raise ValueError('job_id is required')
    for job in PostScheduler().get_jobs():
        if str(job.get('id')) == str(job_id):
            return {'found': True, 'status': 'scheduled', 'next_run': job.get('next_run')}
    return {'found': False, 'status': 'unknown', 'next_run': None}


def _load_decrypted_tokens(user_id: str) -> dict:
    """Build the UniversalPublisher tokens dict from platform_tokens rows."""
    from modules.db import execute_all
    from modules.auth_manager import _decrypt
    import json
    tokens: dict = {}
    rows = execute_all(
        'SELECT platform, access_token, token_meta FROM platform_tokens WHERE user_id = ?',
        (user_id,),
    )
    for row in rows:
        platform = (row.get('platform') or '').lower()
        try:
            access = _decrypt(row.get('access_token') or '')
        except Exception:
            continue
        meta = {}
        try:
            meta = json.loads(row.get('token_meta') or '{}')
        except (ValueError, TypeError):
            pass
        tokens[f'{platform}_token'] = access
        for key, value in meta.items():
            tokens.setdefault(f'{platform}_{key}', value)
            tokens.setdefault(key, value)
    # Compatibility aliases expected by UniversalPublisher
    alias = {
        'facebook_page_id': ('facebook_page_id', 'page_id'),
        'instagram_id': ('instagram_id', 'ig_id'),
        'google_location_id': ('google_location_id', 'location_id'),
    }
    for canon, keys in alias.items():
        if canon not in tokens:
            for key in keys:
                if key in tokens:
                    tokens[canon] = tokens[key]
                    break
    return tokens
