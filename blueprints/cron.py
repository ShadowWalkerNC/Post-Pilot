"""
blueprints/cron.py
Vercel Cron Job endpoints for Post-Pilot.

Endpoints:
  GET|POST /api/cron/publish        -- every minute; publishes due scheduled posts
  GET|POST /api/cron/generate       -- every hour; generates and schedules new posts
  GET|POST /api/cron/poll_comments  -- periodic comment poller & AI reply drafter (M3)
  GET      /api/cron/health         -- liveness check (no auth required)

Security:
  publish/generate/poll_comments must carry:
    Authorization: Bearer <CRON_SECRET>
  Vercel Cron invokes GET and injects this header automatically.

Reference:
  https://vercel.com/docs/cron-jobs
"""

import os
import hmac
import logging

from flask import Blueprint, request, jsonify

cron_bp = Blueprint('cron', __name__, url_prefix='/api/cron')

logger = logging.getLogger(__name__)

_CRON_SECRET = os.getenv('CRON_SECRET', '')


def _verify_cron_secret() -> bool:
    """
    Validate the Authorization header sent by Vercel.
    Returns True only when the header matches CRON_SECRET.
    Always returns False when CRON_SECRET is unset (safe default).
    """
    if not _CRON_SECRET:
        logger.warning('cron: CRON_SECRET is not set -- all cron requests rejected')
        return False
    auth_header = request.headers.get('Authorization', '')
    expected    = f'Bearer {_CRON_SECRET}'
    return hmac.compare_digest(auth_header, expected)


# ---------------------------------------------------------------------------
# /api/cron/publish — Vercel Cron uses GET; POST kept for manual ops
# ---------------------------------------------------------------------------

@cron_bp.route('/publish', methods=['GET', 'POST'])
def publish_due_posts():
    if not _verify_cron_secret():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    try:
        from modules.scheduler_worker import _publish_scheduled_posts
        _publish_scheduled_posts()
        logger.info('cron/publish: completed')
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error('cron/publish: failed: %s', e)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ---------------------------------------------------------------------------
# /api/cron/generate
# ---------------------------------------------------------------------------

@cron_bp.route('/generate', methods=['GET', 'POST'])
def generate_scheduled_posts():
    if not _verify_cron_secret():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    try:
        from modules.automation_agent import run_for_all_users
        summary = run_for_all_users()
        logger.info('cron/generate: %s', summary)
        return jsonify({'success': True, 'summary': summary}), 200
    except Exception as e:
        logger.error('cron/generate: failed: %s', e)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ---------------------------------------------------------------------------
# /api/cron/poll_comments (M3)
# ---------------------------------------------------------------------------

@cron_bp.route('/poll_comments', methods=['GET', 'POST'])
def poll_social_comments():
    if not _verify_cron_secret():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    try:
        from modules.comment_poller import poll_all_active_users
        summary = poll_all_active_users()
        logger.info('cron/poll_comments: %s', summary)
        return jsonify({'success': True, 'summary': summary}), 200
    except Exception as e:
        logger.error('cron/poll_comments: failed: %s', e)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ---------------------------------------------------------------------------
# GET /api/cron/health
# ---------------------------------------------------------------------------

@cron_bp.route('/health', methods=['GET'])
def cron_health():
    return jsonify({
        'status':    'ok',
        'endpoints': {
            'publish':       '/api/cron/publish (GET|POST, every minute)',
            'generate':      '/api/cron/generate (GET|POST, every hour)',
            'poll_comments': '/api/cron/poll_comments (GET|POST, periodic poller)',
        },
    }), 200
