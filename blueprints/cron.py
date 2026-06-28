"""
blueprintsicron.py
Vercel Cron Job endpoints for Post-Pilot.

Endpoints:
  POST /api/cron/publish   -- runs every minute; publishes due scheduled posts
  POST /api/cron/generate  -- runs every hour; generates and schedules new posts
  GET  /api/cron/health    -- liveness check (no auth required)

Security:
  All POST requests must carry:
    Authorization: Bearer <CRON_SECRET>
  Vercel automatically injects this header on cron invocations.
  Unauthenticated requests receive 401.

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
# POST /api/cron/publish
# Runs every minute (vercel.json). Publishes all due scheduled posts.
# ---------------------------------------------------------------------------

@cron_bp.route('/publish', methods=['POST'])
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
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/cron/generate
# Runs every hour (vercel.json). Generates and schedules new posts for all
# users whose business profiles are complete.
# ---------------------------------------------------------------------------

@cron_bp.route('/generate', methods=['POST'])
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
        return jsonify({'success': False, 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/cron/health
# Lightweight liveness check (no auth required).
# ---------------------------------------------------------------------------

@cron_bp.route('/health', methods=['GET'])
def cron_health():
    return jsonify({
        'status':    'ok',
        'endpoints': {
            'publish':  '/api/cron/publish  (POST, every minute)',
            'generate': '/api/cron/generate (POST, every hour)',
        },
    }), 200
