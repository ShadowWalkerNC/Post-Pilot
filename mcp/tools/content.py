"""
mcp/tools/content.py — content.generate + content.schedule + content.adapt + content.preview.

Delegates to: modules.ai_generator (generate), modules.scheduler_worker (schedule),
modules.platform_adapter.PlatformAdapter (adapt/preview).
"""

from typing import Dict, List, Optional

SPEC_CONTENT_GENERATE = {
    'name': 'content.generate',
    'description': 'Generate a master caption plus per-platform adaptations for a user.',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Consumes the plan AI-caption quota (plan_guard).',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required, quota attribution)',
        'content_type': 'daily_special | location | general (default general)',
        'tone': 'hype | friendly | urgent | funny | community (default friendly)',
        'keywords': 'Optional list of words to weave in',
        'platforms': 'Optional list of short platform keys (fb, ig, tt, yt, gb, web, tw, yts)',
        'special': 'Optional special text merged into business context',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_CONTENT_SCHEDULE = {
    'name': 'content.schedule',
    'description': 'Schedule a post for future publishing via the PostScheduler.',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; jobs publish only to that user connected platforms.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'caption': 'Post text (required)',
        'scheduled_at': 'ISO datetime string (required)',
        'platforms': 'Optional platform list or {key: bool} map',
        'content_type': 'Content type for routing (default general)',
        'image_url': 'Optional image URL',
        'video_url': 'Optional video URL',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def content_generate(
    user_id: str,
    content_type: str = 'general',
    tone: str = 'friendly',
    keywords: Optional[list] = None,
    platforms: Optional[list] = None,
    special: str = '',
) -> dict:
    """Generate master + adapted captions using the user's business profile."""
    from modules.ai_generator import generate_with_adaptations
    from modules.user_manager import UserManager
    if not user_id:
        raise ValueError('user_id is required')
    profile = UserManager.get_business_profile(user_id) or {}
    business_info = {
        'name': profile.get('name', 'Our Business'),
        'type': profile.get('business_type', 'food business'),
        'location': profile.get('location', ''),
        'hours': profile.get('hours', ''),
        'special': special or '',
    }
    return generate_with_adaptations(
        business_info=business_info,
        content_type=content_type,
        tone=tone,
        keywords=keywords or [],
        platforms=platforms,
    )


def content_schedule(
    user_id: str,
    caption: str,
    scheduled_at: str,
    platforms=None,
    content_type: str = 'general',
    image_url: Optional[str] = None,
    video_url: Optional[str] = None,
) -> dict:
    """Schedule a post via PostScheduler. Returns the scheduler result dict."""
    from modules.scheduler_worker import PostScheduler
    from mcp.tools.publish import _load_decrypted_tokens
    if not user_id:
        raise ValueError('user_id is required')
    if not caption:
        raise ValueError('caption is required')
    if not scheduled_at:
        raise ValueError('scheduled_at is required')
    tokens = _load_decrypted_tokens(user_id)
    fb_token = tokens.get('facebook_token', '')
    if not fb_token:
        return {'success': False, 'error': 'Facebook not connected for this user'}
    platform = _first_platform(platforms)
    scheduler = PostScheduler()
    return scheduler.schedule({
        'access_token': fb_token,
        'page_id': tokens.get('facebook_page_id', ''),
        'instagram_id': tokens.get('instagram_id', ''),
        'platform': platform,
        'caption': caption,
        'image_url': image_url,
        'publish_time': scheduled_at,
    })


SPEC_CONTENT_ADAPT = {
    'name': 'content.adapt',
    'description': 'Adapt a master caption for specific platforms (same adapter as the dashboard).',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Consumes the plan AI-caption quota (plan_guard).',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required, quota attribution)',
        'master': 'Master caption text (required)',
        'platforms': 'Non-empty list of short platform keys: fb, ig, tt, yt, gb, web, tw, yts',
        'tone': 'hype | friendly | urgent | funny | community (default friendly)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_CONTENT_PREVIEW = {
    'name': 'content.preview',
    'description': 'Preview adapted captions with char counts and media warnings (no writes).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Read-only render of content.adapt output.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'master': 'Master caption text (required)',
        'platforms': 'Non-empty list of short platform keys',
        'tone': 'hype | friendly | urgent | funny | community (default friendly)',
        'image_url': 'Optional image URL (silences the Instagram media warning)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

#: Platforms that require an image for publishing.
IMAGE_REQUIRED = {'ig', 'instagram'}


def content_adapt(
    user_id: str,
    master: str,
    platforms: List[str],
    tone: str = 'friendly',
) -> dict:
    """Adapt master for platforms via PlatformAdapter. Returns {master, adapted}."""
    from modules.platform_adapter import PlatformAdapter
    from modules.user_manager import UserManager
    if not user_id:
        raise ValueError('user_id is required')
    if not master or not str(master).strip():
        raise ValueError('master is required')
    if not platforms:
        raise ValueError('platforms must be a non-empty list')
    profile = UserManager.get_business_profile(user_id) or {}
    business = {
        'name': profile.get('name', 'Our Business'),
        'type': profile.get('business_type', 'food business'),
        'location': profile.get('location', ''),
        'city': profile.get('location', ''),
    }
    adapted = PlatformAdapter().adapt_all(str(master), list(platforms), tone=tone, business=business)
    return {'master': str(master), 'adapted': adapted}


def content_preview(
    user_id: str,
    master: str,
    platforms: List[str],
    tone: str = 'friendly',
    image_url: Optional[str] = None,
) -> dict:
    """Adapt + annotate each platform with char counts and media warnings."""
    result = content_adapt(user_id, master, platforms, tone)
    previews = {}
    for platform, text in result['adapted'].items():
        warnings = []
        if platform.lower() in IMAGE_REQUIRED and not image_url:
            warnings.append('instagram publishing requires image_url')
        previews[platform] = {'text': text, 'chars': len(text or ''), 'warnings': warnings}
    return {'master': result['master'], 'previews': previews}


def _first_platform(platforms) -> str:
    """Pick 'facebook' or 'instagram' from a list/map; default instagram."""
    if isinstance(platforms, dict):
        keys = [k for k, v in platforms.items() if v]
    elif isinstance(platforms, (list, tuple)):
        keys = list(platforms)
    else:
        return 'instagram'
    norm = {'fb': 'facebook', 'facebook': 'facebook',
            'ig': 'instagram', 'instagram': 'instagram'}
    for key in keys:
        mapped = norm.get(str(key).lower())
        if mapped:
            return mapped
    return 'instagram'
