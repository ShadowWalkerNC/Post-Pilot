"""
integrations/meta.py — Canonical Meta Graph API client for Post-Pilot.
Inherits / adapts to ProviderClient while maintaining backwards compatibility with MetaAPI.
"""

from typing import Dict, Optional, Any
from datetime import datetime
import requests
from integrations.base import ProviderClient


class MetaAPI(ProviderClient):
    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self, access_token: str, page_id: str, instagram_id: Optional[str] = None):
        self.token = access_token
        self.page_id = page_id
        self.ig_id = instagram_id

    # ------------------------------------------------------------------
    # ProviderClient interface implementation
    # ------------------------------------------------------------------

    def publish(
        self,
        text: str,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        link_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Publish to Facebook (default) or Instagram based on kwargs."""
        platform = kwargs.get('platform', 'facebook')
        if platform == 'instagram':
            return self.post_to_instagram(caption=text, image_url=image_url)
        return self.post_to_facebook(message=text, image_url=image_url)

    def schedule(
        self,
        text: str,
        publish_time: datetime,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Schedule to Facebook (default) or Instagram based on kwargs."""
        platform = kwargs.get('platform', 'facebook')
        if platform == 'instagram':
            return self.schedule_instagram_post(caption=text, image_url=image_url, publish_time=publish_time)
        return self.schedule_facebook_post(message=text, publish_time=publish_time, image_url=image_url)

    def get_insights(self, days: int = 30) -> Dict[str, Any]:
        """Fetch general page insights."""
        return self.get_page_posts(limit=days)

    # ------------------------------------------------------------------
    # Facebook Graph API
    # ------------------------------------------------------------------

    def post_to_facebook(self, message: str, image_url: str = None) -> Dict:
        """Publish immediately to Facebook Page"""
        if image_url:
            endpoint = f"{self.BASE}/{self.page_id}/photos"
            params = {'url': image_url, 'caption': message, 'access_token': self.token}
        else:
            endpoint = f"{self.BASE}/{self.page_id}/feed"
            params = {'message': message, 'access_token': self.token}
        res = requests.post(endpoint, params=params)
        return res.json()

    def schedule_facebook_post(self, message: str, publish_time: datetime, image_url: str = None) -> Dict:
        """Schedule a Facebook post for a future time"""
        unix_time = int(publish_time.timestamp())
        endpoint = f"{self.BASE}/{self.page_id}/feed"
        params = {
            'message': message,
            'published': False,
            'scheduled_publish_time': unix_time,
            'access_token': self.token
        }
        res = requests.post(endpoint, params=params)
        return res.json()

    # ------------------------------------------------------------------
    # Instagram Graph API
    # ------------------------------------------------------------------

    def post_to_instagram(self, caption: str, image_url: str) -> Dict:
        """Publish immediately to Instagram Business account"""
        if not self.ig_id:
            return {'error': 'Instagram ID not configured'}
        container = requests.post(
            f"{self.BASE}/{self.ig_id}/media",
            params={'image_url': image_url, 'caption': caption, 'access_token': self.token}
        ).json()
        creation_id = container.get('id')
        if not creation_id:
            return {'error': 'Failed to create media container', 'details': container}
        publish = requests.post(
            f"{self.BASE}/{self.ig_id}/media_publish",
            params={'creation_id': creation_id, 'access_token': self.token}
        ).json()
        return publish

    def schedule_instagram_post(self, caption: str, image_url: str, publish_time: datetime) -> Dict:
        """Schedule an Instagram post for a future time"""
        if not self.ig_id:
            return {'error': 'Instagram ID not configured'}
        unix_time = int(publish_time.timestamp())
        container = requests.post(
            f"{self.BASE}/{self.ig_id}/media",
            params={
                'image_url': image_url,
                'caption': caption,
                'scheduled_publish_time': unix_time,
                'media_type': 'IMAGE',
                'access_token': self.token
            }
        ).json()
        creation_id = container.get('id')
        if not creation_id:
            return {'error': 'Failed to create scheduled container', 'details': container}
        publish = requests.post(
            f"{self.BASE}/{self.ig_id}/media_publish",
            params={'creation_id': creation_id, 'access_token': self.token}
        ).json()
        return publish

    def get_page_posts(self, limit: int = 10) -> Dict:
        """Get recent posts from Facebook Page"""
        res = requests.get(
            f"{self.BASE}/{self.page_id}/posts",
            params={'limit': limit, 'access_token': self.token}
        )
        return res.json()

    def get_post_insights(self, post_id: str) -> Dict:
        """Get insights (likes, comments, reach) for a specific post"""
        res = requests.get(
            f"{self.BASE}/{post_id}/insights",
            params={
                'metric': 'post_impressions,post_engaged_users,post_reactions_by_type_total',
                'access_token': self.token
            }
        )
        return res.json()

    # ------------------------------------------------------------------
    # Social Comment Inbox & Moderation (M3)
    # ------------------------------------------------------------------

    def get_facebook_comments(self, post_id: str, limit: int = 25) -> Dict:
        """Fetch comments on a Facebook post"""
        res = requests.get(
            f"{self.BASE}/{post_id}/comments",
            params={
                'fields': 'id,message,created_time,from,like_count,comment_count',
                'limit': limit,
                'access_token': self.token,
            }
        )
        return res.json()

    def get_instagram_comments(self, media_id: str, limit: int = 25) -> Dict:
        """Fetch comments on an Instagram media post"""
        res = requests.get(
            f"{self.BASE}/{media_id}/comments",
            params={
                'fields': 'id,text,timestamp,username,like_count,hidden',
                'limit': limit,
                'access_token': self.token,
            }
        )
        return res.json()

    def fetch_comments(self, platform: str, object_id: str, limit: int = 25) -> Dict:
        """Universal comment fetch router"""
        plat = (platform or '').lower()
        if plat in ('fb', 'facebook'):
            return self.get_facebook_comments(object_id, limit=limit)
        if plat in ('ig', 'instagram'):
            return self.get_instagram_comments(object_id, limit=limit)
        return {'error': f'Unsupported platform for comment fetching: {platform}'}

    def reply_to_facebook_comment(self, comment_id: str, message: str) -> Dict:
        """Post a reply to a Facebook comment"""
        res = requests.post(
            f"{self.BASE}/{comment_id}/comments",
            params={'message': message, 'access_token': self.token}
        )
        return res.json()

    def reply_to_instagram_comment(self, comment_id: str, message: str) -> Dict:
        """Post a reply to an Instagram comment"""
        res = requests.post(
            f"{self.BASE}/{comment_id}/replies",
            params={'message': message, 'access_token': self.token}
        )
        return res.json()

    def reply_to_comment(self, platform: str, comment_id: str, message: str) -> Dict:
        """Universal comment reply router"""
        plat = (platform or '').lower()
        if plat in ('fb', 'facebook'):
            return self.reply_to_facebook_comment(comment_id, message)
        if plat in ('ig', 'instagram'):
            return self.reply_to_instagram_comment(comment_id, message)
        return {'error': f'Unsupported platform for comment replying: {platform}'}

    def hide_facebook_comment(self, comment_id: str, is_hidden: bool = True) -> Dict:
        """Hide or unhide a Facebook comment"""
        res = requests.post(
            f"{self.BASE}/{comment_id}",
            params={'is_hidden': is_hidden, 'access_token': self.token}
        )
        return res.json()

    def hide_instagram_comment(self, comment_id: str, hide: bool = True) -> Dict:
        """Hide or unhide an Instagram comment"""
        res = requests.post(
            f"{self.BASE}/{comment_id}",
            params={'hide': hide, 'access_token': self.token}
        )
        return res.json()

    def hide_comment(self, platform: str, comment_id: str, hide: bool = True) -> Dict:
        """Universal comment hide router"""
        plat = (platform or '').lower()
        if plat in ('fb', 'facebook'):
            return self.hide_facebook_comment(comment_id, is_hidden=hide)
        if plat in ('ig', 'instagram'):
            return self.hide_instagram_comment(comment_id, hide=hide)
        return {'error': f'Unsupported platform for comment hiding: {platform}'}

    def post_instagram_comment(self, media_id: str, message: str) -> Dict:
        """Post a top-level comment to an Instagram media post (e.g. First Comment hashtags)."""
        res = requests.post(
            f"{self.BASE}/{media_id}/comments",
            params={'message': message, 'access_token': self.token}
        )
        return res.json()
