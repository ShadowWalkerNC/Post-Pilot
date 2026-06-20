"""
tiktok_client.py — TikTok Content Posting API v2 Client (Phase 4 Session 8)

Provides two classes:

  TikTokClient
    Full integration with TikTok Content Posting API v2.
    Requires an approved TikTok developer app with video.publish scope.

    ─ upload_video()         — init a PULL_FROM_URL or FILE_UPLOAD post
    ─ get_video_status()     — poll publish_id until PUBLISH_COMPLETE
    ─ query_creator_info()   — fetch max video duration, privacy options, duet/stitch settings
    ─ get_video_analytics()  — views, likes, comments, shares for a video
    ─ delete_video()         — delete a published video by video_id
    ─ generate_script()      — format a ready-to-read on-camera script from any caption

  TikTokScriptGenerator
    Zero-API fallback — works without app approval or any token.
    ─ generate()             — returns a structured hook / body / CTA script dict
    ─ format_text()          — returns a plain printable script string

Token lifecycle:
  TikTokClient calls auth_manager.get_valid_tiktok_token() before every
  request, which auto-refreshes the 24-hour TikTok access token transparently.

App approval note:
  TikTok requires formal Content Posting API approval (5–10 business days).
  Until approval lands, use TikTokScriptGenerator as the fallback path.
  publisher.py switches automatically based on token availability.
"""

import os
import time
import logging
import requests
import tempfile
from typing import Optional

from modules.auth_manager import load_token, save_token, refresh_tiktok_token

logger = logging.getLogger(__name__)

_TT_BASE   = 'https://open.tiktokapis.com/v2'
_POLL_MAX  = 20    # max status-poll attempts
_POLL_WAIT = 3     # seconds between polls


# ---------------------------------------------------------------------------
# Token helper — mirrors get_valid_google_token pattern from auth_manager
# ---------------------------------------------------------------------------
def get_valid_tiktok_token(user_id: str = 'default') -> Optional[str]:
    """
    Return a valid TikTok access token, auto-refreshing the 24-hour token
    if it has expired.  Returns None if no token is stored at all.
    """
    from modules.auth_manager import is_token_expired
    status = is_token_expired('tiktok', user_id, warn_days=0)
    if status == 'missing':
        return None
    if status == 'expired':
        return refresh_tiktok_token(user_id)
    token = load_token('tiktok', user_id)
    return token['access_token'] if token else None


