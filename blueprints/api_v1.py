"""
blueprints/api_v1.py
Unified Headless REST API (/api/v1/*) for Post-Pilot.

Endpoints:
  GET  /api/v1/health                  -- Public health check
  GET  /api/v1/manifest                -- Machine-readable SRN manifest
  POST /api/v1/posts/draft             -- Create post draft
  POST /api/v1/posts/generate          -- AI caption generation & platform adaptations
  POST /api/v1/posts/dispatch          -- Multi-platform immediate publishing dispatch
  POST /api/v1/posts/schedule          -- Queue & schedule posts for specific timestamp
  GET  /api/v1/posts/history           -- Post history with pagination & status filters
  GET  /api/v1/specials                -- List specials
  POST /api/v1/specials                -- Create special
  GET  /api/v1/specials/<id>           -- Get single special
  PUT, PATCH /api/v1/specials/<id>     -- Update special (pending only)
  DELETE /api/v1/specials/<id>         -- Delete special
  POST /api/v1/specials/<id>/cancel    -- Cancel special
  GET  /api/v1/events                  -- List events
  POST /api/v1/events                  -- Create event
  GET  /api/v1/events/<id>             -- Get single event
  PUT, PATCH /api/v1/events/<id>       -- Update event (pending only)
  DELETE /api/v1/events/<id>           -- Delete event
  POST /api/v1/events/<id>/cancel      -- Cancel event
  GET  /api/v1/hours/overrides         -- List hours overrides
  POST /api/v1/hours/overrides         -- Create hours override
  GET  /api/v1/hours/overrides/<id>    -- Get single hours override
  PUT, PATCH /api/v1/hours/overrides/<id> -- Update hours override (pending only)
  DELETE /api/v1/hours/overrides/<id>  -- Delete hours override
  POST /api/v1/hours/overrides/<id>/cancel -- Cancel hours override
  GET, POST /api/v1/analytics/summary  -- Analytics summary (KPIs, charts, IG/Google)

Legacy Aliases:
  /v1/health, /v1/manifest, /v1/generate_post, /v1/publish_post,
  /v1/generate_and_publish, /v1/get_history, /v1/get_site_config, /v1/set_published,
  /v1/keys/create, /v1/keys, /v1/keys/revoke
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from functools import wraps
from typing import Optional

from flask import Blueprint, g, jsonify, request
from flask_login import current_user

from blueprints.utils import _get_tokens
from modules.database import get_db
from modules.plan_guard import check_platform_limit, check_post_limit
from modules.publisher import UniversalPublisher
from modules.user_manager import UserManager
from modules.validator import validate_post_input

api_v1_bp = Blueprint('api_v1', __name__)
logger = logging.getLogger(__name__)

APP_NAME = 'post-pilot'
APP_VERSION = '1.0.0'

CONTENT_TYPES_SPECIALS = ['daily_special', 'location', 'general']
EVENT_TYPES = ['event', 'happy_hour', 'pop_up', 'concert', 'market', 'general']
OVERRIDE_TYPES = ['closure', 'hours_change', 'holiday', 'general']
TONES = ['friendly', 'hype', 'urgent', 'funny', 'community']


# ---------------------------------------------------------------------------
# Standard JSON Response Envelopes
# ---------------------------------------------------------------------------

def api_success(data=None, status_code: int = 200, **kwargs):
    """
    Standard successful JSON response.
    Format: { "status": "success", "success": True, "data": ... }
    """
    payload = {
        'status': 'success',
        'success': True,
    }
    if data is not None:
        payload['data'] = data
    payload.update(kwargs)
    return jsonify(payload), status_code


def api_error(message: str, code: str = 'ERROR', status_code: int = 400, **kwargs):
    """
    Standard error JSON response.
    Format: { "status": "error", "success": False, "message": ..., "error": ..., "code": ... }
    """
    payload = {
        'status': 'error',
        'success': False,
        'message': message,
        'error': message,
        'code': code,
    }
    payload.update(kwargs)
    return jsonify(payload), status_code


# ---------------------------------------------------------------------------
# Auth Helper & Decorator
# ---------------------------------------------------------------------------

def _get_api_key_row(token: str) -> Optional[dict]:
    """Look up an API key row by token hash or raw key."""
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()

    try:
        row = db.execute(
            'SELECT * FROM api_keys WHERE (key_hash = ? OR key_value = ? OR key_hash = ? OR key_value = ?) LIMIT 1',
            (key_hash, token, token, key_hash),
        ).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass

    try:
        row = db.execute('SELECT * FROM api_keys WHERE key_hash = ? LIMIT 1', (key_hash,)).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass

    try:
        row = db.execute('SELECT * FROM api_keys WHERE key_value = ? LIMIT 1', (token,)).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass

    return None


def _get_srn_key() -> str:
    return os.environ.get('SRN_SECRET', '').strip()


def _resolve_scoped_user_id(requested=None) -> Optional[str]:
    """
    Resolve the user_id for a call.
    User API keys are always bound to key owner (prevents cross-tenant IDOR).
    SRN shared secret callers may pass explicit user_id.
    """
    if getattr(g, 'api_key_row', None) is not None:
        return str(g.api_user_id)
    if requested:
        return str(requested)
    if getattr(g, 'api_user_id', None) is not None:
        return str(g.api_user_id)
    if current_user.is_authenticated:
        return str(current_user.id)
    return None


def _get_user_and_tier(uid: str):
    user = UserManager.get_user(uid)
    tier = user.subscription_tier if user else 'starter'
    return user, tier


def require_api_key(f):
    """
    Decorator: validates Bearer token from Authorization header or session.
    Accepts:
      - A user-issued pp_live_xxx API key (checked against api_keys table)
      - The shared SRN_SECRET (for ShadowRealm / Sigil / microservice calls)
      - Authenticated Flask-Login session as fallback
    Sets g.api_user_id, g.api_caller, and g.api_key_row on success.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        caller = request.headers.get('X-SRN-App', 'unknown')

        token = ''
        if auth:
            parts = auth.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1].strip()
            else:
                token = auth.replace('Bearer ', '').replace('bearer ', '').strip()

        if not token:
            # Check if user has active session (for dashboard fallback)
            if current_user.is_authenticated:
                g.api_user_id = str(current_user.id)
                g.api_caller = 'session'
                g.api_key_row = None
                return f(*args, **kwargs)
            code = 'UNAUTHENTICATED' if request.path.endswith('/keys') or '/keys/' in request.path else 'MISSING_AUTH'
            return api_error('Missing Authorization header', code=code, status_code=401)

        # 1. SRN shared secret bypass
        srn_secret = _get_srn_key()
        if srn_secret and len(token) == len(srn_secret) and hmac.compare_digest(token, srn_secret):
            g.api_user_id = None
            g.api_caller = caller
            g.api_key_row = None
            return f(*args, **kwargs)

        # 2. User API key lookup
        row = _get_api_key_row(token)
        if not row:
            return api_error('Invalid or revoked API key', code='INVALID_KEY', status_code=401)

        # Check active status
        is_active = row.get('is_active', row.get('active', 1))
        if not is_active:
            return api_error('Invalid or revoked API key', code='INVALID_KEY', status_code=401)

        # Check expiry
        expires_at = row.get('expires_at')
        if expires_at:
            now_ts = int(time.time())
            try:
                if isinstance(expires_at, (int, float)) and expires_at < now_ts:
                    return api_error('API key has expired', code='KEY_EXPIRED', status_code=401)
                elif isinstance(expires_at, str) and int(expires_at) < now_ts:
                    return api_error('API key has expired', code='KEY_EXPIRED', status_code=401)
            except (ValueError, TypeError):
                pass

        # Update last_used and call_count
        try:
            db = get_db()
            now_ts = int(time.time())
            db.execute(
                'UPDATE api_keys SET last_used_at = ?, call_count = call_count + 1 WHERE id = ?',
                (now_ts, row['id']),
            )
            db.commit()
        except Exception:
            try:
                db.execute(
                    'UPDATE api_keys SET last_used = ?, call_count = call_count + 1 WHERE id = ?',
                    (now_ts, row['id']),
                )
                db.commit()
            except Exception:
                pass

        g.api_user_id = str(row['user_id'])
        g.api_caller = caller
        g.api_key_row = row
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Health & Manifest Endpoints
# ---------------------------------------------------------------------------

