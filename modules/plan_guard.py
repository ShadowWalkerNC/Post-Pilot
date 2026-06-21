"""
plan_guard.py -- Subscription plan enforcement for Post-Pilot.

Usage in app.py:
    from modules.plan_guard import require_plan, check_platform_limit

    @app.route('/api/analytics', methods=['POST'])
    @login_required
    @require_plan('pro')
    def api_analytics():
        ...

Plan hierarchy (weakest to strongest):
    free < starter < pro < agency

Feature -> minimum plan mapping is defined in FEATURE_PLANS (from PRICING.md).
"""

import functools
import logging
from flask import jsonify, request, redirect, url_for, flash
from flask_login import current_user

logger = logging.getLogger(__name__)

PLAN_RANK = {
    'free':    0,
    'starter': 1,
    'pro':     2,
    'agency':  3,
}

# Feature -> minimum required plan (mirrors PRICING.md)
FEATURE_PLANS = {
    'multi_platform': 'starter',
    'ai_generate':    'starter',
    'scheduling':     'starter',
    'analytics':      'pro',
    'bulk_schedule':  'pro',
    'api_access':     'pro',
    'website_hub':    'starter',
    'white_label':    'agency',
}

# Per-plan concurrent platform limits
PLATFORM_LIMITS = {
    'free':    1,
    'starter': 3,
    'pro':     6,
    'agency':  6,
}


def _plan_rank(tier: str) -> int:
    return PLAN_RANK.get((tier or 'free').lower(), 0)


def require_plan(minimum_plan: str):
    """
    Decorator: block users below `minimum_plan`.
    - API/JSON requests -> 403 JSON with upgrade_url
    - Browser requests  -> redirect to /billing with flash
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            user_tier = getattr(current_user, 'subscription_tier', 'free') or 'free'
            if _plan_rank(user_tier) < _plan_rank(minimum_plan):
                logger.warning(
                    'Plan gate blocked: user=%s tier=%s path=%s requires=%s',
                    getattr(current_user, 'id', 'anon'), user_tier, request.path, minimum_plan
                )
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({
                        'success': False,
                        'error': {
                            'code':        'PLAN_REQUIRED',
                            'message':     f'This feature requires the {minimum_plan.title()} plan or higher.',
                            'upgrade_url': '/billing',
                        }
                    }), 403
                flash(f'Upgrade to {minimum_plan.title()} to unlock this feature.', 'warning')
                return redirect(url_for('billing'))
            return f(*args, **kwargs)
        return wrapped
    return decorator


def check_platform_limit(user_tier: str, requested_platforms: list) -> tuple[bool, int]:
    """
    Check whether the user's plan allows publishing to N platforms at once.
    Returns (allowed: bool, limit: int).
    """
    tier  = (user_tier or 'free').lower()
    limit = PLATFORM_LIMITS.get(tier, 1)
    return len(requested_platforms) <= limit, limit
