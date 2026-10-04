"""
blueprints/api.py
All /api/* endpoints: publish, generate, schedule, history,
analytics, business profile, connection status, token setup,
platform settings (toggles).

Option B flow:
    POST /api/generate
        → returns { master, adapted: {fb, ig, tt, ...} }
    Dashboard pre-fills per-platform editable textareas.
    User edits any/all, clicks Publish.
    POST /api/push_all  { captions: {fb: '...', ig: '...'}, platforms: [...] }
        → each platform receives its own adapted text.
"""

import json
import logging

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from modules.post_generator   import SocialMediaPostGenerator
from modules.post_scheduler    import PostScheduler
from modules.analytics_client  import Analytics
from modules.publisher         import UniversalPublisher
from modules.user_manager      import UserManager
from modules.plan_guard        import require_plan, check_platform_limit, check_post_limit
from modules.validator         import validate_post_input
from modules.database          import get_db
from blueprints.utils          import _uid, _get_tokens

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enforce_platform_limit(tier, platforms):
    if not platforms:
        return True, None
    allowed, limit = check_platform_limit(tier, platforms)
    if not allowed:
        return False, (jsonify({
            'success': False,
            'error': f'Your plan allows up to {limit} platform(s) at once. Upgrade at /billing.'
        }), 403)
    return True, None


def _enforce_post_limit(uid, tier):
    used = UserManager.count_posts_this_month(uid)
    allowed, limit = check_post_limit(tier, used)
    if not allowed:
        return False, (jsonify({
            'success': False,
            'error': {
                'code': 'POST_LIMIT',
                'message': f'Your plan allows {limit} posts this month. Upgrade at /billing.',
                'upgrade_url': '/billing',
            }
        }), 403)
    return True, None


