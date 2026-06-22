"""
modules/analytics_client.py
Meta Insights API client -- single source of truth for all analytics.

Previously duplicated in modules/analytics.py (now a tombstone shim).
Difference resolved: both _metric() and _extract_metric() are supported
so callers using either name continue to work.
"""

import requests
from typing import Dict
from datetime import datetime, timedelta


class Analytics:
    BASE = 'https://graph.facebook.com/v19.0'

    def __init__(self, access_token: str, page_id: str):
        self.token   = access_token
        self.page_id = page_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_weekly_summary(self) -> Dict:
        """Return this week's per-post performance plus the best-reach post."""
        posts   = self._get_recent_posts(limit=7)
        summary = []
        for post in posts.get('data', []):
            pid      = post.get('id')
            insights = self._get_post_insights(pid)
            summary.append({
                'post_id':      pid,
                'message':      post.get('message', '')[:80],
                'created_time': post.get('created_time'),
                'likes':        self._metric(insights, 'post_reactions_by_type_total'),
                'reach':        self._metric(insights, 'post_impressions'),
                'engaged':      self._metric(insights, 'post_engaged_users'),
            })
        best = max(summary, key=lambda x: x['reach']) if summary else {}
        return {'success': True, 'posts': summary, 'best_post': best, 'total_posts': len(summary)}

    def get_page_insights(self, days: int = 7) -> Dict:
        """Return page-level impressions, engagement, and fan count for the past N days."""
        since = int((datetime.now() - timedelta(days=days)).timestamp())
        until = int(datetime.now().timestamp())
        return requests.get(
            f'{self.BASE}/{self.page_id}/insights',
            params={
                'metric':       'page_impressions,page_engaged_users,page_fans',
                'since':        since,
                'until':        until,
                'access_token': self.token,
            },
            timeout=10,
        ).json()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_recent_posts(self, limit: int = 7) -> Dict:
        return requests.get(
            f'{self.BASE}/{self.page_id}/posts',
            params={
                'limit':        limit,
                'fields':       'id,message,created_time',
                'access_token': self.token,
            },
            timeout=10,
        ).json()

    def _get_post_insights(self, post_id: str) -> Dict:
        return requests.get(
            f'{self.BASE}/{post_id}/insights',
            params={
                'metric':       'post_impressions,post_engaged_users,post_reactions_by_type_total',
                'access_token': self.token,
            },
            timeout=10,
        ).json()

    def _metric(self, insights: Dict, name: str) -> int:
        """Extract a single integer metric value from an Insights response."""
        for item in insights.get('data', []):
            if item.get('name') == name:
                values = item.get('values', [{}])
                val    = values[-1].get('value', 0) if values else 0
                if isinstance(val, int):
                    return val
                if isinstance(val, dict):
                    return sum(val.values())
                return 0
        return 0

    # Alias: analytics.py used _extract_metric(); keep both so old callers don't break
    _extract_metric = _metric
