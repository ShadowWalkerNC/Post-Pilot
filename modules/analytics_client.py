"""
modules/analytics_client.py
Meta Insights API client -- Facebook Pages + Instagram Business.

Main entry point: Analytics.get_combined_summary(days)
Returns a single dict with KPIs, chart series, IG metrics, and post table
ready for the analytics dashboard to render directly.
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class Analytics:
    BASE = 'https://graph.facebook.com/v19.0'

    def __init__(self, access_token: str, page_id: str, ig_id: Optional[str] = None):
        self.token   = access_token
        self.page_id = page_id
        self.ig_id   = ig_id

    # ------------------------------------------------------------------
    # Primary combined entry point
    # ------------------------------------------------------------------

    def get_combined_summary(self, days: int = 30) -> Dict:
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        until = int(datetime.utcnow().timestamp())

        page_data = self._get_page_daily(since, until)
        chart     = self._build_chart_series(page_data, days)

        posts_raw     = self._get_recent_posts(limit=min(days, 25), since=since)
        post_rows     = []
        total_reach   = 0
        total_likes   = 0
        total_engaged = 0
        for post in posts_raw.get('data', []):
            pid      = post.get('id')
            insights = self._get_post_insights(pid)
            reach    = self._metric(insights, 'post_impressions')
            likes    = self._metric(insights, 'post_reactions_by_type_total')
            engaged  = self._metric(insights, 'post_engaged_users')
            total_reach   += reach
            total_likes   += likes
            total_engaged += engaged
            post_rows.append({
                'post_id':      pid,
                'message':      post.get('message', '')[:100],
                'created_time': post.get('created_time', ''),
                'reach':        reach,
                'likes':        likes,
                'engaged':      engaged,
            })

        eng_rate = round(total_engaged / total_reach * 100, 1) if total_reach else 0.0
        ig       = self.get_instagram_insights(days=days) if self.ig_id else {}

        return {
            'success': True,
            'kpis': {
                'posts':    len(post_rows),
                'reach':    total_reach,
                'likes':    total_likes,
                'engaged':  total_engaged,
                'eng_rate': eng_rate,
            },
            'chart': chart,
            'ig':    ig,
            'posts': post_rows,
        }

    # ------------------------------------------------------------------
    # Instagram insights
    # ------------------------------------------------------------------

    def get_instagram_insights(self, days: int = 30) -> Dict:
        if not self.ig_id:
            return {}
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        until = int(datetime.utcnow().timestamp())
        try:
            user_resp = requests.get(
                f'{self.BASE}/{self.ig_id}',
                params={'fields': 'followers_count', 'access_token': self.token},
                timeout=10,
            ).json()
            followers = user_resp.get('followers_count', 0)

            ins_resp = requests.get(
                f'{self.BASE}/{self.ig_id}/insights',
                params={
                    'metric':       'reach,impressions,profile_views',
                    'period':       'day',
                    'since':        since,
                    'until':        until,
                    'access_token': self.token,
                },
                timeout=10,
            ).json()

            reach         = sum(v.get('value', 0) for v in self._daily_values(ins_resp, 'reach'))
            impressions   = sum(v.get('value', 0) for v in self._daily_values(ins_resp, 'impressions'))
            profile_views = sum(v.get('value', 0) for v in self._daily_values(ins_resp, 'profile_views'))

            return {
                'followers':     followers,
                'reach':         reach,
                'impressions':   impressions,
                'profile_views': profile_views,
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Legacy public methods (backwards compat)
    # ------------------------------------------------------------------

    def get_weekly_summary(self) -> Dict:
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
        since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        until = int(datetime.utcnow().timestamp())
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

    def _get_page_daily(self, since: int, until: int) -> Dict:
        try:
            return requests.get(
                f'{self.BASE}/{self.page_id}/insights',
                params={
                    'metric':       'page_impressions,page_engaged_users',
                    'period':       'day',
                    'since':        since,
                    'until':        until,
                    'access_token': self.token,
                },
                timeout=10,
            ).json()
        except Exception:
            return {}

    def _build_chart_series(self, page_data: Dict, days: int) -> Dict:
        reach_vals   = self._daily_values(page_data, 'page_impressions')
        engaged_vals = self._daily_values(page_data, 'page_engaged_users')
        reach_map    = {v['end_time'][:10]: v['value'] for v in reach_vals}
        engaged_map  = {v['end_time'][:10]: v['value'] for v in engaged_vals}
        labels  = sorted(set(list(reach_map.keys()) + list(engaged_map.keys())))[-days:]
        return {
            'labels':  labels,
            'reach':   [reach_map.get(d, 0)   for d in labels],
            'engaged': [engaged_map.get(d, 0) for d in labels],
        }

    def _daily_values(self, insights: Dict, metric_name: str) -> List[Dict]:
        for item in insights.get('data', []):
            if item.get('name') == metric_name:
                return item.get('values', [])
        return []

    def _get_recent_posts(self, limit: int = 7, since: Optional[int] = None) -> Dict:
        params = {'limit': limit, 'fields': 'id,message,created_time', 'access_token': self.token}
        if since:
            params['since'] = since
        try:
            return requests.get(f'{self.BASE}/{self.page_id}/posts', params=params, timeout=10).json()
        except Exception:
            return {'data': []}

    def _get_post_insights(self, post_id: str) -> Dict:
        try:
            return requests.get(
                f'{self.BASE}/{post_id}/insights',
                params={
                    'metric':       'post_impressions,post_engaged_users,post_reactions_by_type_total',
                    'access_token': self.token,
                },
                timeout=10,
            ).json()
        except Exception:
            return {'data': []}

    def _metric(self, insights: Dict, name: str) -> int:
        for item in insights.get('data', []):
            if item.get('name') == name:
                values = item.get('values', [{}])
                val    = values[-1].get('value', 0) if values else 0
                if isinstance(val, int):  return val
                if isinstance(val, dict): return sum(val.values())
                return 0
        return 0

    _extract_metric = _metric