@api_v1_bp.route('/health', methods=['GET'])
def health():
    """Public health check endpoint."""
    uptime = int(time.time())
    is_legacy = request.path.startswith('/v1/') or request.path == '/v1/health' or request.path == '/v1'
    status_str = 'ok' if is_legacy else 'success'
    health_payload = {
        'status': 'ok',
        'healthy': True,
        'app': APP_NAME,
        'version': APP_VERSION,
        'uptime': uptime,
    }
    return jsonify({
        'status': status_str,
        'healthy': True,
        'success': True,
        'app': APP_NAME,
        'version': APP_VERSION,
        'uptime': uptime,
        'data': health_payload,
    }), 200


@api_v1_bp.route('/manifest', methods=['GET'])
@require_api_key
def manifest():
    """SRN manifest -- list of tools exposed by Post-Pilot."""
    tools = [
        {
            'name': 'draft_post',
            'description': 'Create a draft post in post history',
            'method': 'POST',
            'path': '/api/v1/posts/draft',
            'input': {
                'caption': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
                'media_urls': {'type': 'array', 'required': False},
                'scheduled_time': {'type': 'string', 'required': False},
                'tags': {'type': 'array', 'required': False},
            },
            'output': {'status': 'string', 'data': {'post_id': 'string'}},
        },
        {
            'name': 'generate_post',
            'description': 'Generate an AI social media caption with platform adaptations',
            'method': 'POST',
            'path': '/api/v1/posts/generate',
            'input': {
                'topic': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
                'tone': {'type': 'string', 'required': False},
            },
            'output': {'status': 'string', 'data': {'caption': 'string', 'master': 'string', 'adapted': 'object'}},
        },
        {
            'name': 'publish_post',
            'description': 'Publish a post immediately to selected platforms',
            'method': 'POST',
            'path': '/api/v1/posts/dispatch',
            'input': {
                'caption': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
                'image_url': {'type': 'string', 'required': False},
            },
            'output': {'status': 'string', 'data': {'post_id': 'string', 'results': 'object'}},
        },
        {
            'name': 'dispatch_post',
            'description': 'Immediately publish a post to selected platforms',
            'method': 'POST',
            'path': '/api/v1/posts/dispatch',
            'input': {
                'caption': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
                'image_url': {'type': 'string', 'required': False},
            },
            'output': {'status': 'string', 'data': {'post_id': 'string', 'results': 'object'}},
        },
        {
            'name': 'generate_and_publish',
            'description': 'One-shot: generate caption then publish immediately',
            'method': 'POST',
            'path': '/api/v1/generate_and_publish',
            'input': {
                'topic': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
            },
            'output': {'status': 'string', 'data': {'post_id': 'string', 'caption': 'string'}},
        },
        {
            'name': 'schedule_post',
            'description': 'Queue a post to publish at a future timestamp',
            'method': 'POST',
            'path': '/api/v1/posts/schedule',
            'input': {
                'caption': {'type': 'string', 'required': True},
                'scheduled_time': {'type': 'string', 'required': True},
                'platforms': {'type': 'array', 'required': False},
            },
            'output': {'status': 'string', 'data': {'post_id': 'string', 'scheduled_at': 'integer'}},
        },
        {
            'name': 'get_history',
            'description': 'Retrieve post history with pagination and status filters',
            'method': 'GET',
            'path': '/api/v1/posts/history',
            'input': {
                'limit': {'type': 'integer', 'required': False},
                'offset': {'type': 'integer', 'required': False},
                'status': {'type': 'string', 'required': False},
            },
            'output': {'status': 'string', 'data': {'posts': 'array', 'count': 'integer'}},
        },
        {
            'name': 'get_site_config',
            'description': 'Get website hub config for a user',
            'method': 'GET',
            'path': '/api/v1/get_site_config',
        },
        {
            'name': 'set_published',
            'description': 'Publish or unpublish a user website',
            'method': 'POST',
            'path': '/api/v1/set_published',
        },
        {
            'name': 'specials_crud',
            'description': 'CRUD operations for daily specials schedule',
            'method': 'GET/POST/PUT/DELETE',
            'path': '/api/v1/specials',
        },
        {
            'name': 'events_crud',
            'description': 'CRUD operations for upcoming events',
            'method': 'GET/POST/PUT/DELETE',
            'path': '/api/v1/events',
        },
        {
            'name': 'hours_overrides_crud',
            'description': 'CRUD operations for operating hours overrides',
            'method': 'GET/POST/PUT/DELETE',
            'path': '/api/v1/hours/overrides',
        },
        {
            'name': 'analytics_summary',
            'description': 'Combined analytics KPI summary and chart data',
            'method': 'GET',
            'path': '/api/v1/analytics/summary',
        },
    ]
    return api_success({'app': APP_NAME, 'version': APP_VERSION, 'tools': tools})


# ---------------------------------------------------------------------------
# Posts: Draft, Generate, Dispatch, Schedule, History
# ---------------------------------------------------------------------------

