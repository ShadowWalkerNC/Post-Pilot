"""
PostPilot Pro — Universal Publisher
Smart routing: videos → video platforms, text → text platforms,
images → image platforms. Write once, push everywhere.

Option B support:
    push_all() accepts either:
      caption  (str)  — single caption used for all platforms (old behaviour)
      captions (dict) — {platform_key: text} per-platform captions (Option B)
    When captions dict is provided, each platform gets its own adapted text.
    Falls back to caption string if a platform key is missing from the dict.
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, Optional, Union

from modules.google_client import GoogleBusinessClient, YouTubeClient
from modules.tiktok_client import TikTokClient, TikTokScriptGenerator


# ---------------------------------------------------------------------------
# Platform key normalisation map (long name → short key)
# ---------------------------------------------------------------------------
KEY_MAP: Dict[str, str] = {
    'facebook':       'fb',
    'instagram':      'ig',
    'youtube':        'yt',
    'youtube_shorts': 'yts',
    'tiktok':         'tt',
    'google':         'gb',
    'website':        'web',
    'linkedin':       'li',
    'twitter':        'tw',
    'x':              'tw',
    'pinterest':      'pi',
}

# ---------------------------------------------------------------------------
# Smart routing rules — which platforms suit which content types
# ---------------------------------------------------------------------------
ROUTING_RULES: Dict[str, list] = {
    'text':   ['fb', 'li', 'tw', 'gb', 'web'],
    'image':  ['fb', 'ig', 'pi', 'li', 'gb', 'web'],
    'video':  ['fb', 'ig', 'yt', 'yts', 'tt', 'web'],
    'promo':  ['fb', 'ig', 'tt', 'yts', 'li', 'tw', 'gb', 'web'],
    'update': ['fb', 'li', 'tw', 'gb', 'web'],
}


class UniversalPublisher:

    def __init__(self, tokens: Dict, user_id: str = 'default'):
        self.tokens  = tokens
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def push_all(
        self,
        caption:       Union[str, None]  = None,
        content_type:  str               = 'text',
        image_url:     Optional[str]     = None,
        video_url:     Optional[str]     = None,
        link_url:      Optional[str]     = None,
        platforms:     Optional[Union[Dict, list]] = None,
        schedule_time: Optional[str]     = None,
        web_data:      Optional[Dict]    = None,
        captions:      Optional[Dict]    = None,   # Option B: {platform_key: text}
    ) -> Dict:
        """
        Publish to all requested platforms.

        Args:
            caption:      Single caption string used for all platforms.
                          Used as fallback when captions dict is missing a key.
            captions:     Per-platform caption dict {platform_key: text}.
                          When provided, each platform gets its own text.
                          Falls back to caption string for any missing key.
            content_type: Used for smart routing when platforms not specified.
            platforms:    Dict {key: bool} or list of platform keys/names.
                          If None, auto-selected from ROUTING_RULES.
            (other args as before)
        """
        # Normalise platforms → {short_key: bool} dict
        if platforms is None:
            auto      = ROUTING_RULES.get(content_type, ['fb', 'web'])
            platforms = {p: True for p in auto}
        elif isinstance(platforms, list):
            platforms = {KEY_MAP.get(p, p): True for p in platforms}

        results = {}

        if platforms.get('fb'):
            cap = self._resolve_caption(captions, caption, 'fb')
            results['fb'] = self._publish_facebook(cap, image_url, video_url, schedule_time)

        if platforms.get('ig'):
            cap = self._resolve_caption(captions, caption, 'ig')
            if image_url or video_url:
                results['ig'] = self._publish_instagram(cap, image_url or video_url, schedule_time)
            else:
                results['ig'] = {'success': False, 'error': 'Instagram requires an image or video URL'}

        if platforms.get('yt'):
            cap = self._resolve_caption(captions, caption, 'yt')
            results['yt'] = self._handle_youtube(cap, video_url)

        if platforms.get('yts'):
            cap = self._resolve_caption(captions, caption, 'yts')
            results['yts'] = self._handle_youtube_shorts(cap, video_url)

        if platforms.get('tt'):
            cap = self._resolve_caption(captions, caption, 'tt')
            results['tt'] = self._handle_tiktok(cap, video_url)

        if platforms.get('gb'):
            cap = self._resolve_caption(captions, caption, 'gb')
            results['gb'] = self._publish_google_business(cap, image_url, link_url)

        if platforms.get('li'):
            cap = self._resolve_caption(captions, caption, 'li')
            results['li'] = self._publish_linkedin(cap, image_url, link_url)

        if platforms.get('tw'):
            cap = self._resolve_caption(captions, caption, 'tw')
            results['tw'] = self._publish_twitter(cap, image_url)

        if platforms.get('pi'):
            cap = self._resolve_caption(captions, caption, 'pi')
            results['pi'] = self._publish_pinterest(cap, image_url, link_url)

        if platforms.get('web'):
            cap = self._resolve_caption(captions, caption, 'web')
            results['web'] = self._update_website(cap, image_url, link_url, web_data)

        return results

    # ------------------------------------------------------------------
    # Caption resolver
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_caption(
        captions: Optional[Dict],
        fallback: Optional[str],
        platform: str,
    ) -> str:
        """
        Return the per-platform caption if available, else fall back
        to the master caption string.
        """
        if captions and platform in captions:
            return captions[platform]
        return fallback or ''

    # ------------------------------------------------------------------
    # Facebook
    # ------------------------------------------------------------------

    def _publish_facebook(self, caption, image_url, video_url, schedule_time=None):
        token   = self.tokens.get('facebook_token')
        page_id = self.tokens.get('facebook_page_id')
        if not token or not page_id:
            return {'success': False, 'error': 'Facebook not connected'}
        try:
            if video_url and not video_url.startswith('http'):
                return {'success': False, 'error': 'Video URL must be a public https URL'}
            if video_url:
                endpoint = f'https://graph.facebook.com/v19.0/{page_id}/videos'
                params   = {'file_url': video_url, 'description': caption, 'access_token': token}
            elif image_url:
                endpoint = f'https://graph.facebook.com/v19.0/{page_id}/photos'
                params   = {'url': image_url, 'caption': caption, 'access_token': token}
            else:
                endpoint = f'https://graph.facebook.com/v19.0/{page_id}/feed'
                params   = {'message': caption, 'access_token': token}
            if schedule_time:
                ts = int(datetime.fromisoformat(schedule_time).timestamp())
                params.update({'published': False, 'scheduled_publish_time': ts})
            r = requests.post(endpoint, params=params)
            d = r.json()
            label = 'Scheduled' if schedule_time else ('Video posted' if video_url else 'Posted')
            return {
                'success': r.status_code == 200,
                'post_id': d.get('id'),
                'message': label,
                'error':   d.get('error', {}).get('message') if r.status_code != 200 else None,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Instagram
    # ------------------------------------------------------------------

    def _publish_instagram(self, caption, media_url, schedule_time=None):
        token = self.tokens.get('instagram_token')
        ig_id = self.tokens.get('instagram_id')
        if not token or not ig_id:
            return {'success': False, 'error': 'Instagram not connected'}
        try:
            is_video = media_url and (media_url.endswith('.mp4') or 'video' in media_url)
            params   = {'caption': caption, 'access_token': token}
            if is_video:
                params['media_type'] = 'REELS'
                params['video_url']  = media_url
            else:
                params['image_url'] = media_url
            c = requests.post(f'https://graph.facebook.com/v19.0/{ig_id}/media', params=params)
            if c.status_code != 200:
                return {'success': False, 'error': 'Failed to create media container', 'detail': c.json()}
            p = requests.post(
                f'https://graph.facebook.com/v19.0/{ig_id}/media_publish',
                params={'creation_id': c.json().get('id'), 'access_token': token}
            )
            d     = p.json()
            label = 'Reel published' if is_video else 'Photo published'
            return {
                'success': p.status_code == 200,
                'post_id': d.get('id'),
                'message': label,
                'error':   d.get('error', {}).get('message') if p.status_code != 200 else None,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # YouTube
    # ------------------------------------------------------------------

    def _handle_youtube(self, caption, video_url):
        yt_token = self.tokens.get('youtube_token')
        if not yt_token or not video_url:
            return {
                'success':     True,
                'message':     'YouTube description ready — connect YouTube in Settings to auto-upload',
                'description': caption,
                'video_url':   video_url or 'No video URL provided',
                'note':        'Full YouTube auto-upload requires YouTube Data API v3 OAuth',
            }
        try:
            client = YouTubeClient(user_id=self.user_id)
            title  = caption.split('\n')[0][:100]
            result = client.upload_video(
                title       = title,
                description = caption,
                video_url   = video_url,
                tags        = ['food', 'local', 'update'],
                privacy     = 'public',
            )
            if result.get('id'):
                return {'success': True, 'message': 'YouTube video uploaded', 'video_id': result['id']}
            return {'success': False, 'error': result.get('error', 'Upload failed'), 'raw': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # YouTube Shorts (reuses YouTubeClient, adds #Shorts tag)
    # ------------------------------------------------------------------

    def _handle_youtube_shorts(self, caption, video_url):
        yt_token = self.tokens.get('youtube_token')
        if not yt_token or not video_url:
            return {
                'success':     True,
                'message':     'YouTube Shorts description ready — connect YouTube in Settings to auto-upload',
                'description': caption,
                'note':        '#Shorts tag will be added automatically on upload',
            }
        try:
            client = YouTubeClient(user_id=self.user_id)
            title  = caption.split('\n')[0][:100]
            result = client.upload_video(
                title       = title,
                description = caption,
                video_url   = video_url,
                tags        = ['Shorts', 'food', 'local'],
                privacy     = 'public',
            )
            if result.get('id'):
                return {'success': True, 'message': 'YouTube Short uploaded', 'video_id': result['id']}
            return {'success': False, 'error': result.get('error', 'Upload failed'), 'raw': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # TikTok
    # ------------------------------------------------------------------

    def _handle_tiktok(self, caption, video_url=None):
        tt_token = self.tokens.get('tiktok_token')
        if not tt_token:
            script = TikTokScriptGenerator.generate(caption)
            return {
                'success': True,
                'message': 'TikTok script ready — connect TikTok to auto-upload videos',
                'script':  script['full_script'],
            }
        if not video_url:
            script = TikTokScriptGenerator.generate(caption)
            return {
                'success': True,
                'message': 'TikTok script ready (no video URL provided for auto-upload)',
                'script':  script['full_script'],
            }
        try:
            client = TikTokClient(user_id=self.user_id)
            title  = caption.split('\n')[0][:150]
            result = client.upload_video(title=title, video_url=video_url)
            if result.get('publish_id'):
                return {
                    'success':    True,
                    'message':    'TikTok video upload initiated',
                    'publish_id': result['publish_id'],
                    'note':       'Use get_video_status(publish_id) to confirm PUBLISH_COMPLETE',
                }
            return {'success': False, 'error': result.get('error', 'Upload failed'), 'raw': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Google Business
    # ------------------------------------------------------------------

    def _publish_google_business(self, caption, image_url=None, link_url=None):
        token    = self.tokens.get('google_token')
        location = self.tokens.get('google_location_id')
        if not token or not location:
            return {'success': False, 'error': 'Google Business not connected'}
        try:
            client = GoogleBusinessClient(location_id=location, user_id=self.user_id)
            result = client.create_post(
                text           = caption,
                image_url      = image_url,
                call_to_action = 'LEARN_MORE' if link_url else None,
                cta_url        = link_url,
            )
            if result.get('name'):
                return {'success': True, 'post_id': result['name'], 'message': 'Posted to Google Business'}
            return {
                'success': False,
                'error':   result.get('error', {}).get('message', 'Unknown error'),
                'raw':     result,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # LinkedIn (stub — OAuth client built in Phase 3)
    # ------------------------------------------------------------------

    def _publish_linkedin(self, caption, image_url=None, link_url=None):
        token = self.tokens.get('linkedin_token')
        if not token:
            return {'success': False, 'error': 'LinkedIn not connected — connect in Settings'}
        # Full LinkedIn client coming in Phase 3
        return {'success': False, 'error': 'LinkedIn publishing not yet implemented — coming soon'}

    # ------------------------------------------------------------------
    # Twitter / X (stub — OAuth client built in Phase 4)
    # ------------------------------------------------------------------

    def _publish_twitter(self, caption, image_url=None):
        token = self.tokens.get('twitter_token')
        if not token:
            return {'success': False, 'error': 'Twitter / X not connected — connect in Settings'}
        # Full Twitter client coming in Phase 4
        return {'success': False, 'error': 'Twitter publishing not yet implemented — coming soon'}

    # ------------------------------------------------------------------
    # Pinterest (stub — OAuth client built in Phase 5)
    # ------------------------------------------------------------------

    def _publish_pinterest(self, caption, image_url=None, link_url=None):
        token = self.tokens.get('pinterest_token')
        if not token:
            return {'success': False, 'error': 'Pinterest not connected — connect in Settings'}
        # Full Pinterest client coming in Phase 5
        return {'success': False, 'error': 'Pinterest publishing not yet implemented — coming soon'}

    # ------------------------------------------------------------------
    # Website banner
    # ------------------------------------------------------------------

    def _update_website(self, caption, image_url=None, link_url=None, web_data=None):
        try:
            data = {
                'message':  caption.split('\n')[0][:120],
                'full':     caption,
                'image':    image_url or '',
                'link':     link_url  or '',
                'active':   True,
                'updated':  datetime.now().isoformat(),
                'specials': (web_data or {}).get('specials', ''),
                'hours':    (web_data or {}).get('hours',    ''),
                'location': (web_data or {}).get('location', ''),
            }
            path = os.path.join(os.path.dirname(__file__), '..', 'static', 'banner.json')
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return {'success': True, 'message': 'Website banner + sections updated', 'data': data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
