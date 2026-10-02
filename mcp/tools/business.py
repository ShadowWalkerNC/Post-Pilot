"""
mcp/tools/business.py — business.get + menu.get (read-only).

Delegates to: modules.user_manager.UserManager, websites table via modules.db.
"""

import json
import logging

logger = logging.getLogger(__name__)

SPEC_BUSINESS_GET = {
    'name': 'business.get',
    'description': 'Get the business profile (name, type, location, hours, tone) for a user.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {'user_id': 'Post-Pilot user ID (required)'},
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_MENU_GET = {
    'name': 'menu.get',
    'description': 'Get the menu section of the user website config (items, prices, descriptions).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {'user_id': 'Post-Pilot user ID (required)'},
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_BUSINESS_UPDATE = {
    'name': 'business.update',
    'description': 'Update business profile fields (name, type, location, hours, tone, keywords).',
    'permission': 'write',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; merges over the existing profile.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'updates': 'Dict of profile fields to set (required, non-empty)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_MENU_LIST = {
    'name': 'menu.list',
    'description': 'List menu items for a user, optionally filtered by search text.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'search': 'Optional case-insensitive substring filter on name/description/category',
        'limit': 'Max items (default 25, max 100)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_MENU_ITEM_GET = {
    'name': 'menu.item_get',
    'description': 'Get one menu item by id or name ({} when not found).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'item': 'Item id or name (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

#: Profile columns business.update accepts (save_business_profile reads these keys).
PROFILE_FIELDS = {
    'name', 'business_name', 'business_type', 'type', 'location', 'hours',
    'prompt_time', 'timezone', 'ai_tone', 'ai_keywords',
}


def business_get(user_id: str) -> dict:
    """Return the business profile dict for user_id ({} when missing)."""
    from modules.user_manager import UserManager
    if not user_id:
        raise ValueError('user_id is required')
    return UserManager.get_business_profile(user_id) or {}


def business_update(user_id: str, updates: dict) -> dict:
    """Merge updates into the profile via UserManager. Returns {success, profile}."""
    from modules.user_manager import UserManager
    if not user_id:
        raise ValueError('user_id is required')
    if not isinstance(updates, dict) or not updates:
        raise ValueError('updates must be a non-empty dict')
    unknown = sorted(set(updates) - PROFILE_FIELDS)
    if unknown:
        raise ValueError(f'unknown profile fields: {unknown}')
    merged = dict(UserManager.get_business_profile(user_id) or {})
    merged.update(updates)
    ok = UserManager.save_business_profile(user_id, merged)
    return {'success': bool(ok), 'profile': UserManager.get_business_profile(user_id) or {}}


def menu_list(user_id: str, search: str = None, limit: int = 25) -> list:
    """Return menu items, optionally filtered by search text."""
    if not user_id:
        raise ValueError('user_id is required')
    limit = max(1, min(int(limit or 25), 100))
    items = menu_get(user_id).get('items', [])
    if search:
        needle = str(search).lower()
        items = [
            item for item in items
            if needle in ' '.join(
                str(item.get(key, '')) for key in ('name', 'description', 'category')
            ).lower()
        ]
    return list(items)[:limit]


def menu_item_get(user_id: str, item: str) -> dict:
    """Return one menu item matched by id or name ({} when not found)."""
    if not user_id:
        raise ValueError('user_id is required')
    if item is None or str(item).strip() == '':
        raise ValueError('item is required')
    want = str(item).strip().lower()
    items = menu_get(user_id).get('items', [])
    for entry in items:
        if str(entry.get('id', '')).lower() == want:
            return entry
    for entry in items:
        if str(entry.get('name', '')).strip().lower() == want:
            return entry
    for entry in items:
        if want in str(entry.get('name', '')).lower():
            return entry
    return {}


def menu_get(user_id: str) -> dict:
    """Return the menu section_data for user_id ({'items': []} when missing)."""
    from modules.db import execute_one
    if not user_id:
        raise ValueError('user_id is required')
    try:
        row = execute_one(
            'SELECT section_data FROM websites WHERE user_id = ?', (user_id,)
        )
    except Exception as exc:
        # Older schemas lack websites.section_data — treat as "no menu yet".
        logger.warning('menu_get(%s) falling back to empty: %s', user_id, exc)
        return {'items': []}
    if not row or not row.get('section_data'):
        return {'items': []}
    try:
        data = json.loads(row['section_data'])
    except (ValueError, TypeError):
        return {'items': []}
    menu = data.get('menu', {})
    if isinstance(menu, list):
        return {'items': menu}
    if isinstance(menu, dict):
        return {'items': menu.get('items', []), **{k: v for k, v in menu.items() if k != 'items'}}
    return {'items': []}
