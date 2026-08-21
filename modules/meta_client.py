"""
PostPilot Pro — Meta API Client
Handles all Facebook and Instagram Graph API interactions.
"""

import requests
from datetime import datetime
from typing import Dict, Optional


class MetaAPI:
    BASE = 'https://graph.facebook.com/v19.0'

    def __init__(self, access_token: str, page_id: str, instagram_id: Optional[str] = None):
        self.token   = access_token
        self.page_id = page_id
        self.ig_id   = instagram_id

    def post_to_facebook(self, message: str, image_url: str = None) -> Dict:
        if image_url:
            endpoint = f'{self.BASE}/{self.page_id}/photos'
            params   = {'url': image_url, 'caption': message, 'access_token': self.token}
        else:
            endpoint = f'{self.BASE}/{self.page_id}/feed'
            params   = {'message': message, 'access_token': self.token}
        return requests.post(endpoint, params=params).json()

    def schedule_facebook_post(self, message: str, publish_time: datetime, image_url: str = None) -> Dict:
        return requests.post(
            f'{self.BASE}/{self.page_id}/feed',
            params={
                'message': message,
                'published': False,
                'scheduled_publish_time': int(publish_time.timestamp()),
                'access_token': self.token
            }
        ).json()

    def post_to_instagram(self, caption: str, image_url: str) -> Dict:
        if not self.ig_id:
            return {'error': 'Instagram ID not configured'}
        container = requests.post(
            f'{self.BASE}/{self.ig_id}/media',
            params={'image_url': image_url, 'caption': caption, 'access_token': self.token}
        ).json()
        creation_id = container.get('id')
        if not creation_id:
            return {'error': 'Failed to create media container', 'details': container}
        return requests.post(
            f'{self.BASE}/{self.ig_id}/media_publish',
            params={'creation_id': creation_id, 'access_token': self.token}
        ).json()

    def schedule_instagram_post(self, caption: str, image_url: str, publish_time: datetime) -> Dict:
        if not self.ig_id:
            return {'error': 'Instagram ID not configured'}
        container = requests.post(
            f'{self.BASE}/{self.ig_id}/media',
            params={
                'image_url': image_url, 'caption': caption,
                'scheduled_publish_time': int(publish_time.timestamp()),
                'media_type': 'IMAGE', 'access_token': self.token
            }
        ).json()
        creation_id = container.get('id')
        if not creation_id:
            return {'error': 'Failed to create scheduled container', 'details': container}
        return requests.post(
            f'{self.BASE}/{self.ig_id}/media_publish',
            params={'creation_id': creation_id, 'access_token': self.token}
        ).json()

    def get_page_posts(self, limit: int = 10) -> Dict:
        return requests.get(
            f'{self.BASE}/{self.page_id}/posts',
            params={'limit': limit, 'access_token': self.token}
        ).json()

    def get_post_insights(self, post_id: str) -> Dict:
        return requests.get(
            f'{self.BASE}/{post_id}/insights',
            params={
                'metric': 'post_impressions,post_engaged_users,post_reactions_by_type_total',
                'access_token': self.token
            }
        ).json()

    # ------------------------------------------------------------------
    # Social Comment Inbox & Moderation (M3)
    # ------------------------------------------------------------------

    def get_facebook_comments(self, post_id: str, limit: int = 25) -> Dict:
        """Fetch comments on a Facebook post"""
        res = requests.get(
            f'{self.BASE}/{post_id}/comments',
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
            f'{self.BASE}/{media_id}/comments',
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
            f'{self.BASE}/{comment_id}/comments',
            params={'message': message, 'access_token': self.token}
        )
        return res.json()

    def reply_to_instagram_comment(self, comment_id: str, message: str) -> Dict:
        """Post a reply to an Instagram comment"""
        res = requests.post(
            f'{self.BASE}/{comment_id}/replies',
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
            f'{self.BASE}/{comment_id}',
            params={'is_hidden': is_hidden, 'access_token': self.token}
        )
        return res.json()

    def hide_instagram_comment(self, comment_id: str, hide: bool = True) -> Dict:
        """Hide or unhide an Instagram comment"""
        res = requests.post(
            f'{self.BASE}/{comment_id}',
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
        return {'error': f'Unsupported platform for comment replying: {platform}'}
