"""
mcp/tools/analytics.py — analytics.get + analytics.top_posts + analytics.performance_summary.

Delegates to: modules.analytics_client.Analytics (read-only projections).
"""

SPEC_ANALYTICS_GET = {
    'name': 'analytics.get',
    'description': 'Get combined Meta (FB+IG) analytics summary for a user over N days.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Uses the user stored Meta tokens server-side; tokens are never exposed.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'days': 'Lookback window (default 30, max 90)',
    },
    'secrets': 'Never returns tokens or API keys.',
}


SPEC_ANALYTICS_TOP_POSTS = {
    'name': 'analytics.top_posts',
    'description': 'Top posts ranked by a metric (engaged, reach, or likes).',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Uses the user stored Meta tokens server-side; tokens are never exposed.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'days': 'Lookback window (default 30, max 90)',
        'limit': 'Max posts (default 5, max 25)',
        'metric': 'engaged | reach | likes (default engaged)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_ANALYTICS_PERFORMANCE_SUMMARY = {
    'name': 'analytics.performance_summary',
    'description': 'Compact KPI summary: totals, engagement rate, post count, IG coverage.',
    'permission': 'read',
    'auth': 'Caller must be the account owner or team member. Uses the user stored Meta tokens server-side; tokens are never exposed.',
    'inputs': {
        'user_id': 'Post-Pilot user ID (required)',
        'days': 'Lookback window (default 30, max 90)',
    },
    'secrets': 'Never returns tokens or API keys.',
}

TOP_POST_METRICS = {'engaged', 'reach', 'likes'}


def analytics_top_posts(
    user_id: str, days: int = 30, limit: int = 5, metric: str = 'engaged'
) -> dict:
    """Return top posts by metric, or the analytics_get error dict when unconnected."""
    if metric not in TOP_POST_METRICS:
        raise ValueError(f'metric must be one of {sorted(TOP_POST_METRICS)}')
    limit = max(1, min(int(limit or 5), 25))
    summary = analytics_get(user_id, days=days)
    if not summary.get('success'):
        return summary
    ranked = sorted(summary.get('posts', []), key=lambda p: p.get(metric, 0) or 0, reverse=True)
    return {'success': True, 'metric': metric, 'days': days, 'posts': ranked[:limit]}


def analytics_performance_summary(user_id: str, days: int = 30) -> dict:
    """Return compact KPIs, or the analytics_get error dict when unconnected."""
    summary = analytics_get(user_id, days=days)
    if not summary.get('success'):
        return summary
    kpis = summary.get('kpis', {})
    return {
        'success': True,
        'days': days,
        'kpis': kpis,
        'posts_count': len(summary.get('posts', [])),
        'has_instagram': bool(summary.get('ig')),
    }


def analytics_get(user_id: str, days: int = 30) -> dict:
    """Return combined analytics summary, or {'success': False} when unconnected."""
    from modules.analytics_client import Analytics
    from mcp.tools.publish import _load_decrypted_tokens
    if not user_id:
        raise ValueError('user_id is required')
    days = max(1, min(int(days or 30), 90))
    tokens = _load_decrypted_tokens(user_id)
    fb_token = tokens.get('facebook_token', '')
    page_id = tokens.get('facebook_page_id', '')
    if not fb_token or not page_id:
        return {'success': False, 'error': 'Facebook not connected for this user'}
    ig_id = tokens.get('instagram_id') or None
    client = Analytics(access_token=fb_token, page_id=page_id, ig_id=ig_id)
    return client.get_combined_summary(days=days)
