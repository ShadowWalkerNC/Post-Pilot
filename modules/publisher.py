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

# Twitter hard character limit
TWITTER_MAX_CHARS = 280


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
    # YouTube Shorts
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
        return {'success': False, 'error': 'LinkedIn publishing not yet implemented — coming soon'}

    # ------------------------------------------------------------------
    # Twitter / X
    # ------------------------------------------------------------------

    def _publish_twitter(self, caption, image_url=None):
        token = self.tokens.get('twitter_token')
        if not token:
            return {'success': False, 'error': 'Twitter / X not connected — connect in Settings'}

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json',
        }

        # Enforce 280-char hard limit
        tweet_text = caption if len(caption) <= TWITTER_MAX_CHARS else caption[:277] + '…'

        try:
            media_id = None
            if image_url:
                # Upload image via v1.1 media/upload (INIT + APPEND + FINALIZE)
                img_resp = requests.get(image_url, timeout=15)
                img_resp.raise_for_status()
                media_bytes  = img_resp.content
                total_bytes  = len(media_bytes)
                media_type   = img_resp.headers.get('Content-Type', 'image/jpeg')

                # INIT
                init = requests.post(
                    'https://upload.twitter.com/1.1/media/upload.json',
                    headers={'Authorization': f'Bearer {token}'},
                    data={
                        'command':      'INIT',
                        'total_bytes':  total_bytes,
                        'media_type':   media_type,
                        'media_category': 'tweet_image',
                    },
                    timeout=10,
                ).json()
                media_id = init.get('media_id_string')
                if not media_id:
                    return {'success': False, 'error': f'Twitter media INIT failed: {init}'}

                # APPEND
                requests.post(
                    'https://upload.twitter.com/1.1/media/upload.json',
                    headers={'Authorization': f'Bearer {token}'},
                    data={'command': 'APPEND', 'media_id': media_id, 'segment_index': 0},
                    files={'media': media_bytes},
                    timeout=30,
                )

                # FINALIZE
                fin = requests.post(
                    'https://upload.twitter.com/1.1/media/upload.json',
                    headers={'Authorization': f'Bearer {token}'},
                    data={'command': 'FINALIZE', 'media_id': media_id},
                    timeout=10,
                ).json()
                if fin.get('error'):
                    return {'success': False, 'error': f'Twitter media FINALIZE failed: {fin["error"]}'}

            # Post the tweet
            payload = {'text': tweet_text}
            if media_id:
                payload['media'] = {'media_ids': [media_id]}

            r = requests.post(
                'https://api.twitter.com/2/tweets',
                json=payload,
                headers=headers,
                timeout=10,
            )
            d = r.json()
            if r.status_code in (200, 201):
                tweet_id = d.get('data', {}).get('id')
                username = self.tokens.get('twitter_username', '')
                return {
                    'success':  True,
                    'message':  'Tweet posted',
                    'tweet_id': tweet_id,
                    'url':      f'https://twitter.com/{username}/status/{tweet_id}' if username else None,
                }
            return {
                'success': False,
                'error':   d.get('detail') or d.get('title') or 'Tweet failed',
                'raw':     d,
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------
    # Pinterest (stub — OAuth client built in Phase 5)
    # ------------------------------------------------------------------

    def _publish_pinterest(self, caption, image_url=None, link_url=None):
        token = self.tokens.get('pinterest_token')
        if not token:
            return {'success': False, 'error': 'Pinterest not connected — connect in Settings'}
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
