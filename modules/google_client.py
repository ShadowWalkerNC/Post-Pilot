"""
google_client.py — Google Business Profile + YouTube API Client (Phase 4 Session 7)

Provides two focused clients:

  GoogleBusinessClient
    ─ create_post()            — publish a GMB update (text, event, offer)
    ─ update_hours()           — push new hours to the listing
    ─ update_location_note()   — set "where we are today" on the listing description
    ─ update_special()         — post a OFFER type update with title + coupon
    ─ delete_post()            — remove a published GMB post
    ─ get_posts()              — list recent local posts
    ─ get_location_info()      — fetch current listing details
    ─ check_verification()     — returns True if location is verified

  YouTubeClient
    ─ upload_video()           — upload MP4 from URL or local path
    ─ create_channel_post()    — community / channel post (text + optional image)
    ─ get_channel_stats()      — subscribers, views, video count
    ─ get_video_analytics()    — views, likes, comments for a specific video

Both classes call auth_manager.get_valid_google_token() before every request
so tokens are always auto-refreshed without caller intervention.
"""

import os
import logging
import requests
import tempfile
from datetime import datetime
from typing import Optional

from modules.auth_manager import get_valid_google_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API Base URLs
# ---------------------------------------------------------------------------
_GMB_ACCT  = 'https://mybusinessaccountmanagement.googleapis.com/v1'
_GMB_INFO  = 'https://mybusinessbusinessinformation.googleapis.com/v1'
_GMB_POST  = 'https://mybusiness.googleapis.com/v4'
_YT_BASE   = 'https://www.googleapis.com/youtube/v3'
_YT_UPLOAD = 'https://www.googleapis.com/upload/youtube/v3'


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------
def _auth_headers(token: str) -> dict:
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