def _validate_or_400(data: dict):
    ok, errors = validate_post_input(
        caption      = data.get('caption', ''),
        content_type = data.get('content_type', 'text'),
        platforms    = data.get('platforms'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        link_url     = data.get('link_url'),
    )
    if not ok:
        return jsonify({'success': False, 'errors': errors}), 400
    return None


def _get_business_profile() -> dict:
    profile = getattr(current_user, 'business_profile', None)
    if isinstance(profile, str):
        try:
            return json.loads(profile)
        except Exception:
            return {}
    return profile or {}


def _get_enabled_platforms(uid: str) -> dict:
    try:
        db   = get_db()
        rows = db.execute(
            'SELECT platform, enabled FROM platform_settings WHERE user_id = ?', (uid,)
        ).fetchall()
        if not rows:
            return {}
        return {row['platform']: bool(row['enabled']) for row in rows}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Generate (Option B)
# ---------------------------------------------------------------------------

@api_bp.route('/api/generate', methods=['POST'])
@login_required
@require_plan('starter')
def api_generate():
    data         = request.json or {}
    uid          = _uid()
    tone         = data.get('tone', 'friendly')
    content_type = data.get('content_type', 'general')
    keywords     = data.get('keywords', [])
    profile      = _get_business_profile()
    enabled      = _get_enabled_platforms(uid)
    platforms    = data.get('platforms') or [p for p, on in enabled.items() if on] or None
    try:
        from modules.ai_generator import generate_with_adaptations
        result = generate_with_adaptations(
            business_info = profile,
            content_type  = content_type,
            tone          = tone,
            keywords      = keywords,
            platforms     = platforms,
        )
        return jsonify({'success': True, **result})
    except Exception:
        logger.exception('api_generate failed for user %s', uid)
        return jsonify({'success': False, 'error': 'Caption generation failed'}), 500


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

@api_bp.route('/api/push_all', methods=['POST'])
@login_required
@require_plan('starter')
def api_push_all():
    data     = request.json or {}
    uid      = _uid()
    caption  = data.get('caption') or next(iter(data.get('captions', {}).values()), '')
    captions = data.get('captions')
    err      = _validate_or_400({**data, 'caption': caption})
    if err:
        return err
    platforms = data.get('platforms') or []
    ok, limit_err = _enforce_platform_limit(current_user.subscription_tier, platforms)
    if not ok:
        return limit_err
    ok, limit_err = _enforce_post_limit(uid, current_user.subscription_tier)
    if not ok:
        return limit_err
    tokens    = _get_tokens(uid)
    publisher = UniversalPublisher(tokens, user_id=uid)
    results   = publisher.push_all(
        caption       = caption,
        captions      = captions,
        content_type  = data.get('content_type', 'text'),
        image_url     = data.get('image_url'),
        video_url     = data.get('video_url'),
        link_url      = data.get('link_url'),
        platforms     = platforms,
        schedule_time = data.get('schedule_time'),
        web_data      = data.get('web_data'),
    )
    UserManager.log_post(
        user_id      = uid,
        caption      = caption,
        content_type = data.get('content_type', 'text'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        platforms    = platforms,
        results      = results,
        scheduled_at = data.get('schedule_time'),
        status       = 'scheduled' if data.get('schedule_time') else 'published',
    )
    return jsonify({'success': True, 'results': results})


@api_bp.route('/api/publish', methods=['POST'])
@api_bp.route('/api/publish_post', methods=['POST'])
@login_required
@require_plan('starter')
def api_publish():
    data     = request.json or {}
    uid      = _uid()
    caption  = data.get('caption') or next(iter(data.get('captions', {}).values()), '')
    captions = data.get('captions')
    err      = _validate_or_400({**data, 'caption': caption})
    if err:
        return err
    platforms = data.get('platforms') or []
    ok, limit_err = _enforce_platform_limit(current_user.subscription_tier, platforms)
    if not ok:
        return limit_err
    ok, limit_err = _enforce_post_limit(uid, current_user.subscription_tier)
    if not ok:
        return limit_err
    tokens    = _get_tokens(uid)
    publisher = UniversalPublisher(tokens, user_id=uid)
    results   = publisher.push_all(
        caption      = caption,
        captions     = captions,
        content_type = data.get('content_type', 'text'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        link_url     = data.get('link_url'),
        platforms    = platforms,
    )
    UserManager.log_post(
        user_id      = uid,
        caption      = caption,
        content_type = data.get('content_type', 'text'),
        image_url    = data.get('image_url'),
        video_url    = data.get('video_url'),
        platforms    = platforms,
        results      = results,
    )
    return jsonify({'success': True, 'results': results})


# ---------------------------------------------------------------------------
# Platform toggle settings
# ---------------------------------------------------------------------------

@api_bp.route('/api/platform_settings', methods=['GET'])
@login_required
def api_get_platform_settings():
    uid      = _uid()
    settings = _get_enabled_platforms(uid)
    if not settings:
        from modules.publisher import KEY_MAP
        settings = {v: True for v in set(KEY_MAP.values())}
    return jsonify({'success': True, 'settings': settings})


@api_bp.route('/api/platform_settings', methods=['POST'])
@login_required
def api_save_platform_settings():
    data     = request.json or {}
    uid      = _uid()
    settings = data.get('settings', {})
    if not isinstance(settings, dict):
        return jsonify({'success': False, 'error': 'settings must be an object'}), 400
    try:
        db = get_db()
        for platform, enabled in settings.items():
            db.execute(
                'INSERT INTO platform_settings (user_id, platform, enabled) VALUES (?, ?, ?) '
                'ON CONFLICT(user_id, platform) DO UPDATE SET enabled = excluded.enabled',
                (uid, str(platform), 1 if enabled else 0)
            )
        db.commit()
        return jsonify({'success': True})
    except Exception:
        logger.exception('api_save_platform_settings failed for user %s', uid)
        return jsonify({'success': False, 'error': 'Failed to save settings'}), 500


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------

@api_bp.route('/api/connection_status', methods=['GET', 'POST'])
@login_required
def api_connection_status():
    tokens = _get_tokens(_uid())
    status = {
        'fb':  bool(tokens.get('facebook_token') and tokens.get('facebook_page_id')),
        'ig':  bool(tokens.get('instagram_token') and tokens.get('instagram_id')),
        'yt':  bool(tokens.get('youtube_token')),
        'yts': bool(tokens.get('youtube_token')),
        'tt':  bool(tokens.get('tiktok_token')),
        'gb':  bool(tokens.get('google_token')),
        'li':  bool(tokens.get('linkedin_token')),
        'tw':  bool(tokens.get('twitter_token')),
        'pi':  bool(tokens.get('pinterest_token')),
        'web': True,
    }
    return jsonify({'success': True, 'platforms': status, 'connections': status})


# ---------------------------------------------------------------------------
# Business profile
# ---------------------------------------------------------------------------

@api_bp.route('/api/setup_business', methods=['POST'])
@login_required
def api_setup_business():
    data = request.json or {}
    uid  = _uid()
    info = data.get('business_info', {})
    gen  = SocialMediaPostGenerator()
    gen.setup_business(info)
    UserManager.save_business_profile(uid, info)
    return jsonify({'success': True})


@api_bp.route('/api/get_business', methods=['GET'])
@login_required
def api_get_business():
    return jsonify({'success': True, 'business_info': _get_business_profile()})


@api_bp.route('/api/onboarding/setup', methods=['POST'])
@login_required
def api_onboarding_setup():
    data = request.json or {}
    business_info = {
        'name':          data.get('name', ''),
        'business_type': data.get('type', ''),
        'location':      data.get('location', ''),
        'hours':         data.get('hours', ''),
        'prompt_time':   data.get('prompt_time', '07:00'),
    }
    UserManager.save_business_profile(_uid(), business_info)
    return jsonify({'success': True, 'business': business_info})


# ---------------------------------------------------------------------------
# Token setup
# ---------------------------------------------------------------------------

@api_bp.route('/api/setup_tokens', methods=['POST'])
@login_required
def api_setup_tokens():
    # Disabled: raw token injection is a CSRF/XSS hazard.
    # Connect platforms via OAuth routes under /auth/* instead.
    return jsonify({
        'success': False,
        'error': {
            'code': 'GONE',
            'message': 'Use Connect Platforms (OAuth) instead of posting tokens directly.',
            'connect_url': '/connect',
        }
    }), 410


# ---------------------------------------------------------------------------
# Generate (legacy)
# ---------------------------------------------------------------------------

@api_bp.route('/api/generate_weekly', methods=['POST'])
@api_bp.route('/api/generate_posts', methods=['POST'])
@login_required
@require_plan('starter')
def api_generate_weekly():
    profile = _get_business_profile()
    gen = SocialMediaPostGenerator()
    if profile:
        gen.setup_business(profile)
    schedule = gen.generate_weekly_schedule()
    posts    = schedule if isinstance(schedule, list) else schedule.get('posts', [])
    return jsonify({'success': True, 'posts': posts, 'schedule': schedule})


@api_bp.route('/api/generate_post', methods=['POST'])
@api_bp.route('/api/generate_single', methods=['POST'])
@login_required
@require_plan('starter')
def api_generate_post():
    data         = request.json or {}
    template     = data.get('template')
    content_type = data.get('content_type', 'general')
    platform     = data.get('platform', 'facebook')
    tone         = data.get('tone', 'friendly')
    keywords     = data.get('keywords', [])

    # If caller specifically asked for an explicit legacy template name
    if template:
        gen = SocialMediaPostGenerator()
        profile = _get_business_profile()
        if profile:
            gen.setup_business(profile)
        try:
            post = gen.generate_post(template)
            return jsonify({'success': True, 'post': post})
        except Exception:
            logger.exception('generate_post failed for template %s', template)
            return jsonify({'success': False, 'error': 'Post generation failed'}), 500

    # Otherwise route through real AI generator (LLM gateway with template fallback)
    from modules.ai_generator import generate_caption
    profile = _get_business_profile()
    try:
        caption = generate_caption(
            business_info = profile,
            content_type  = content_type,
            tone          = tone,
            keywords      = keywords,
            platform      = platform if platform in ('facebook', 'instagram', 'tiktok', 'youtube', 'google', 'website') else 'facebook',
        )
        return jsonify({'success': True, 'post': {'caption': caption, 'platform': platform, 'type': content_type}})
    except Exception:
        logger.exception('generate_single failed for user %s', _uid())
        return jsonify({'success': False, 'error': 'Caption generation failed'}), 500


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@api_bp.route('/api/schedule_post', methods=['POST'])
@login_required
@require_plan('starter')
def api_schedule_post():
    return jsonify(PostScheduler().schedule(request.json))


@api_bp.route('/api/scheduled_posts', methods=['GET'])
@login_required
def api_scheduled_posts():
    from modules.database import get_db
    uid = _uid()
    db  = get_db()
    try:
        rows = db.execute(
            'SELECT * FROM post_history WHERE user_id = ? AND status = "scheduled" '
            'ORDER BY scheduled_at ASC', (uid,)
        ).fetchall()
        posts = [{
            'id':             row['id'],
            'caption':        row['caption'],
            'platforms':      json.loads(row['platforms'] or '[]'),
            'status':         row['status'],
            'scheduled_date': row['scheduled_at'],
            'time':           '',
        } for row in rows]
    except Exception:
        logger.exception('api_scheduled_posts failed for user %s', uid)
        posts = []
    return jsonify({'success': True, 'posts': posts})


@api_bp.route('/api/post_history', methods=['GET'])
@login_required
def api_post_history():
    from modules.database import get_db
    uid = _uid()
    db  = get_db()
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
    except (ValueError, TypeError):
        limit = 20
    try:
        rows = db.execute(
            'SELECT * FROM post_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
            (uid, limit)
        ).fetchall()
        posts = [{
            'id':           row['id'],
            'caption':      row['caption'],
            'content_type': row['content_type'],
            'image_url':    row['image_url'],
            'platforms':    json.loads(row['platforms'] or '[]'),
            'status':       row['status'],
            'scheduled_at': row['scheduled_at'],
            'created_at':   row['created_at'],
            'results':      json.loads(row['results'] or '{}'),
        } for row in rows]
    except Exception:
        logger.exception('api_post_history failed for user %s', uid)
        return jsonify({'success': False, 'error': 'Could not load history', 'posts': []})
    return jsonify({'success': True, 'posts': posts, 'count': len(posts)})


@api_bp.route('/api/bulk_schedule', methods=['POST'])
@login_required
@require_plan('pro')
def api_bulk_schedule():
    data  = request.json or {}
    uid   = _uid()
    posts = data.get('posts', [])
    for p in posts:
        UserManager.log_post(
            user_id      = uid,
            caption      = p.get('caption', ''),
            content_type = 'text',
            platforms    = p.get('platforms'),
            results      = {},
            scheduled_at = p.get('scheduled_date'),
            status       = 'scheduled',
        )
    return jsonify({'success': True, 'count': len(posts)})


@api_bp.route('/api/delete_post', methods=['POST'])
@login_required
def api_delete_post():
    from modules.database import get_db
    data    = request.json or {}
    post_id = data.get('post_id')
    uid     = _uid()
    if post_id:
        db = get_db()
        try:
            db.execute('DELETE FROM post_history WHERE id = ? AND user_id = ?', (post_id, uid))
            db.commit()
        except Exception:
            logger.exception('api_delete_post failed for post %s user %s', post_id, uid)
            return jsonify({'success': False, 'error': 'Delete failed'})
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Analytics  (Facebook + Instagram + Google Business + YouTube)
# ---------------------------------------------------------------------------

@api_bp.route('/api/analytics', methods=['GET', 'POST'])
@login_required
@require_plan('starter')
def api_analytics():
    """
    Combined Facebook + Instagram + Google Business + YouTube analytics.
    GET  /api/analytics?days=30
    POST /api/analytics  { days: 30 }
    """
    uid    = _uid()
    data   = request.json or {}
    tokens = _get_tokens(uid)

    try:
        days = int(request.args.get('days') or data.get('days') or 30)
        days = max(1, min(days, 90))
    except (ValueError, TypeError):
        days = 30

    token   = tokens.get('facebook_token')
    page_id = tokens.get('facebook_page_id')
    ig_id   = tokens.get('instagram_id')

    # ── Facebook / Instagram ──────────────────────────────────────────
    if not token or not page_id:
        fb_result = {
            'success': False,
            'error':   'Facebook not connected — visit Settings to connect',
            'kpis':    {'posts': 0, 'reach': 0, 'likes': 0, 'engaged': 0, 'eng_rate': 0.0},
            'chart':   {'labels': [], 'reach': [], 'engaged': []},
            'ig':      {},
            'posts':   [],
        }
    else:
        try:
            fb_result = Analytics(token, page_id, ig_id=ig_id).get_combined_summary(days=days)
        except Exception:
            logger.exception('api_analytics FB failed for user %s', uid)
            fb_result = {
                'success': False, 'error': 'Analytics fetch failed',
                'kpis': {'posts': 0, 'reach': 0, 'likes': 0, 'engaged': 0, 'eng_rate': 0.0},
                'chart': {'labels': [], 'reach': [], 'engaged': []},
                'ig': {}, 'posts': [],
            }

    # ── Google Business + YouTube ─────────────────────────────────────
    google_result = {}
    if tokens.get('google_token'):
        try:
            google_result = Analytics.get_google_youtube_summary(
                user_id     = uid,
                location_id = tokens.get('google_location_id', ''),
                days        = days,
            )
        except Exception:
            logger.exception('api_analytics Google/YT failed for user %s', uid)

    return jsonify({**fb_result, 'google': google_result})


# ---------------------------------------------------------------------------
# POST /api/location/one_tap — Food truck one-tap location post
# ---------------------------------------------------------------------------

@api_bp.route('/api/location/one_tap', methods=['POST'])
@login_required
def api_one_tap_location():

    """
    Accepts GPS coordinates ({ lat, lng }) or address string ({ address }).
    Generates location-aware captions across platforms, updates website banner,
    and optionally publishes immediately to connected networks.
    """
    uid  = _uid()
    tier = getattr(current_user, 'plan', 'free')
    data = request.get_json(silent=True) or {}

    loc_input = {}
    if 'lat' in data and 'lng' in data:
        try:
            loc_input['lat'] = float(data['lat'])
            loc_input['lng'] = float(data['lng'])
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid latitude or longitude'}), 400
    elif 'address' in data and str(data['address']).strip():
        loc_input['address'] = str(data['address']).strip()
    else:
        return jsonify({'success': False, 'error': 'Must provide lat/lng or address'}), 400

    from modules.location_service import one_tap_location_post
    biz = UserManager.get_business_profile(uid) or {}
    business_info = {
        'name':    biz.get('business_name') or getattr(current_user, 'business_name', 'Our Business'),
        'hours':   biz.get('hours') or 'today',
        'special': data.get('special') or biz.get('special') or '',
        'type':    biz.get('business_type') or 'food truck',
    }

    try:
        post_payload = one_tap_location_post(business_info, loc_input)
        if not post_payload.get('ready'):
            return jsonify({'success': False, 'error': post_payload.get('error') or 'Failed to prepare post'}), 400

        # Optional immediate publish if requested
        should_publish = bool(data.get('publish_now', False))
        publish_results = {}
        if should_publish:
            tokens = _get_tokens(uid)
            platforms = data.get('platforms') or ['facebook', 'instagram']
            ok, err_resp = _enforce_platform_limit(tier, platforms)
            if not ok:
                return err_resp

            ok, err_resp = _enforce_post_limit(uid, tier)
            if not ok:
                return err_resp

            publisher = UniversalPublisher(tokens=tokens)
            captions = post_payload.get('captions', {})
            publish_results = publisher.publish_to_all(
                text=captions.get('facebook') or captions.get('website', ''),
                adapted_captions=captions,
                platforms=platforms,
            )
            # Log to post history
            try:
                for plat, p_res in publish_results.items():
                    if p_res.get('success'):
                        UserManager.log_post(
                            user_id=uid,
                            platform=plat,
                            content=captions.get(plat, ''),
                            status='published',
                            post_id=p_res.get('id') or p_res.get('post_id'),
                        )
            except Exception as log_err:
                logger.warning('Failed to log published location post: %s', log_err)

        return jsonify({
            'success': True,
            'payload': post_payload,
            'published': should_publish,
            'publish_results': publish_results,
        }), 200

    except Exception as e:
        logger.exception('one_tap_location failed for user %s: %s', uid, e)
        return jsonify({'success': False, 'error': str(e)}), 500