@api_v1_bp.route('/posts/draft', methods=['POST'])
@require_api_key
def create_draft():
    """Create a post draft in post_history."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    caption = (body.get('caption') or body.get('content') or '').strip()
    if not caption:
        return api_error('caption is required', code='MISSING_CAPTION', status_code=400)

    platforms = body.get('platforms') or ['fb', 'ig']
    content_type = body.get('content_type', 'text')
    media_urls = body.get('media_urls')
    image_url = body.get('image_url') or (media_urls[0] if media_urls and isinstance(media_urls, list) else None)
    video_url = body.get('video_url')
    link_url = body.get('link_url')
    scheduled_at = body.get('scheduled_time') or body.get('scheduled_at')
    tags = body.get('tags') or body.get('hashtags') or []

    post_id = UserManager.log_post(
        user_id=uid,
        caption=caption,
        content_type=content_type,
        image_url=image_url,
        video_url=video_url,
        platforms=platforms,
        results={'draft': True, 'tags': tags, 'link_url': link_url},
        scheduled_at=scheduled_at,
        status='draft',
    )

    return api_success({
        'post_id': str(post_id),
        'status': 'draft',
        'caption': caption,
        'platforms': platforms,
        'content_type': content_type,
        'image_url': image_url,
        'video_url': video_url,
        'scheduled_at': scheduled_at,
        'tags': tags,
    }, status_code=201)


@api_v1_bp.route('/posts/generate', methods=['POST'])
@api_v1_bp.route('/generate_post', methods=['POST'])
@require_api_key
def generate_post():
    """AI caption generation with multi-platform adaptations."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))

    topic = (body.get('topic') or body.get('prompt') or '').strip()
    if not topic:
        return api_error('topic or prompt is required', code='MISSING_TOPIC', status_code=400)

    platform = body.get('platform')
    platforms = body.get('platforms')
    if platform and not platforms:
        platforms = [platform]
    elif not platforms:
        platforms = ['fb', 'ig']

    tone = body.get('tone', 'friendly')
    keywords = body.get('keywords', [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(',') if k.strip()]

    # Load business profile for context if available
    business_info = body.get('business_info')
    if not business_info and uid:
        try:
            db = get_db()
            row = db.execute('SELECT * FROM business_profiles WHERE user_id = ?', (uid,)).fetchone()
            if row:
                d = dict(row)
                business_info = {
                    'name': d.get('name') or 'Our Business',
                    'type': d.get('business_type') or 'restaurant',
                    'location': d.get('location') or '',
                    'hours': d.get('hours') or '',
                    'special': topic,
                }
        except Exception:
            pass

    if not business_info:
        business_info = {
            'name': 'Our Business',
            'type': 'restaurant',
            'location': 'Downtown',
            'hours': '11 AM - 8 PM',
            'special': topic,
        }

    try:
        from modules.post_generator import PostGenerator
        gen = PostGenerator(user_id=uid)
        gen_result = gen.generate(topic=topic, platform=platforms[0] if platforms else 'instagram', tone=tone)
        primary_caption = gen_result.get('caption', topic)
        hashtags = gen_result.get('hashtags', [])

        return api_success({
            'caption': primary_caption,
            'master': primary_caption,
            'adapted': {p: primary_caption for p in platforms},
            'hashtags': hashtags,
            'platforms': platforms,
        })
    except Exception as e:
        logger.exception('generate_post failed: %s', e)
        return api_error(str(e), code='GENERATION_ERROR', status_code=500)


@api_v1_bp.route('/posts/dispatch', methods=['POST'])
@api_v1_bp.route('/publish_post', methods=['POST'])
@require_api_key
def dispatch_post():
    """Multi-platform immediate publishing dispatch (UniversalPublisher)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    caption = (body.get('caption') or body.get('content') or '').strip()
    captions = body.get('captions')
    if not caption and captions and isinstance(captions, dict):
        caption = next(iter(captions.values()), '').strip()

    # One-shot generate & publish support
    topic = body.get('topic') or body.get('prompt')
    if not caption and topic:
        try:
            from modules.post_generator import PostGenerator
            gen = PostGenerator(user_id=uid)
            gen_result = gen.generate(
                topic=topic,
                platform=body.get('platforms', ['facebook'])[0] if body.get('platforms') else 'facebook',
                tone=body.get('tone', 'friendly'),
            )
            caption = gen_result.get('caption', topic)
        except Exception:
            try:
                from modules.ai_generator import generate_caption
                caption = generate_caption(
                    business_info={'name': 'Our Business', 'type': 'restaurant', 'special': topic},
                    content_type=body.get('content_type', 'general'),
                    tone=body.get('tone', 'friendly'),
                    platform=body.get('platforms', ['facebook'])[0] if body.get('platforms') else 'facebook',
                )
            except Exception as e:
                return api_error(f'AI generation failed: {e}', code='GENERATION_ERROR', status_code=500)

    if not caption:
        return api_error('caption is required', code='MISSING_CAPTION', status_code=400)

    platforms = body.get('platforms') or ['fb', 'ig']
    content_type = body.get('content_type', 'text')
    image_url = body.get('image_url')
    video_url = body.get('video_url')
    link_url = body.get('link_url')
    scheduled_at = body.get('scheduled_at') or body.get('schedule_time')

    # Input validation
    if content_type == 'image' and not image_url and not video_url:
        return api_error(
            'Validation failed: content_type is "image" but no image_url was provided.',
            code='VALIDATION_ERROR',
            status_code=400,
        )

    # Tier limits enforcement
    user, tier = _get_user_and_tier(uid)
    allowed, limit = check_platform_limit(tier, platforms)
    if not allowed:
        return api_error(f'Your plan allows up to {limit} platform(s) at once.', code='PLATFORM_LIMIT', status_code=403)

    used_posts = UserManager.count_posts_this_month(uid)
    allowed, limit = check_post_limit(tier, used_posts)
    if not allowed:
        return api_error(f'Your plan allows {limit} posts this month.', code='POST_LIMIT', status_code=403)

    tokens = _get_tokens(uid)
    publisher = UniversalPublisher(tokens, user_id=uid)
    results = publisher.push_all(
        caption=caption,
        captions=captions,
        content_type=content_type,
        image_url=image_url,
        video_url=video_url,
        link_url=link_url,
        platforms=platforms,
        schedule_time=str(scheduled_at) if scheduled_at else None,
    )

    post_id = UserManager.log_post(
        user_id=uid,
        caption=caption,
        content_type=content_type,
        image_url=image_url,
        video_url=video_url,
        platforms=platforms,
        results=results,
        scheduled_at=scheduled_at,
        status='scheduled' if scheduled_at else 'published',
    )

    return api_success({
        'post_id': str(post_id),
        'results': results,
        'status': 'scheduled' if scheduled_at else 'published',
        'caption': caption,
        'platforms': platforms,
    })


@api_v1_bp.route('/generate_and_publish', methods=['POST'])
@require_api_key
def generate_and_publish():
    """One-shot: generate caption then publish immediately."""
    return dispatch_post()


@api_v1_bp.route('/posts/schedule', methods=['POST'])
@require_api_key
def schedule_post():
    """Queue and schedule a post for a future timestamp."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    caption = (body.get('caption') or '').strip()
    if not caption:
        return api_error('caption is required', code='MISSING_CAPTION', status_code=400)

    scheduled_at = body.get('scheduled_time') or body.get('scheduled_at')
    if not scheduled_at:
        return api_error('scheduled_time or scheduled_at is required', code='MISSING_SCHEDULE_TIME', status_code=400)

    # Convert scheduled timestamp / date
    ts_val = None
    if isinstance(scheduled_at, (int, float)):
        ts_val = int(scheduled_at)
    elif isinstance(scheduled_at, str):
        try:
            ts_val = int(scheduled_at)
        except ValueError:
            try:
                dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                ts_val = int(dt.timestamp())
            except Exception:
                return api_error(
                    'Invalid scheduled_time format. Use Unix timestamp or ISO-8601 string.',
                    code='INVALID_SCHEDULE_TIME',
                    status_code=400,
                )

    platforms = body.get('platforms') or ['fb', 'ig']
    content_type = body.get('content_type', 'text')
    image_url = body.get('image_url')
    video_url = body.get('video_url')
    link_url = body.get('link_url')
    captions = body.get('captions')

    user, tier = _get_user_and_tier(uid)
    allowed, limit = check_platform_limit(tier, platforms)
    if not allowed:
        return api_error(f'Your plan allows up to {limit} platform(s) at once.', code='PLATFORM_LIMIT', status_code=403)

    post_id = UserManager.log_post(
        user_id=uid,
        caption=caption,
        content_type=content_type,
        image_url=image_url,
        video_url=video_url,
        platforms=platforms,
        results={'scheduled': True, 'captions': captions, 'link_url': link_url} if captions else {'scheduled': True},
        scheduled_at=ts_val,
        status='scheduled',
    )

    return api_success({
        'post_id': str(post_id),
        'status': 'scheduled',
        'scheduled_at': ts_val,
        'caption': caption,
        'platforms': platforms,
    }, status_code=201)


# ---------------------------------------------------------------------------
# Buffer-style Queue Slot Buffering & Engagement Analysis
# ---------------------------------------------------------------------------

@api_v1_bp.route('/posts/queue', methods=['POST'])
@require_api_key
def queue_post_to_next_slot():
    """
    Buffer-style Smart Queue Slot: automatically schedules the post to the next
    available marketing/rush time slot (e.g. tomorrow 11:30 AM lunch slot).
    """
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    caption = (body.get('caption') or '').strip()
    if not caption:
        return api_error('caption is required', code='MISSING_CAPTION', status_code=400)

    # Calculate next queue slot: default tomorrow 11:30 AM or +4 hours if current time is morning
    now = datetime.now()
    slot_hour = 11 if now.hour < 11 else (17 if now.hour < 17 else 11)
    day_offset = 1 if now.hour >= 17 else 0
    import datetime as dt_module
    target_date = now.date() + dt_module.timedelta(days=day_offset)
    scheduled_dt = datetime(target_date.year, target_date.month, target_date.day, slot_hour, 30, 0)
    scheduled_ts = int(scheduled_dt.timestamp())

    platforms = body.get('platforms') or ['fb', 'ig']
    content_type = body.get('content_type', 'text')
    image_url = body.get('image_url')
    video_url = body.get('video_url')
    first_comment = body.get('first_comment')

    user, tier = _get_user_and_tier(uid)
    allowed, limit = check_platform_limit(tier, platforms)
    if not allowed:
        return api_error(f'Your plan allows up to {limit} platform(s) at once.', code='PLATFORM_LIMIT', status_code=403)

    post_id = UserManager.log_post(
        user_id=uid,
        caption=caption,
        content_type=content_type,
        image_url=image_url,
        video_url=video_url,
        platforms=platforms,
        results={'queued': True, 'slot_type': 'auto_rush_slot', 'first_comment': first_comment},
        scheduled_at=scheduled_ts,
        status='scheduled',
    )

    return api_success({
        'post_id': str(post_id),
        'status': 'scheduled',
        'queued_slot': scheduled_dt.isoformat(),
        'scheduled_at': scheduled_ts,
        'caption': caption,
        'platforms': platforms,
    }, status_code=201)


@api_v1_bp.route('/posts/analyze', methods=['POST'])
@require_api_key
def analyze_post_engagement():
    """Analyze engagement & viral score for a draft caption (Sprout/Hootsuite pattern)."""
    body = request.get_json(silent=True) or {}
    caption = (body.get('caption') or '').strip()
    if not caption:
        return api_error('caption is required', code='MISSING_CAPTION', status_code=400)

    platform = body.get('platform', 'instagram')
    content_type = body.get('content_type', 'general')

    from modules.ai_generator import calculate_engagement_score
    analysis = calculate_engagement_score(caption=caption, platform=platform, content_type=content_type)
    return api_success(analysis)


@api_v1_bp.route('/posts/history', methods=['GET'])
@api_v1_bp.route('/get_history', methods=['GET'])
@require_api_key
def get_history():
    """Get post history with pagination and status filters."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        limit = min(max(int(request.args.get('limit', 20)), 1), 100)
    except (ValueError, TypeError):
        limit = 20

    try:
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    status = request.args.get('status')
    posts = UserManager.get_post_history(uid, limit=limit, offset=offset, status=status)
    return api_success({
        'posts': posts,
        'count': len(posts),
        'limit': limit,
        'offset': offset,

    })


# ---------------------------------------------------------------------------
# Specials CRUD
# ---------------------------------------------------------------------------

@api_v1_bp.route('/specials', methods=['GET'])
@require_api_key
def list_specials():
    """List daily specials for the user with optional filters."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    post_date = request.args.get('post_date')
    status = request.args.get('status')

    query = 'SELECT * FROM specials WHERE user_id = ?'
    params = [uid]
    if post_date:
        query += ' AND post_date = ?'
        params.append(post_date)
    if status:
        query += ' AND status = ?'
        params.append(status)
    query += ' ORDER BY post_date ASC, post_time ASC'

    try:
        db = get_db()
        rows = db.execute(query, params).fetchall()
        specials = []
        for r in rows:
            d = dict(r)
            if d.get('platforms') and isinstance(d['platforms'], str):
                try:
                    d['platforms'] = json.loads(d['platforms'])
                except Exception:
                    pass
            specials.append(d)
        return api_success({'specials': specials, 'count': len(specials)})
    except Exception as e:
        logger.exception('list_specials failed: %s', e)
        return api_error('Could not load specials', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/specials', methods=['POST'])
@require_api_key
def create_special():
    """Create a new daily special."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    item_name = (body.get('item_name') or '').strip()
    post_date = (body.get('post_date') or '').strip()
    post_time = (body.get('post_time') or '11:00').strip()
    description = (body.get('description') or '').strip()
    content_type = body.get('content_type', 'daily_special')
    tone = body.get('tone', 'friendly')
    image_url = (body.get('image_url') or '').strip() or None
    platforms = body.get('platforms') or ['fb', 'ig', 'tt', 'gb', 'web']

    errors = []
    if not item_name:
        errors.append('item_name is required')
    if not post_date:
        errors.append('post_date is required (YYYY-MM-DD)')
    else:
        try:
            datetime.strptime(post_date, '%Y-%m-%d')
        except ValueError:
            errors.append('post_date must be YYYY-MM-DD')
    try:
        datetime.strptime(post_time, '%H:%M')
    except ValueError:
        errors.append('post_time must be HH:MM (24h)')
    if content_type not in CONTENT_TYPES_SPECIALS:
        content_type = 'daily_special'
    if tone not in TONES:
        tone = 'friendly'
    if not isinstance(platforms, list) or not platforms:
        errors.append('platforms must be a non-empty list')

    if errors:
        return api_error('; '.join(errors), code='VALIDATION_ERROR', status_code=400, errors=errors)

    now_ts = int(time.time())
    try:
        db = get_db()
        cur = db.execute(
            '''
            INSERT INTO specials
              (user_id, item_name, description, post_date, post_time, platforms,
               content_type, tone, image_url, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                uid,
                item_name,
                description or None,
                post_date,
                post_time,
                json.dumps(platforms),
                content_type,
                tone,
                image_url,
                'pending',
                now_ts,
                now_ts,
            ),
        )
        db.commit()
        special_id = cur.lastrowid
        return api_success({'id': special_id, 'message': 'Special created'}, status_code=201)
    except Exception as e:
        logger.exception('create_special failed: %s', e)
        return api_error('Could not create special', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/specials/<int:special_id>', methods=['GET'])
@require_api_key
def get_special(special_id: int):
    """Get single special by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT * FROM specials WHERE id = ? AND user_id = ?', (special_id, uid)).fetchone()
        if not row:
            return api_error('Special not found', code='NOT_FOUND', status_code=404)
        d = dict(row)
        if d.get('platforms') and isinstance(d['platforms'], str):
            try:
                d['platforms'] = json.loads(d['platforms'])
            except Exception:
                pass
        return api_success({'special': d})
    except Exception as e:
        logger.exception('get_special failed: %s', e)
        return api_error('Could not load special', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/specials/<int:special_id>', methods=['PUT', 'PATCH'])
@require_api_key
def update_special(special_id: int):
    """Update special (pending only)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT status FROM specials WHERE id = ? AND user_id = ?', (special_id, uid)).fetchone()
        if not row:
            return api_error('Special not found', code='NOT_FOUND', status_code=404)
        if row['status'] != 'pending':
            return api_error(f'Cannot edit a {row["status"]} special', code='CONFLICT', status_code=409)

        fields, values = [], []
        if 'item_name' in body and body['item_name'].strip():
            fields.append('item_name = ?')
            values.append(body['item_name'].strip())
        if 'description' in body:
            fields.append('description = ?')
            values.append(body['description'] or None)
        if 'post_date' in body:
            try:
                datetime.strptime(body['post_date'], '%Y-%m-%d')
                fields.append('post_date = ?')
                values.append(body['post_date'])
            except ValueError:
                return api_error('post_date must be YYYY-MM-DD', code='VALIDATION_ERROR', status_code=400)
        if 'post_time' in body:
            try:
                datetime.strptime(body['post_time'], '%H:%M')
                fields.append('post_time = ?')
                values.append(body['post_time'])
            except ValueError:
                return api_error('post_time must be HH:MM', code='VALIDATION_ERROR', status_code=400)
        if 'platforms' in body and isinstance(body['platforms'], list):
            fields.append('platforms = ?')
            values.append(json.dumps(body['platforms']))
        if 'content_type' in body and body['content_type'] in CONTENT_TYPES_SPECIALS:
            fields.append('content_type = ?')
            values.append(body['content_type'])
        if 'tone' in body and body['tone'] in TONES:
            fields.append('tone = ?')
            values.append(body['tone'])
        if 'image_url' in body:
            fields.append('image_url = ?')
            values.append(body['image_url'] or None)

        if not fields:
            return api_success({'message': 'Nothing to update'})

        fields.append('updated_at = ?')
        values.append(int(time.time()))
        values.extend([special_id, uid])

        db.execute(f'UPDATE specials SET {", ".join(fields)} WHERE id = ? AND user_id = ?', values)
        db.commit()
        return api_success({'message': 'Special updated'})
    except Exception as e:
        logger.exception('update_special failed: %s', e)
        return api_error('Update failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/specials/<int:special_id>', methods=['DELETE'])
@require_api_key
def delete_special(special_id: int):
    """Delete special by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute('DELETE FROM specials WHERE id = ? AND user_id = ?', (special_id, uid))
        db.commit()
        if cur.rowcount == 0:
            return api_error('Special not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Special deleted'})
    except Exception as e:
        logger.exception('delete_special failed: %s', e)
        return api_error('Delete failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/specials/<int:special_id>/cancel', methods=['POST'])
@require_api_key
def cancel_special(special_id: int):
    """Cancel a special (status=cancelled)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute(
            'UPDATE specials SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            ('cancelled', int(time.time()), special_id, uid),
        )
        db.commit()
        if cur.rowcount == 0:
            return api_error('Special not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Special cancelled'})
    except Exception as e:
        logger.exception('cancel_special failed: %s', e)
        return api_error('Cancel failed', code='DB_ERROR', status_code=500)


# ---------------------------------------------------------------------------
# Events CRUD
# ---------------------------------------------------------------------------

@api_v1_bp.route('/events', methods=['GET'])
@require_api_key
def list_events():
    """List upcoming events for the user with optional filters."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    event_date = request.args.get('event_date')
    post_date = request.args.get('post_date')
    status = request.args.get('status')
    event_type = request.args.get('event_type')

    query = 'SELECT * FROM events WHERE user_id = ?'
    params = [uid]
    if event_date:
        query += ' AND event_date = ?'
        params.append(event_date)
    if post_date:
        query += ' AND post_date = ?'
        params.append(post_date)
    if status:
        query += ' AND status = ?'
        params.append(status)
    if event_type:
        query += ' AND event_type = ?'
        params.append(event_type)
    query += ' ORDER BY post_date ASC, post_time ASC'

    try:
        db = get_db()
        rows = db.execute(query, params).fetchall()
        events = []
        for r in rows:
            d = dict(r)
            if d.get('platforms') and isinstance(d['platforms'], str):
                try:
                    d['platforms'] = json.loads(d['platforms'])
                except Exception:
                    pass
            events.append(d)
        return api_success({'events': events, 'count': len(events)})
    except Exception as e:
        logger.exception('list_events failed: %s', e)
        return api_error('Could not load events', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/events', methods=['POST'])
@require_api_key
def create_event():
    """Create a new upcoming event."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    title = (body.get('title') or '').strip()
    post_date = (body.get('post_date') or '').strip()
    post_time = (body.get('post_time') or '11:00').strip()
    event_date = (body.get('event_date') or post_date).strip()
    event_end = (body.get('event_end_date') or '').strip() or None
    description = (body.get('description') or '').strip() or None
    event_type = body.get('event_type', 'event')
    tone = body.get('tone', 'hype')
    image_url = (body.get('image_url') or '').strip() or None
    ticket_url = (body.get('ticket_url') or '').strip() or None
    platforms = body.get('platforms') or ['fb', 'ig', 'tt', 'gb', 'web']

    errors = []
    if not title:
        errors.append('title is required')
    if not post_date:
        errors.append('post_date is required (YYYY-MM-DD)')
    else:
        try:
            datetime.strptime(post_date, '%Y-%m-%d')
        except ValueError:
            errors.append('post_date must be YYYY-MM-DD')
    if event_date:
        try:
            datetime.strptime(event_date, '%Y-%m-%d')
        except ValueError:
            errors.append('event_date must be YYYY-MM-DD')
    if event_end:
        try:
            datetime.strptime(event_end, '%Y-%m-%d')
        except ValueError:
            errors.append('event_end_date must be YYYY-MM-DD')
    try:
        datetime.strptime(post_time, '%H:%M')
    except ValueError:
        errors.append('post_time must be HH:MM')
    if event_type not in EVENT_TYPES:
        event_type = 'event'
    if tone not in TONES:
        tone = 'hype'
    if not isinstance(platforms, list) or not platforms:
        errors.append('platforms must be a non-empty list')

    if errors:
        return api_error('; '.join(errors), code='VALIDATION_ERROR', status_code=400, errors=errors)

    now_ts = int(time.time())
    try:
        db = get_db()
        cur = db.execute(
            '''
            INSERT INTO events
              (user_id, title, description, event_date, event_end_date, post_date,
               post_time, event_type, platforms, tone, image_url, ticket_url,
               status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                uid,
                title,
                description,
                event_date,
                event_end,
                post_date,
                post_time,
                event_type,
                json.dumps(platforms),
                tone,
                image_url,
                ticket_url,
                'pending',
                now_ts,
                now_ts,
            ),
        )
        db.commit()
        event_id = cur.lastrowid
        return api_success({'id': event_id, 'message': 'Event created'}, status_code=201)
    except Exception as e:
        logger.exception('create_event failed: %s', e)
        return api_error('Could not create event', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/events/<int:event_id>', methods=['GET'])
@require_api_key
def get_event(event_id: int):
    """Get single event by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT * FROM events WHERE id = ? AND user_id = ?', (event_id, uid)).fetchone()
        if not row:
            return api_error('Event not found', code='NOT_FOUND', status_code=404)
        d = dict(row)
        if d.get('platforms') and isinstance(d['platforms'], str):
            try:
                d['platforms'] = json.loads(d['platforms'])
            except Exception:
                pass
        return api_success({'event': d})
    except Exception as e:
        logger.exception('get_event failed: %s', e)
        return api_error('Could not load event', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/events/<int:event_id>', methods=['PUT', 'PATCH'])
@require_api_key
def update_event(event_id: int):
    """Update event (pending only)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT status FROM events WHERE id = ? AND user_id = ?', (event_id, uid)).fetchone()
        if not row:
            return api_error('Event not found', code='NOT_FOUND', status_code=404)
        if row['status'] != 'pending':
            return api_error(f'Cannot edit a {row["status"]} event', code='CONFLICT', status_code=409)

        fields, values = [], []
        if 'title' in body and body['title'].strip():
            fields.append('title = ?')
            values.append(body['title'].strip())
        if 'description' in body:
            fields.append('description = ?')
            values.append(body['description'] or None)
        if 'event_date' in body:
            try:
                datetime.strptime(body['event_date'], '%Y-%m-%d')
                fields.append('event_date = ?')
                values.append(body['event_date'])
            except ValueError:
                return api_error('event_date must be YYYY-MM-DD', code='VALIDATION_ERROR', status_code=400)
        if 'event_end_date' in body:
            fields.append('event_end_date = ?')
            values.append(body['event_end_date'] or None)
        if 'post_date' in body:
            try:
                datetime.strptime(body['post_date'], '%Y-%m-%d')
                fields.append('post_date = ?')
                values.append(body['post_date'])
            except ValueError:
                return api_error('post_date must be YYYY-MM-DD', code='VALIDATION_ERROR', status_code=400)
        if 'post_time' in body:
            try:
                datetime.strptime(body['post_time'], '%H:%M')
                fields.append('post_time = ?')
                values.append(body['post_time'])
            except ValueError:
                return api_error('post_time must be HH:MM', code='VALIDATION_ERROR', status_code=400)
        if 'event_type' in body and body['event_type'] in EVENT_TYPES:
            fields.append('event_type = ?')
            values.append(body['event_type'])
        if 'platforms' in body and isinstance(body['platforms'], list):
            fields.append('platforms = ?')
            values.append(json.dumps(body['platforms']))
        if 'tone' in body and body['tone'] in TONES:
            fields.append('tone = ?')
            values.append(body['tone'])
        if 'image_url' in body:
            fields.append('image_url = ?')
            values.append(body['image_url'] or None)
        if 'ticket_url' in body:
            fields.append('ticket_url = ?')
            values.append(body['ticket_url'] or None)

        if not fields:
            return api_success({'message': 'Nothing to update'})

        fields.append('updated_at = ?')
        values.append(int(time.time()))
        values.extend([event_id, uid])

        db.execute(f'UPDATE events SET {", ".join(fields)} WHERE id = ? AND user_id = ?', values)
        db.commit()
        return api_success({'message': 'Event updated'})
    except Exception as e:
        logger.exception('update_event failed: %s', e)
        return api_error('Update failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/events/<int:event_id>', methods=['DELETE'])
@require_api_key
def delete_event(event_id: int):
    """Delete event by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute('DELETE FROM events WHERE id = ? AND user_id = ?', (event_id, uid))
        db.commit()
        if cur.rowcount == 0:
            return api_error('Event not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Event deleted'})
    except Exception as e:
        logger.exception('delete_event failed: %s', e)
        return api_error('Delete failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/events/<int:event_id>/cancel', methods=['POST'])
@require_api_key
def cancel_event(event_id: int):
    """Cancel an event (status=cancelled)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute(
            'UPDATE events SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            ('cancelled', int(time.time()), event_id, uid),
        )
        db.commit()
        if cur.rowcount == 0:
            return api_error('Event not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Event cancelled'})
    except Exception as e:
        logger.exception('cancel_event failed: %s', e)
        return api_error('Cancel failed', code='DB_ERROR', status_code=500)


# ---------------------------------------------------------------------------
# Hours Overrides CRUD
# ---------------------------------------------------------------------------

@api_v1_bp.route('/hours/overrides', methods=['GET'])
@require_api_key
def list_hours_overrides():
    """List hours overrides for user with optional filters."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    post_date = request.args.get('post_date')
    status = request.args.get('status')
    override_type = request.args.get('override_type')

    query = 'SELECT * FROM hours_overrides WHERE user_id = ?'
    params = [uid]
    if post_date:
        query += ' AND post_date = ?'
        params.append(post_date)
    if status:
        query += ' AND status = ?'
        params.append(status)
    if override_type:
        query += ' AND override_type = ?'
        params.append(override_type)
    query += ' ORDER BY post_date ASC, post_time ASC'

    try:
        db = get_db()
        rows = db.execute(query, params).fetchall()
        overrides = []
        for r in rows:
            d = dict(r)
            if d.get('platforms') and isinstance(d['platforms'], str):
                try:
                    d['platforms'] = json.loads(d['platforms'])
                except Exception:
                    pass
            overrides.append(d)
        return api_success({'overrides': overrides, 'count': len(overrides)})
    except Exception as e:
        logger.exception('list_hours_overrides failed: %s', e)
        return api_error('Could not load hours overrides', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/hours/overrides', methods=['POST'])
@require_api_key
def create_hours_override():
    """Create a new hours override."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    title = (body.get('title') or '').strip()
    post_date = (body.get('post_date') or '').strip()
    post_time = (body.get('post_time') or '09:00').strip()
    message = (body.get('message') or '').strip() or None
    override_type = body.get('override_type', 'closure')
    tone = body.get('tone', 'friendly')
    platforms = body.get('platforms') or ['fb', 'ig', 'gb', 'web']

    errors = []
    if not title:
        errors.append('title is required')
    if not post_date:
        errors.append('post_date is required (YYYY-MM-DD)')
    else:
        try:
            datetime.strptime(post_date, '%Y-%m-%d')
        except ValueError:
            errors.append('post_date must be YYYY-MM-DD')
    try:
        datetime.strptime(post_time, '%H:%M')
    except ValueError:
        errors.append('post_time must be HH:MM')
    if override_type not in OVERRIDE_TYPES:
        override_type = 'closure'
    if tone not in TONES:
        tone = 'friendly'
    if not isinstance(platforms, list) or not platforms:
        errors.append('platforms must be a non-empty list')

    if errors:
        return api_error('; '.join(errors), code='VALIDATION_ERROR', status_code=400, errors=errors)

    now_ts = int(time.time())
    try:
        db = get_db()
        cur = db.execute(
            '''
            INSERT INTO hours_overrides
              (user_id, title, message, override_type, post_date, post_time,
               platforms, tone, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                uid,
                title,
                message,
                override_type,
                post_date,
                post_time,
                json.dumps(platforms),
                tone,
                'pending',
                now_ts,
                now_ts,
            ),
        )
        db.commit()
        override_id = cur.lastrowid
        return api_success({'id': override_id, 'message': 'Hours override created'}, status_code=201)
    except Exception as e:
        logger.exception('create_hours_override failed: %s', e)
        return api_error('Could not create hours override', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/hours/overrides/<int:override_id>', methods=['GET'])
@require_api_key
def get_hours_override(override_id: int):
    """Get single hours override by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT * FROM hours_overrides WHERE id = ? AND user_id = ?', (override_id, uid)).fetchone()
        if not row:
            return api_error('Hours override not found', code='NOT_FOUND', status_code=404)
        d = dict(row)
        if d.get('platforms') and isinstance(d['platforms'], str):
            try:
                d['platforms'] = json.loads(d['platforms'])
            except Exception:
                pass
        return api_success({'override': d})
    except Exception as e:
        logger.exception('get_hours_override failed: %s', e)
        return api_error('Could not load hours override', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/hours/overrides/<int:override_id>', methods=['PUT', 'PATCH'])
@require_api_key
def update_hours_override(override_id: int):
    """Update hours override (pending only)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        row = db.execute('SELECT status FROM hours_overrides WHERE id = ? AND user_id = ?', (override_id, uid)).fetchone()
        if not row:
            return api_error('Hours override not found', code='NOT_FOUND', status_code=404)
        if row['status'] != 'pending':
            return api_error(f'Cannot edit a {row["status"]} hours override', code='CONFLICT', status_code=409)

        fields, values = [], []
        if 'title' in body and body['title'].strip():
            fields.append('title = ?')
            values.append(body['title'].strip())
        if 'message' in body:
            fields.append('message = ?')
            values.append(body['message'] or None)
        if 'post_date' in body:
            try:
                datetime.strptime(body['post_date'], '%Y-%m-%d')
                fields.append('post_date = ?')
                values.append(body['post_date'])
            except ValueError:
                return api_error('post_date must be YYYY-MM-DD', code='VALIDATION_ERROR', status_code=400)
        if 'post_time' in body:
            try:
                datetime.strptime(body['post_time'], '%H:%M')
                fields.append('post_time = ?')
                values.append(body['post_time'])
            except ValueError:
                return api_error('post_time must be HH:MM', code='VALIDATION_ERROR', status_code=400)
        if 'override_type' in body and body['override_type'] in OVERRIDE_TYPES:
            fields.append('override_type = ?')
            values.append(body['override_type'])
        if 'platforms' in body and isinstance(body['platforms'], list):
            fields.append('platforms = ?')
            values.append(json.dumps(body['platforms']))
        if 'tone' in body and body['tone'] in TONES:
            fields.append('tone = ?')
            values.append(body['tone'])

        if not fields:
            return api_success({'message': 'Nothing to update'})

        fields.append('updated_at = ?')
        values.append(int(time.time()))
        values.extend([override_id, uid])

        db.execute(f'UPDATE hours_overrides SET {", ".join(fields)} WHERE id = ? AND user_id = ?', values)
        db.commit()
        return api_success({'message': 'Hours override updated'})
    except Exception as e:
        logger.exception('update_hours_override failed: %s', e)
        return api_error('Update failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/hours/overrides/<int:override_id>', methods=['DELETE'])
@require_api_key
def delete_hours_override(override_id: int):
    """Delete hours override by ID."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute('DELETE FROM hours_overrides WHERE id = ? AND user_id = ?', (override_id, uid))
        db.commit()
        if cur.rowcount == 0:
            return api_error('Hours override not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Hours override deleted'})
    except Exception as e:
        logger.exception('delete_hours_override failed: %s', e)
        return api_error('Delete failed', code='DB_ERROR', status_code=500)


@api_v1_bp.route('/hours/overrides/<int:override_id>/cancel', methods=['POST'])
@require_api_key
def cancel_hours_override(override_id: int):
    """Cancel hours override (status=cancelled)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        db = get_db()
        cur = db.execute(
            'UPDATE hours_overrides SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?',
            ('cancelled', int(time.time()), override_id, uid),
        )
        db.commit()
        if cur.rowcount == 0:
            return api_error('Hours override not found', code='NOT_FOUND', status_code=404)
        return api_success({'message': 'Hours override cancelled'})
    except Exception as e:
        logger.exception('cancel_hours_override failed: %s', e)
        return api_error('Cancel failed', code='DB_ERROR', status_code=500)


# ---------------------------------------------------------------------------
# Analytics Summary
# ---------------------------------------------------------------------------

@api_v1_bp.route('/analytics/summary', methods=['GET', 'POST'])
@require_api_key
def analytics_summary():
    """Combined Analytics summary (Meta, Google, KPIs)."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id') or request.args.get('user_id'))
    if not uid:
        return api_error('user_id is required', code='MISSING_USER_ID', status_code=400)

    try:
        days = int(request.args.get('days') or body.get('days') or 30)
        days = max(1, min(days, 90))
    except (ValueError, TypeError):
        days = 30

    tokens = _get_tokens(uid)
    token = tokens.get('facebook_token')
    page_id = tokens.get('facebook_page_id')
    ig_id = tokens.get('instagram_id')

    # Facebook / Instagram analytics
    fb_result = {
        'kpis': {'posts': 0, 'reach': 0, 'likes': 0, 'engaged': 0, 'eng_rate': 0.0},
        'chart': {'labels': [], 'reach': [], 'engaged': []},
        'ig': {},
        'posts': [],
    }

    if token and page_id:
        try:
            from modules.analytics_client import Analytics
            fb_result = Analytics(token, page_id, ig_id=ig_id).get_combined_summary(days=days)
        except Exception:
            logger.exception('analytics_summary FB failed for user %s', uid)

    # Google / YouTube analytics
    google_result = {}
    if tokens.get('google_token'):
        try:
            from modules.analytics_client import Analytics
            google_result = Analytics.get_google_youtube_summary(
                user_id=uid,
                location_id=tokens.get('google_location_id', ''),
                days=days,
            )
        except Exception:
            logger.exception('analytics_summary Google failed for user %s', uid)

    connected_platforms = [p for p, tok in tokens.items() if tok and 'token' in p]

    return api_success({
        'kpis': fb_result.get('kpis', {'posts': 0, 'reach': 0, 'likes': 0, 'engaged': 0, 'eng_rate': 0.0}),
        'chart': fb_result.get('chart', {'labels': [], 'reach': [], 'engaged': []}),
        'ig': fb_result.get('ig', {}),
        'posts': fb_result.get('posts', []),
        'google': google_result,
        'connected_platforms': connected_platforms,
        'days': days,
    })


# ---------------------------------------------------------------------------
# Legacy Endpoints (Compatibility)
# ---------------------------------------------------------------------------

@api_v1_bp.route('/get_site_config', methods=['GET'])
@require_api_key
def get_site_config():
    """Get website hub config for a user."""
    uid = _resolve_scoped_user_id(request.args.get('user_id'))
    if not uid:
        return api_error('user_id required', code='MISSING_USER_ID', status_code=400)
    try:
        from modules.website_manager import WebsiteManager
        wm = WebsiteManager(user_id=uid)
        site = wm.get_site()
        return api_success(site)
    except Exception as e:
        return api_error(str(e), code='SITE_CONFIG_ERROR', status_code=500)


@api_v1_bp.route('/set_published', methods=['POST'])
@require_api_key
def set_published():
    """Publish or unpublish a user website."""
    body = request.get_json(silent=True) or {}
    uid = _resolve_scoped_user_id(body.get('user_id'))
    published = body.get('published')

    if not uid:
        return api_error('user_id required', code='MISSING_USER_ID', status_code=400)
    if published is None:
        return api_error('published (boolean) required', code='MISSING_PUBLISHED', status_code=400)

    try:
        from modules.website_manager import WebsiteManager
        wm = WebsiteManager(user_id=uid)
        result = wm.set_published(bool(published))
        return api_success(result)
    except Exception as e:
        return api_error(str(e), code='SET_PUBLISHED_ERROR', status_code=500)


@api_v1_bp.route('/keys/create', methods=['POST'])
@require_api_key
def create_api_key():
    """Create a new API key."""
    uid = _resolve_scoped_user_id()
    if not uid:
        return api_error('Login or API authentication required', code='UNAUTHENTICATED', status_code=401)

    body = request.get_json(silent=True) or {}
    label = body.get('label', 'My Key')[:64]
    ttl = body.get('ttl_days')

    token = 'pp_live_' + secrets.token_urlsafe(32)
    expires_at = int(time.time()) + ttl * 86400 if ttl else None
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    preview = token[:12] + '...'

    try:
        db = get_db()
        db.execute(
            '''
            INSERT INTO api_keys
              (user_id, label, key_hash, key_value, key_preview, is_active, active, created_at, expires_at, call_count)
            VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, 0)
            ''',
            (uid, label, key_hash, token, preview, int(time.time()), expires_at),
        )
        db.commit()
        return api_success({'key': token, 'label': label, 'expires_at': expires_at})
    except Exception as e:
        logger.exception('create_api_key failed: %s', e)
        return api_error(str(e), code='KEY_CREATE_ERROR', status_code=500)


@api_v1_bp.route('/keys', methods=['GET'])
@require_api_key
def list_api_keys():
    """List API keys for the user."""
    uid = _resolve_scoped_user_id()
    if not uid:
        return api_error('Login or API authentication required', code='UNAUTHENTICATED', status_code=401)

    try:
        db = get_db()
        rows = db.execute(
            '''
            SELECT id, label, is_active, created_at, expires_at, last_used_at, call_count,
                   key_preview
            FROM   api_keys
            WHERE  user_id = ?
            ORDER  BY created_at DESC
            ''',
            (uid,),
        ).fetchall()
        res_keys = []
        for r in rows:
            d = dict(r)
            d['active'] = d.pop('is_active', 1)
            res_keys.append(d)
        return api_success({'keys': res_keys})
    except Exception as e:
        logger.exception('list_api_keys failed: %s', e)
        return api_error(str(e), code='KEY_LIST_ERROR', status_code=500)


@api_v1_bp.route('/keys/revoke', methods=['POST'])
@require_api_key
def revoke_api_key():
    """Revoke an API key by id."""
    uid = _resolve_scoped_user_id()
    if not uid:
        return api_error('Login or API authentication required', code='UNAUTHENTICATED', status_code=401)

    body = request.get_json(silent=True) or {}
    key_id = body.get('key_id')
    if not key_id:
        return api_error('key_id required', code='MISSING_KEY_ID', status_code=400)

    try:
        db = get_db()
        db.execute(
            'UPDATE api_keys SET is_active = 0, active = 0 WHERE id = ? AND user_id = ?',
            (key_id, uid),
        )
        db.commit()
        return api_success({'revoked': True})
    except Exception as e:
        logger.exception('revoke_api_key failed: %s', e)
        return api_error(str(e), code='KEY_REVOKE_ERROR', status_code=500)