# ===========================================================================
# TikTok API Client
# ===========================================================================
class TikTokClient:
    """
    TikTok Content Posting API v2 client.
    All methods silently auto-refresh the token via auth_manager.
    """

    def __init__(self, user_id: str = 'default'):
        self.user_id = user_id

    def _token(self) -> Optional[str]:
        t = get_valid_tiktok_token(self.user_id)
        if not t:
            logger.error('TikTokClient: no valid token for user=%s', self.user_id)
        return t

    def _headers(self, token: str) -> dict:
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type':  'application/json; charset=UTF-8',
        }

    # ─── Creator info ────────────────────────────────────────────────
    def query_creator_info(self) -> dict:
        """
        Fetch the authenticated creator's posting constraints:
        max video duration, allowed privacy levels, duet/stitch settings.
        Must call this before upload_video() to respect per-account limits.

        Returns:
            Dict with keys: max_video_post_duration_sec, privacy_level_options,
            duet_disabled, stitch_disabled, comment_disabled.
            Or {'error': ...} on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid TikTok token'}

        resp = requests.post(
            f'{_TT_BASE}/post/publish/creator_info/query/',
            headers=self._headers(token),
            json={},
        )
        data = resp.json()
        if resp.status_code != 200:
            logger.error('TikTok query_creator_info failed %s: %s', resp.status_code, data)
            return {'error': data}

        d = data.get('data', {})
        return {
            'max_video_post_duration_sec': d.get('max_video_post_duration_sec', 60),
            'privacy_level_options':       d.get('privacy_level_options', ['PUBLIC_TO_EVERYONE']),
            'duet_disabled':               d.get('duet_disabled', False),
            'stitch_disabled':             d.get('stitch_disabled', False),
            'comment_disabled':            d.get('comment_disabled', False),
        }

    # ─── Upload video (PULL_FROM_URL or FILE_UPLOAD) ─────────────────────
    def upload_video(
        self,
        title: str,
        video_url: Optional[str] = None,
        local_path: Optional[str] = None,
        privacy: str = 'PUBLIC_TO_EVERYONE',
        disable_duet: bool = False,
        disable_stitch: bool = False,
        disable_comment: bool = False,
        auto_add_music: bool = False,
    ) -> dict:
        """
        Publish a video to TikTok via the Content Posting API.

        Provide either video_url (remote MP4, TikTok pulls it directly) or
        local_path (file upload mode — uses chunked FILE_UPLOAD source type).

        Args:
            title:           Caption / description (max 2200 chars for TikTok).
            video_url:       Public HTTPS URL to an MP4. TikTok fetches it directly.
            local_path:      Path to a local MP4 to upload via FILE_UPLOAD.
            privacy:         'PUBLIC_TO_EVERYONE' | 'MUTUAL_FOLLOW_FRIENDS' |
                             'FOLLOWER_OF_CREATOR' | 'SELF_ONLY'
            disable_duet:    Prevent duets on this video.
            disable_stitch:  Prevent stitches on this video.
            disable_comment: Disable comments.
            auto_add_music:  Let TikTok auto-add background music.

        Returns:
            Dict with 'publish_id' on success (use get_video_status() to poll).
            Or {'error': ...} on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid TikTok token'}

        if not video_url and not local_path:
            return {'error': 'Provide either video_url or local_path'}

        post_info = {
            'title':           title[:2200],
            'privacy_level':   privacy,
            'disable_duet':    disable_duet,
            'disable_stitch':  disable_stitch,
            'disable_comment': disable_comment,
            'auto_add_music':  auto_add_music,
        }

        # ── PULL_FROM_URL (preferred — TikTok fetches the video itself) ──────
        if video_url:
            payload = {
                'post_info':   post_info,
                'source_info': {
                    'source':    'PULL_FROM_URL',
                    'video_url': video_url,
                },
            }
            resp = requests.post(
                f'{_TT_BASE}/post/publish/video/init/',
                headers=self._headers(token),
                json=payload,
            )
            data = resp.json()
            if resp.status_code == 200:
                publish_id = data.get('data', {}).get('publish_id')
                logger.info('TikTok PULL_FROM_URL initiated: publish_id=%s', publish_id)
                return {'success': True, 'publish_id': publish_id, 'source': 'PULL_FROM_URL'}
            logger.error('TikTok upload (PULL_FROM_URL) failed %s: %s', resp.status_code, data)
            return {'error': data}

        # ── FILE_UPLOAD (local file, chunked) ──────────────────────────────
        file_size = os.path.getsize(local_path)
        chunk_size = 10 * 1024 * 1024  # 10 MB chunks

        # Step 1: Init upload
        init_payload = {
            'post_info':   post_info,
            'source_info': {
                'source':          'FILE_UPLOAD',
                'video_size':      file_size,
                'chunk_size':      chunk_size,
                'total_chunk_count': (file_size + chunk_size - 1) // chunk_size,
            },
        }
        init_resp = requests.post(
            f'{_TT_BASE}/post/publish/video/init/',
            headers=self._headers(token),
            json=init_payload,
        )
        init_data = init_resp.json()
        if init_resp.status_code != 200:
            logger.error('TikTok FILE_UPLOAD init failed %s: %s', init_resp.status_code, init_data)
            return {'error': init_data}

        upload_url = init_data.get('data', {}).get('upload_url')
        publish_id = init_data.get('data', {}).get('publish_id')

        if not upload_url:
            return {'error': 'No upload_url in TikTok init response', 'raw': init_data}

        # Step 2: Upload chunks
        try:
            with open(local_path, 'rb') as f:
                chunk_index  = 0
                bytes_sent   = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    chunk_end = bytes_sent + len(chunk) - 1
                    upload_headers = {
                        'Content-Type':  'video/mp4',
                        'Content-Range': f'bytes {bytes_sent}-{chunk_end}/{file_size}',
                    }
                    chunk_resp = requests.put(
                        upload_url,
                        headers=upload_headers,
                        data=chunk,
                    )
                    if chunk_resp.status_code not in (200, 206):
                        logger.error('TikTok chunk upload failed at chunk %d: %s',
                                     chunk_index, chunk_resp.status_code)
                        return {'error': f'Chunk {chunk_index} upload failed: {chunk_resp.status_code}'}
                    bytes_sent  += len(chunk)
                    chunk_index += 1
        except Exception as e:
            logger.error('TikTok FILE_UPLOAD error: %s', e)
            return {'error': str(e)}

        logger.info('TikTok FILE_UPLOAD complete: publish_id=%s', publish_id)
        return {'success': True, 'publish_id': publish_id, 'source': 'FILE_UPLOAD'}

    # ─── Poll publish status ────────────────────────────────────────────
    def get_video_status(self, publish_id: str, poll: bool = False) -> dict:
        """
        Query the publish status of a video upload.

        Args:
            publish_id: The ID returned by upload_video().
            poll:       If True, block and retry until PUBLISH_COMPLETE or
                        FAILED (up to _POLL_MAX * _POLL_WAIT seconds).

        Returns:
            Dict with 'status' key: 'PROCESSING_UPLOAD' | 'PUBLISH_COMPLETE' |
            'FAILED' | 'PUBLISH_COMPLETE'. Also includes 'video_id' when done.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid TikTok token'}

        for attempt in range(_POLL_MAX if poll else 1):
            resp = requests.post(
                f'{_TT_BASE}/post/publish/status/fetch/',
                headers=self._headers(token),
                json={'publish_id': publish_id},
            )
            data   = resp.json()
            status = data.get('data', {}).get('status', 'UNKNOWN')

            if status in ('PUBLISH_COMPLETE', 'FAILED') or not poll:
                video_id = data.get('data', {}).get('publicaly_available_post_id', [])
                return {
                    'status':     status,
                    'video_id':   video_id[0] if video_id else None,
                    'publish_id': publish_id,
                    'raw':        data,
                }

            logger.debug('TikTok status %s for publish_id=%s, attempt %d/%d',
                         status, publish_id, attempt + 1, _POLL_MAX)
            time.sleep(_POLL_WAIT)

        return {'status': 'TIMEOUT', 'publish_id': publish_id,
                'message': f'Status still processing after {_POLL_MAX * _POLL_WAIT}s'}

    # ─── Video analytics ─────────────────────────────────────────────────
    def get_video_analytics(
        self,
        video_ids: list[str],
        fields: Optional[list] = None,
    ) -> dict:
        """
        Fetch analytics for one or more TikTok videos.

        Args:
            video_ids: List of video ID strings (max 20 per request).
            fields:    Metrics to fetch. Defaults to the main engagement metrics.

        Returns:
            Dict with 'videos' list, each having: id, view_count, like_count,
            comment_count, share_count, reach, avg_watch_time.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid TikTok token'}

        default_fields = [
            'id', 'view_count', 'like_count', 'comment_count',
            'share_count', 'reach', 'average_time_watched',
        ]
        requested_fields = fields or default_fields

        resp = requests.post(
            f'{_TT_BASE}/video/query/',
            headers=self._headers(token),
            params={'fields': ','.join(requested_fields)},
            json={'filters': {'video_ids': video_ids[:20]}},
        )
        data  = resp.json()
        if resp.status_code != 200:
            logger.error('TikTok get_video_analytics failed %s: %s', resp.status_code, data)
            return {'error': data}

        videos = data.get('data', {}).get('videos', [])
        return {
            'videos': [
                {
                    'id':               v.get('id'),
                    'view_count':       v.get('view_count', 0),
                    'like_count':       v.get('like_count', 0),
                    'comment_count':    v.get('comment_count', 0),
                    'share_count':      v.get('share_count', 0),
                    'reach':            v.get('reach', 0),
                    'avg_watch_time':   v.get('average_time_watched', 0),
                }
                for v in videos
            ]
        }

    # ─── Delete video ──────────────────────────────────────────────────
    def delete_video(self, video_id: str) -> dict:
        """
        Delete a published TikTok video.

        Args:
            video_id: The TikTok video ID string.

        Returns:
            Empty dict on success, {'error': ...} on failure.
        """
        token = self._token()
        if not token:
            return {'error': 'No valid TikTok token'}

        resp = requests.post(
            f'{_TT_BASE}/video/delete/',
            headers=self._headers(token),
            json={'video_id': video_id},
        )
        data = resp.json()
        if resp.status_code == 200:
            logger.info('TikTok video deleted: video_id=%s', video_id)
            return {}
        logger.error('TikTok delete_video failed %s: %s', resp.status_code, data)
        return {'error': data}

    # ─── Generate on-camera script ───────────────────────────────────────
    def generate_script(
        self,
        caption: str,
        business_name: str = '',
        hashtags: Optional[list] = None,
    ) -> dict:
        """
        Format a ready-to-read on-camera TikTok script from any caption.
        Useful as a fallback when app approval is pending.

        Args:
            caption:       The main post caption.
            business_name: Optional business name for the hook.
            hashtags:      Optional list of hashtag strings (without #).

        Returns:
            Dict with: hook, body, cta, hashtags, full_script (formatted string).
        """
        return TikTokScriptGenerator.generate(
            caption       = caption,
            business_name = business_name,
            hashtags      = hashtags,
        )


