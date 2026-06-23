"""
modules/analytics_client.py
Meta Insights API client -- Facebook Pages + Instagram Business.
Also exposes get_google_youtube_summary() for Google Business + YouTube.

Main entry point: Analytics.get_combined_summary(days)
Returns a single dict with KPIs, chart series, IG metrics, post table,
and google/youtube section ready for the analytics dashboard.
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
    # Google Business + YouTube summary
    # ------------------------------------------------------------------

    @staticmethod
    def get_google_youtube_summary(user_id: str, location_id: str = '', days: int = 30) -> Dict:
        """
        Pull Google Business recent posts and YouTube channel stats + recent
        video analytics.  Returns a dict under the 'google' key in the
        /api/analytics response.

        Args:
            user_id:     Post-Pilot user ID (for token lookup).
            location_id: GMB location resource name. Falls back to token meta.
            days:        Lookback window (used for display labels only;
                         GMB posts are capped at 10 by default).

        Returns:
            {
              'gmb': {
                'posts': [ { title, summary, create_time, url } ... ]
              },
              'youtube': {
                'subscribers': int,
                'total_views': int,
                'video_count': int,
                'recent_videos': [ { id, title, views, likes, comments } ... ]
              }
            }
            On partial failure the affected sub-key will be {}.
        """
        from modules.google_client import GoogleBusinessClient, YouTubeClient
        from modules.auth_manager  import get_token

        result: Dict = {'gmb': {}, 'youtube': {}}

        # ── Resolve location_id from token meta if not passed in ──────
        if not location_id:
            try:
                tok_row = get_token('google', user_id)
                if tok_row:
                    meta        = tok_row.get('meta') or {}
                    location_id = meta.get('location_id', '')
            except Exception:
                pass

        # ── Google Business posts ─────────────────────────────────────
        if location_id:
            try:
                gbc   = GoogleBusinessClient(location_id, user_id=user_id)
                raw   = gbc.get_posts(page_size=10)
                posts = []
                for p in raw.get('localPosts', []):
                    posts.append({
                        'title':       p.get('event', {}).get('title', '') or p.get('topicType', 'Post'),
                        'summary':     (p.get('summary', '') or '')[:120],
                        'create_time': p.get('createTime', ''),
                        'url':         p.get('searchUrl', ''),
                    })
                result['gmb'] = {'posts': posts}
            except Exception:
                result['gmb'] = {}

        # ── YouTube channel stats + recent video analytics ────────────
        try:
            ytc   = YouTubeClient(user_id=user_id)
            stats = ytc.get_channel_stats()
            if 'error' not in stats:
                # fetch up to 5 recent video IDs
                from modules.auth_manager import get_valid_google_token
                token = get_valid_google_token(user_id)
                recent_videos = []
                if token:
                    vid_resp = requests.get(
                        'https://www.googleapis.com/youtube/v3/search',
                        headers={'Authorization': f'Bearer {token}'},
                        params={
                            'part':       'snippet',
                            'forMine':    'true',
                            'type':       'video',
                            'order':      'date',
                            'maxResults': 5,
                        },
                        timeout=10,
                    ).json()
                    for item in vid_resp.get('items', []):
                        vid_id    = item.get('id', {}).get('videoId', '')
                        title     = item.get('snippet', {}).get('title', '')
                        analytics = ytc.get_video_analytics(vid_id) if vid_id else {}
                        recent_videos.append({
                            'id':       vid_id,
                            'title':    title,
                            'views':    analytics.get('views',    0),
                            'likes':    analytics.get('likes',    0),
                            'comments': analytics.get('comments', 0),
                        })
                result['youtube'] = {**stats, 'recent_videos': recent_videos}
            else:
                result['youtube'] = {}
        except Exception:
            result['youtube'] = {}

        return result

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
