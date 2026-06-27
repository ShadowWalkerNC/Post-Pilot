"""
blueprintsicron.py
Vercel Cron Job endpoint for Post-Pilot.

Vercel calls POST /api/cron/publish every minute (configured in vercel.json).
This replaces the APScheduler background thread, which cannot run persistently
on Vercel's serverless platform.

Security:
  All requests must carry the Authorization header:
    Authorization: Bearer <CRON_SECRET>
  Vercel automatically injects this header when invoking cron jobs.
  Unauthenticated requests receive 401. The secret never appears in code.

Usage:
  Set CRON_SECRET in your Vercel environment variables.
  Vercel will pass it automatically -- you never call this endpoint manually.

Reference:
  https://vercel.com/docs/cron-jobs
"""

import os
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
    # Constant-time comparison to prevent timing attacks
    import hmac
    return hmac.compare_digest(auth_header, expected)


@cron_bp.route('/publish', methods=['POST'])
def publish_due_posts():
    """
    Called by Vercel Cron every minute.
    Publishes all scheduled posts whose scheduled_at <= now().
    """
    if not _verify_cron_secret():
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    try:
        from modules.scheduler_worker import _publish_scheduled_posts
        _publish_scheduled_posts()
        logger.info('cron: publish_due_posts completed')
        return jsonify({'success': True}), 200
    except Exception as e:
        logger.error('cron: publish_due_posts failed: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@cron_bp.route('/health', methods=['GET'])
def cron_health():
    """Lightweight liveness check for the cron blueprint (no auth required)."""
    return jsonify({'status': 'ok', 'endpoint': '/api/cron/publish'}), 200
