"""
mcp/tools/brand.py — brand.get + brand.validate (read-only, deterministic).

brand.get delegates to: business_profiles via modules.user_manager.
brand.validate runs deterministic checks against that profile (no LLM calls):
text presence, tone known, business-name mention, keyword hits.
"""

SPEC_BRAND_GET = {
    'name': 'brand.get',
    'description': 'Get the brand voice fields for a user (name, type, tone, keywords).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Scoped to user_id; no cross-tenant reads.',
    'inputs': {'user_id': 'Post-Pilot user ID (required)'},
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_BRAND_VALIDATE = {
    'name': 'brand.validate',
    'description': 'Deterministic brand check on a text (v1: no LLM). Returns checks + verdict.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Read-only computation; nothing is stored.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'text': 'Text to validate (required)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


def brand_get(user_id: str) -> dict:
    """Return brand voice fields for user_id (empty strings when missing)."""
    from modules.user_manager import UserManager
    if not user_id:
        raise ValueError('user_id is required')
    profile = UserManager.get_business_profile(user_id) or {}
    return {
        'name': profile.get('name') or '',
        'business_type': profile.get('business_type') or '',
        'ai_tone': profile.get('ai_tone') or '',
        'ai_keywords': profile.get('ai_keywords') or '',
        'location': profile.get('location') or '',
    }


def brand_validate(user_id: str, text: str) -> dict:
    """Return {checks, verdict} for text against the user brand (deterministic)."""
    from modules.reply_agent import TONES
    if not user_id:
        raise ValueError('user_id is required')
    if text is None or str(text).strip() == '':
        raise ValueError('text is required')
    brand = brand_get(user_id)
    lowered = str(text).lower()
    name = (brand.get('name') or '').strip()
    keywords = [k.strip().lower() for k in (brand.get('ai_keywords') or '').split(',') if k.strip()]
    checks = {
        'has_text': bool(lowered.strip()),
        'tone_known': (brand.get('ai_tone') or '') in set(TONES),
        'name_mentioned': bool(name) and name.lower() in lowered,
        'keyword_hits': sum(1 for kw in keywords if kw in lowered),
    }
    verdict = 'pass' if checks['has_text'] and checks['tone_known'] else 'needs-review'
    return {'checks': checks, 'verdict': verdict, 'brand': brand}