# ===========================================================================
# TikTok Script Generator — zero-API fallback
# ===========================================================================
class TikTokScriptGenerator:
    """
    Generates structured on-camera TikTok scripts from any caption.
    No token or API approval required — works immediately.

    Used by publisher.py when:
      - TikTok app approval is still pending
      - No TikTok token is stored yet
      - Video content type is selected but no video_url is provided
    """

    DEFAULT_HASHTAGS = ['foodtok', 'fyp', 'viral', 'localfood', 'smallbusiness']

    @staticmethod
    def generate(
        caption: str,
        business_name: str = '',
        hashtags: Optional[list] = None,
    ) -> dict:
        """
        Build a structured script dict from a plain caption.

        Returns:
            {
              'hook':        First sentence — read in the first 3 seconds.
              'body':        Main content — expand on the hook.
              'cta':         Call-to-action — end of video.
              'hashtags':    Formatted hashtag string for the caption field.
              'full_script': Ready-to-copy formatted script string.
            }
        """
        lines    = [l.strip() for l in caption.strip().split('\n') if l.strip()]
        hook     = lines[0][:150] if lines else caption[:150]
        body     = ' '.join(lines[1:])[:400] if len(lines) > 1 else caption[:400]
        biz_part = f' at {business_name}' if business_name else ''
        cta      = f'Follow us{biz_part} for daily updates — link in bio!'
        tags     = hashtags or TikTokScriptGenerator.DEFAULT_HASHTAGS
        tag_str  = ' '.join(f'#{t.lstrip("#")}' for t in tags)

        full = (
            f"🎵 TIKTOK SCRIPT\n"
            f"{'=' * 40}\n\n"
            f"[HOOK — say this in the first 3 seconds]\n"
            f"\"{hook}\"\n\n"
            f"[BODY — expand for 15–30 seconds]\n"
            f"{body}\n\n"
            f"[CTA — end of video]\n"
            f"\"{cta}\"\n\n"
            f"[CAPTION + HASHTAGS]\n"
            f"{hook}\n\n"
            f"{tag_str}\n"
        )

        return {
            'hook':        hook,
            'body':        body,
            'cta':         cta,
            'hashtags':    tag_str,
            'full_script': full,
        }

    @staticmethod
    def format_text(script_dict: dict) -> str:
        """Return the full_script string from a generate() result."""
        return script_dict.get('full_script', '')