# ===========================================================================
# Google Business Profile Client
# ===========================================================================
class GoogleBusinessClient:
    """
    All interactions with the Google Business Profile (GMB) API.
    Instantiate with a location_id of the form
    'accounts/{account_id}/locations/{location_id}'.
    Pass user_id to support multi-user mode; defaults to 'default'.
    """

    def __init__(self, location_id: str, user_id: str = 'default'):
        self.location_id = location_id
        self.user_id     = user_id

    # ─── Internal: always fetch a fresh / auto-refreshed token ────────────
    def _token(self) -> Optional[str]:
        t = get_valid_google_token(self.user_id)
        if not t:
            logger.error('GoogleBusinessClient: no valid token for user=%s', self.user_id)
        return t

    # ─── Create a local post ───────────────────────────────────────────
    def create_post(
        self,
        text: str,
        post_type: str = 'STANDARD',
        image_url: Optional[str] = None,
        call_to_action: Optional[str] = None,
        cta_url: Optional[str] = None,
    ) -> dict:
        """
        Publish a Google Business update.

        Args:
            text:           Post body (max 1500 chars).
            post_type:      'STANDARD' | 'EVENT' | 'OFFER' | 'PRODUCT'
            image_url:      Public URL of an image to attach.
            call_to_action: CTA button type: 'LEARN_MORE' | 'ORDER' | 'BUY' |
                            'SIGN_UP' | 'CALL' | 'BOOK' | 'GET_OFFER'
            cta_url:        URL the CTA button links to.

        Returns:
            GMB API response dict.  Contains 'name' on success.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        body: dict = {
            'languageCode': 'en-US',
            'summary':      text[:1500],
            'topicType':    post_type,
        }

        if image_url:
            body['media'] = [{'mediaFormat': 'PHOTO', 'sourceUrl': image_url}]

        if call_to_action and cta_url:
            body['callToAction'] = {
                'actionType': call_to_action,
                'url':        cta_url,
            }

        resp = requests.post(
            f'{_GMB_POST}/{self.location_id}/localPosts',
            headers=_auth_headers(token),
            json=body,
        )
        result = resp.json()
        if resp.status_code == 200:
            logger.info('GMB post created: %s', result.get('name'))
        else:
            logger.error('GMB create_post failed %s: %s', resp.status_code, result)
        return result

    # ─── Update hours ─────────────────────────────────────────────────
    def update_hours(self, periods: list[dict]) -> dict:
        """
        Update regular business hours on the listing.

        Args:
            periods: List of period dicts, each with:
                {
                  'openDay':   'MONDAY',   # MONDAY – SUNDAY
                  'openTime':  {'hours': 11, 'minutes': 0},
                  'closeDay':  'MONDAY',
                  'closeTime': {'hours': 20, 'minutes': 0},
                }

        Returns:
            Updated location object from GMB API.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.patch(
            f'{_GMB_INFO}/{self.location_id}',
            headers=_auth_headers(token),
            params={'updateMask': 'regularHours'},
            json={'regularHours': {'periods': periods}},
        )
        result = resp.json()
        if resp.status_code == 200:
            logger.info('GMB hours updated for location=%s', self.location_id)
        else:
            logger.error('GMB update_hours failed %s: %s', resp.status_code, result)
        return result

    # ─── Update "where we are today" description note ────────────────────
    def update_location_note(self, note: str) -> dict:
        """
        Patch the location description with a short "today's location" note.
        For food trucks / pop-ups: "We're at 5th & Main today 🚚"

        Args:
            note: Up to 750 characters.

        Returns:
            Updated location object.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.patch(
            f'{_GMB_INFO}/{self.location_id}',
            headers=_auth_headers(token),
            params={'updateMask': 'profile.description'},
            json={'profile': {'description': note[:750]}},
        )
        result = resp.json()
        if resp.status_code == 200:
            logger.info('GMB location note updated')
        else:
            logger.error('GMB update_location_note failed %s: %s', resp.status_code, result)
        return result

    # ─── Post a special / offer ──────────────────────────────────────────
    def update_special(
        self,
        title: str,
        description: str,
        coupon_code: Optional[str] = None,
        redeem_url: Optional[str] = None,
        image_url: Optional[str] = None,
        valid_hours: int = 24,
    ) -> dict:
        """
        Post an OFFER-type update (today's special, coupon, etc.).

        Args:
            title:       Short headline, e.g. "BBQ Brisket Tacos — $12 Today Only"
            description: Body text.
            coupon_code: Optional coupon string shown on the post.
            redeem_url:  Optional URL to redeem / order online.
            image_url:   Optional photo URL.
            valid_hours: How many hours the offer is valid (default 24).

        Returns:
            GMB API response dict.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        now       = datetime.utcnow()
        end_time  = datetime(now.year, now.month, now.day, 23, 59, 59)

        body: dict = {
            'languageCode': 'en-US',
            'summary':      description[:1500],
            'topicType':    'OFFER',
            'offer': {
                'couponCode':        coupon_code or '',
                'redeemOnlineUrl':   redeem_url  or '',
                'termsConditions':   '',
            },
            'event': {
                'title':    title[:58],  # GMB title max 58 chars
                'schedule': {
                    'startDate': {'year': now.year,      'month': now.month,      'day': now.day},
                    'startTime': {'hours': now.hour,     'minutes': now.minute},
                    'endDate':   {'year': end_time.year, 'month': end_time.month, 'day': end_time.day},
                    'endTime':   {'hours': 23,           'minutes': 59},
                },
            },
        }

        if image_url:
            body['media'] = [{'mediaFormat': 'PHOTO', 'sourceUrl': image_url}]

        resp = requests.post(
            f'{_GMB_POST}/{self.location_id}/localPosts',
            headers=_auth_headers(token),
            json=body,
        )
        result = resp.json()
        if resp.status_code == 200:
            logger.info('GMB special posted: %s', title)
        else:
            logger.error('GMB update_special failed %s: %s', resp.status_code, result)
        return result

    # ─── Delete a post ─────────────────────────────────────────────────
    def delete_post(self, post_name: str) -> dict:
        """
        Delete a previously published local post.

        Args:
            post_name: The 'name' field returned by create_post(),
                       e.g. 'accounts/123/locations/456/localPosts/789'

        Returns:
            Empty dict on success, error dict on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.delete(
            f'{_GMB_POST}/{post_name}',
            headers=_auth_headers(token),
        )
        if resp.status_code == 200:
            logger.info('GMB post deleted: %s', post_name)
            return {}
        result = resp.json()
        logger.error('GMB delete_post failed %s: %s', resp.status_code, result)
        return result

    # ─── List recent posts ──────────────────────────────────────────────
    def get_posts(self, page_size: int = 10) -> dict:
        """
        Fetch recent local posts for this location.

        Returns:
            Dict with 'localPosts' list.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.get(
            f'{_GMB_POST}/{self.location_id}/localPosts',
            headers=_auth_headers(token),
            params={'pageSize': page_size},
        )
        return resp.json()

    # ─── Get location info ─────────────────────────────────────────────
    def get_location_info(self, read_mask: str = 'name,title,regularHours,profile') -> dict:
        """
        Fetch current listing details.

        Args:
            read_mask: Comma-separated fields to return.

        Returns:
            Location object from GMB API.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.get(
            f'{_GMB_INFO}/{self.location_id}',
            headers=_auth_headers(token),
            params={'readMask': read_mask},
        )
        return resp.json()

    # ─── Check verification status ──────────────────────────────────────
    def check_verification(self) -> bool:
        """
        Returns True if the location is verified, False otherwise.
        Used by the dashboard to show a yellow 'pending' indicator.
        """
        token = self._token()
        if not token:
            return False
        resp = requests.get(
            f'{_GMB_INFO}/{self.location_id}/verifications',
            headers=_auth_headers(token),
        )
        data         = resp.json()
        verifications = data.get('verifications', [])
        return any(v.get('state') == 'COMPLETED' for v in verifications)


# ===========================================================================
# YouTube Client
# ===========================================================================
class YouTubeClient:
    """
    Handles YouTube Data API v3 interactions.
    Pass user_id to support multi-user mode; defaults to 'default'.
    """

    def __init__(self, user_id: str = 'default'):
        self.user_id = user_id

    def _token(self) -> Optional[str]:
        t = get_valid_google_token(self.user_id)
        if not t:
            logger.error('YouTubeClient: no valid token for user=%s', self.user_id)
        return t

    # ─── Upload video ──────────────────────────────────────────────────
    def upload_video(
        self,
        title: str,
        description: str,
        video_url: Optional[str] = None,
        local_path: Optional[str] = None,
        tags: Optional[list] = None,
        privacy: str = 'public',
        category_id: str = '22',   # 22 = People & Blogs
    ) -> dict:
        """
        Upload a video to YouTube.

        Provide either video_url (remote MP4) or local_path (local file).
        If video_url is given, the file is downloaded to a temp directory first.

        Args:
            title:        Video title (max 100 chars).
            description:  Video description.
            video_url:    Public URL of an MP4 to download and upload.
            local_path:   Path to a local MP4 file.
            tags:         List of tag strings.
            privacy:      'public' | 'unlisted' | 'private'
            category_id:  YouTube category ID string.

        Returns:
            YouTube API response dict.  Contains 'id' (video ID) on success.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        # Resolve video source
        tmp_file = None
        if video_url and not local_path:
            logger.info('YouTubeClient: downloading video from %s', video_url)
            r = requests.get(video_url, stream=True, timeout=120)
            if r.status_code != 200:
                return {'error': f'Failed to download video: HTTP {r.status_code}'}
            tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            for chunk in r.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp.close()
            local_path = tmp.name
            tmp_file   = tmp.name

        if not local_path:
            return {'error': 'Provide either video_url or local_path'}

        metadata = {
            'snippet': {
                'title':       title[:100],
                'description': description,
                'tags':        tags or [],
                'categoryId':  category_id,
            },
            'status': {
                'privacyStatus':           privacy,
                'selfDeclaredMadeForKids': False,
            },
        }

        try:
            with open(local_path, 'rb') as video_file:
                resp = requests.post(
                    f'{_YT_UPLOAD}/videos',
                    headers={'Authorization': f'Bearer {token}'},
                    params={
                        'uploadType': 'multipart',
                        'part':       'snippet,status',
                    },
                    files={
                        'metadata': (None, str(metadata), 'application/json'),
                        'video':    ('video.mp4', video_file, 'video/mp4'),
                    },
                )
        finally:
            if tmp_file:
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass

        result = resp.json()
        if resp.status_code in (200, 201):
            logger.info('YouTube video uploaded: id=%s', result.get('id'))
        else:
            logger.error('YouTube upload_video failed %s: %s', resp.status_code, result)
        return result

    # ─── Create channel / community post ───────────────────────────────────
    def create_channel_post(
        self,
        text: str,
        image_url: Optional[str] = None,
    ) -> dict:
        """
        Publish a YouTube Community post (channel update / announcement).
        Requires the channel to have the Community tab enabled
        (typically 500+ subscribers or manually enabled).

        Args:
            text:       Post body text.
            image_url:  Optional image URL to attach.

        Returns:
            YouTube API response dict.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        body: dict = {
            'snippet': {
                'textOriginal': text,
            }
        }

        if image_url:
            body['snippet']['backgroundImage'] = {'url': image_url}

        resp = requests.post(
            f'{_YT_BASE}/communityPosts',
            headers=_auth_headers(token),
            params={'part': 'snippet'},
            json=body,
        )
        result = resp.json()
        if resp.status_code in (200, 201):
            logger.info('YouTube community post created')
        else:
            logger.error('YouTube create_channel_post failed %s: %s', resp.status_code, result)
        return result

    # ─── Get channel stats ──────────────────────────────────────────────
    def get_channel_stats(self) -> dict:
        """
        Fetch subscriber count, total views, and video count for the
        authenticated user's channel.

        Returns:
            Dict with 'subscribers', 'total_views', 'video_count',
            or 'error' on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.get(
            f'{_YT_BASE}/channels',
            headers=_auth_headers(token),
            params={
                'part': 'statistics',
                'mine': 'true',
            },
        )
        data  = resp.json()
        items = data.get('items', [])
        if not items:
            return {'error': 'No channel found', 'raw': data}

        stats = items[0].get('statistics', {})
        return {
            'subscribers':  int(stats.get('subscriberCount', 0)),
            'total_views':  int(stats.get('viewCount', 0)),
            'video_count':  int(stats.get('videoCount', 0)),
        }

    # ─── Get video analytics ────────────────────────────────────────────
    def get_video_analytics(self, video_id: str) -> dict:
        """
        Fetch view count, like count, and comment count for a specific video.

        Args:
            video_id: YouTube video ID string (e.g. 'dQw4w9WgXcQ').

        Returns:
            Dict with 'views', 'likes', 'comments', or 'error' on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid Google token'}

        resp = requests.get(
            f'{_YT_BASE}/videos',
            headers=_auth_headers(token),
            params={
                'part': 'statistics',
                'id':   video_id,
            },
        )
        data  = resp.json()
        items = data.get('items', [])
        if not items:
            return {'error': f'Video {video_id} not found', 'raw': data}

        stats = items[0].get('statistics', {})
        return {
            'views':    int(stats.get('viewCount',    0)),
            'likes':    int(stats.get('likeCount',    0)),
            'comments': int(stats.get('commentCount', 0)),
        }
