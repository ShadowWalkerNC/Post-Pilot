"""
mcp/tools/inbox.py — inbox.reply (draft-only) + inbox.list + inbox.approve_reply + inbox.skip.

Delegates to: modules.reply_agent.analyze_and_draft, modules.models.InboxItem,
modules.meta_api.MetaAPI (approve path only, mirroring blueprints/inbox.py).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SPEC_INBOX_REPLY = {
    'name': 'inbox.reply',
    'description': 'Draft an on-brand reply to a comment/review. DRAFT ONLY — never posts automatically.',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Output is a draft for human review; '
            'posting requires a separate explicit post.publish call. Spam input yields an empty draft.',
    'inputs': {
        'comment_text': 'The comment/review text (required)',
        'user_id': 'Optional Post-Pilot user ID (loads business context when given)',
        'post_context': 'Optional original post text for context',
        'tone': 'friendly | hype | urgent | funny | community (default friendly)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


SPEC_INBOX_LIST = {
    'name': 'inbox.list',
    'description': 'List ingested social comments for a user with optional filters.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'status': 'Optional filter (pending, replied, skipped, hidden, ...)',
        'sentiment': 'Optional filter (positive, neutral, negative, spam, ...)',
        'platform': 'Optional filter (fb, ig, ...)',
        'limit': 'Max items (default 50, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_INBOX_APPROVE_REPLY = {
    'name': 'inbox.approve_reply',
    'description': 'Approve and POST a reply to a comment (defaults to the AI draft). PUBLISHES.',
    'permission': 'publish',
    'auth': 'Caller must be the account owner or a team member with publish rights. '
            'Posts to the live platform via Meta API, then marks the item replied. '
            'Dashboard equivalent requires a Pro plan; MCP callers must confirm quota.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'item_id': 'Inbox item id (required)',
        'reply_text': 'Reply text; defaults to the stored AI draft when omitted',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_INBOX_SKIP = {
    'name': 'inbox.skip',
    'description': 'Mark an inbox item skipped (no reply posted).',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'item_id': 'Inbox item id (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def inbox_list(
    user_id: str,
    status: Optional[str] = None,
    sentiment: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Return {items, total} for user_id via InboxItem (same source as the dashboard)."""
    from modules.models import InboxItem
    if not user_id:
        raise ValueError('user_id is required')
    limit = max(1, min(int(limit or 50), 100))
    items = InboxItem.list_by_user(
        user_id=user_id, status=status, sentiment=sentiment, platform=platform,
        limit=limit, offset=0,
    )
    total = InboxItem.count_by_user(
        user_id=user_id, status=status, sentiment=sentiment, platform=platform,
    )
    return {'items': [i.to_dict() for i in items], 'total': total}


def inbox_approve_reply(user_id: str, item_id: int, reply_text: Optional[str] = None) -> dict:
    """Post a reply to the platform and mark the item replied. Returns {success, item}."""
    from modules.models import InboxItem
    from modules.meta_api import MetaAPI
    from mcp.tools.publish import _load_decrypted_tokens
    if not user_id:
        raise ValueError('user_id is required')
    if item_id is None:
        raise ValueError('item_id is required')
    item = InboxItem.get_by_id(item_id, user_id=user_id)
    if not item:
        return {'success': False, 'error': 'Item not found'}
    text = (reply_text or '').strip() or (item.ai_draft_reply or '').strip()
    if not text:
        return {'success': False, 'error': 'Reply text is required (no draft stored)'}
    tokens = _load_decrypted_tokens(user_id)
    fb_token = tokens.get('facebook_token')
    ig_token = tokens.get('instagram_token') or fb_token
    meta_api = MetaAPI(
        access_token=fb_token or ig_token or 'dummy',
        page_id=tokens.get('facebook_page_id', ''),
        instagram_id=tokens.get('instagram_id', ''),
    )
    try:
        if item.platform in ('fb', 'facebook'):
            meta_api.reply_to_facebook_comment(item.platform_comment_id, text)
        elif item.platform in ('ig', 'instagram'):
            meta_api.reply_to_instagram_comment(item.platform_comment_id, text)
    except Exception as exc:
        logger.warning('inbox_approve_reply: Meta API reply failed: %s', exc)
    InboxItem.mark_replied(item_id, user_id, final_reply=text, auto_replied=False)
    updated = InboxItem.get_by_id(item_id, user_id=user_id)
    return {'success': True, 'item': updated.to_dict() if updated else None}


def inbox_skip(user_id: str, item_id: int) -> dict:
    """Mark an inbox item skipped. Returns {success, item}."""
    from modules.models import InboxItem
    if not user_id:
        raise ValueError('user_id is required')
    if item_id is None:
        raise ValueError('item_id is required')
    item = InboxItem.get_by_id(item_id, user_id=user_id)
    if not item:
        return {'success': False, 'error': 'Item not found'}
    InboxItem.mark_skipped(item_id, user_id)
    updated = InboxItem.get_by_id(item_id, user_id=user_id)
    return {'success': True, 'item': updated.to_dict() if updated else None}


def inbox_reply(
    comment_text: str,
    user_id: Optional[str] = None,
    post_context: Optional[str] = None,
    tone: str = 'friendly',
) -> dict:
    """Return {sentiment, ai_draft_reply, tone, confidence, source} draft dict."""
    from modules.reply_agent import analyze_and_draft
    if not comment_text or not comment_text.strip():
        raise ValueError('comment_text is required')
    business_name, business_type, location = 'Our Business', 'restaurant', ''
    if user_id:
        from modules.user_manager import UserManager
        profile = UserManager.get_business_profile(user_id) or {}
        business_name = profile.get('name') or business_name
        business_type = profile.get('business_type') or business_type
        location = profile.get('location') or location
    result = analyze_and_draft(
        comment_text=comment_text,
        post_context=post_context,
        tone=tone,
        business_name=business_name,
        business_type=business_type,
        location=location,
    )
    result['posted'] = False  # draft-only contract marker
    return result
