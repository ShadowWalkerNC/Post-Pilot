"""
PostPilot Pro — Universal Publisher
Smart routing: videos → video platforms, text → text platforms,
images → image platforms. Write once, push everywhere.
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, Optional


# Smart routing rules (mirrors frontend ROUTING constant)
ROUTING_RULES = {
    'text':   ['fb', 'gb', 'web'],
    'image':  ['fb', 'ig', 'gb', 'web'],
    'video':  ['fb', 'ig', 'yt', 'tt', 'web'],
    'promo':  ['fb', 'ig', 'tt', 'gb', 'web'],
    'update': ['fb', 'gb', 'web'],
}


class UniversalPublisher:

    def __init__(self, tokens: Dict):
        self.tokens = tokens

    def push_all(self, caption: str, content_type: str = 'text',
                 image_url: Optional[str] = None, video_url: Optional[str] = None,
                 link_url: Optional[str] = None, platforms: Optional[Dict] = None,
                 schedule_time: Optional[str] = None, web_data: Optional[Dict] = None) -> Dict:

        # Auto-select platforms if not provided
        if platforms is None:
            auto = ROUTING_RULES.get(content_type, ['fb', 'web'])
            platforms = {p: p in auto for p in ['fb', 'ig', 'yt', 'tt', 'gb', 'web']}

        results = {}

        if platforms.get('fb'):
            results['fb'] = self._publish_facebook(caption, image_url, video_url, schedule_time)

        if platforms.get('ig'):
            if image_url or video_url:
                results['ig'] = self._publish_instagram(caption, image_url or video_url, schedule_time)
            else:
                results['ig'] = {'success': False, 'error': 'Instagram requires an image or video URL'}

        if platforms.get('yt'):
            results['yt'] = self._handle_youtube(caption, video_url)

        if platforms.get('tt'):
            results['tt'] = self._generate_tiktok(caption, video_url)

        if platforms.get('gb'):
            results['gb'] = self._publish_google_business(caption, image_url, link_url)

        if platforms.get('web'):
            results['web'] = self._update_website(caption, image_url, link_url, web_data)

        return results

    # ── Facebook ───────────────────────────────────────────────────

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
            return {'success': r.status_code == 200, 'post_id': d.get('id'), 'message': label,
                    'error': d.get('error', {}).get('message') if r.status_code != 200 else None}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── Instagram ─────────────────────────────────────────────────

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
            d = p.json()
            label = 'Reel published' if is_video else 'Photo published'
            return {'success': p.status_code == 200, 'post_id': d.get('id'), 'message': label,
                    'error': d.get('error', {}).get('message') if p.status_code != 200 else None}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── YouTube ─────────────────────────────────────────────────────

    def _handle_youtube(self, caption, video_url):
        yt_token = self.tokens.get('youtube_token')
        if not yt_token:
            # Return the script + link even without upload credentials
            return {
                'success': True,
                'message': 'YouTube description ready — connect YouTube in Settings to auto-upload',
                'description': caption,
                'video_url': video_url or 'No video URL provided',
                'note': 'Full YouTube auto-upload requires YouTube Data API v3 OAuth'
            }
        # Full YouTube upload via resumable upload API
        try:
            title = caption.split('\n')[0][:100]
            meta  = {'snippet': {'title': title, 'description': caption, 'tags': ['food','local','update']},
                     'status':  {'privacyStatus': 'public'}}
            r = requests.post(
                'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                json=meta,
                headers={'Authorization': f'Bearer {yt_token}', 'Content-Type': 'application/json',
                         'X-Upload-Content-Type': 'video/*'}
            )
            upload_url = r.headers.get('Location')
            if not upload_url:
                return {'success': False, 'error': 'Could not get YouTube upload URL'}
            return {'success': True, 'message': 'YouTube upload initiated', 'upload_url': upload_url}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── TikTok ──────────────────────────────────────────────────────

    def _generate_tiktok(self, caption, video_url=None):
        tt_token = self.tokens.get('tiktok_token')
        first    = caption.split('\n')[0]
        script   = (
            f"🎵 TIKTOK SCRIPT\n\n"
            f"[HOOK — first 3 sec]\n\"{first}\"\n\n"
            f"[BODY]\n{caption[:300]}\n\n"
            f"[CTA]\n\"Follow us — link in bio!\"\n\n"
            f"#foodtok #fyp #viral"
        )
        if tt_token and video_url:
            # TikTok Content Posting API (requires approved app)
            try:
                r = requests.post(
                    'https://open.tiktokapis.com/v2/post/publish/video/init/',
                    json={'post_info': {'title': first[:150], 'privacy_level': 'PUBLIC_TO_EVERYONE',
                                        'disable_duet': False, 'disable_stitch': False},
                          'source_info': {'source': 'PULL_FROM_URL', 'video_url': video_url}},
                    headers={'Authorization': f'Bearer {tt_token}', 'Content-Type': 'application/json; charset=UTF-8'}
                )
                d = r.json()
                if r.status_code == 200:
                    return {'success': True, 'message': 'TikTok video uploaded!', 'publish_id': d.get('data', {}).get('publish_id')}
            except Exception as e:
                pass  # Fall through to script
        return {'success': True, 'message': 'TikTok script ready — connect TikTok to auto-upload videos', 'script': script}

    # ── Google Business ────────────────────────────────────────────

    def _publish_google_business(self, caption, image_url=None, link_url=None):
        token    = self.tokens.get('google_token')
        location = self.tokens.get('google_location_id')
        if not token or not location:
            return {'success': False, 'error': 'Google Business not connected'}
        try:
            clean = caption.encode('ascii', 'ignore').decode()[:1500]
            body  = {'languageCode': 'en', 'summary': clean, 'topicType': 'STANDARD'}
            if link_url:
                body['callToAction'] = {'actionType': 'LEARN_MORE', 'url': link_url}
            if image_url:
                body['media'] = [{'mediaFormat': 'PHOTO', 'sourceUrl': image_url}]
            r = requests.post(
                f'https://mybusiness.googleapis.com/v4/{location}/localPosts',
                json=body,
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            )
            d = r.json()
            return {'success': r.status_code == 200, 'post_id': d.get('name'), 'message': 'Posted to Google Business',
                    'error': d.get('error', {}).get('message') if r.status_code != 200 else None}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ── Website (banner + sections) ─────────────────────────────────

    def _update_website(self, caption, image_url=None, link_url=None, web_data=None):
        try:
            data = {
                'message':  caption.split('\n')[0][:120],
                'full':     caption,
                'image':    image_url or '',
                'link':     link_url or '',
                'active':   True,
                'updated':  datetime.now().isoformat(),
                'specials': (web_data or {}).get('specials', ''),
                'hours':    (web_data or {}).get('hours', ''),
                'location': (web_data or {}).get('location', ''),
            }
            path = os.path.join(os.path.dirname(__file__), '..', 'static', 'banner.json')
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return {'success': True, 'message': 'Website banner + sections updated', 'data': data}
        except Exception as e:
            return {'success': False, 'error': str(e)}
