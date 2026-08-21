"""
blueprints/inbox.py
AI Social Comment Inbox & Auto-Reply Moderation Endpoints.

Routes:
  GET  /inbox                         -- Dashboard moderation view (Starter+)
  GET  /api/inbox/items               -- List items with filters (Starter+)
  GET  /api/inbox/stats               -- Statistics / counts (Starter+)
  POST /api/inbox/poll_now            -- On-demand comment polling trigger (Starter+)
  POST /api/inbox/<item_id>/reply     -- Send reply via Meta Graph API (Pro+)
  POST /api/inbox/<item_id>/regenerate-- Regenerate AI draft reply with tone (Pro+)
  POST /api/inbox/<item_id>/hide      -- Hide comment on platform (Pro+)
  POST /api/inbox/<item_id>/skip      -- Skip / archive comment (Starter+)
"""

import logging
from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user

from blueprints.utils import _uid, _business_name, _get_tokens
from modules.plan_guard import require_plan, _plan_rank
from modules.models import InboxItem
from modules.meta_api import MetaAPI
from modules.reply_agent import analyze_and_draft, TONES, SENTIMENTS
from modules.comment_poller import poll_user_comments

inbox_bp = Blueprint('inbox', __name__)
logger = logging.getLogger(__name__)


def _get_user_stats(uid: str) -> dict:
    """Calculate summary stats for the user's comment inbox."""
    pending = InboxItem.count_by_user(uid, status=InboxItem.STATUS_PENDING)
    approved = InboxItem.count_by_user(uid, status=InboxItem.STATUS_APPROVED)
    auto_replied = InboxItem.count_by_user(uid, status=InboxItem.STATUS_AUTO_REPLIED)
    hidden = InboxItem.count_by_user(uid, status=InboxItem.STATUS_HIDDEN)
    skipped = InboxItem.count_by_user(uid, status=InboxItem.STATUS_SKIPPED)
    total = InboxItem.count_by_user(uid)

    pos = InboxItem.count_by_user(uid, sentiment=InboxItem.SENTIMENT_POSITIVE)
    q = InboxItem.count_by_user(uid, sentiment=InboxItem.SENTIMENT_QUESTION)
    neg = InboxItem.count_by_user(uid, sentiment=InboxItem.SENTIMENT_NEGATIVE)
    neu = InboxItem.count_by_user(uid, sentiment=InboxItem.SENTIMENT_NEUTRAL)
    spam = InboxItem.count_by_user(uid, sentiment=InboxItem.SENTIMENT_SPAM)

    return {
        'pending': pending,
        'approved': approved,
        'auto_replied': auto_replied,
        'replied': approved + auto_replied,
        'hidden': hidden,
        'skipped': skipped,
        'total': total,
        'sentiment': {
            'positive': pos,
            'question': q,
            'negative': neg,
            'neutral': neu,
            'spam': spam,
        }
    }


# ---------------------------------------------------------------------------
# Page: /inbox
# ---------------------------------------------------------------------------

@inbox_bp.route('/inbox', methods=['GET'])
@login_required
@require_plan('starter')
def inbox_page():
    uid = _uid()
    status_filter = request.args.get('status')
    sentiment_filter = request.args.get('sentiment')
    platform_filter = request.args.get('platform')

    # If no status filter requested, default to 'pending'
    active_status = status_filter if status_filter is not None else InboxItem.STATUS_PENDING
    if active_status == 'all':
        query_status = None
    else:
        query_status = active_status

    items = InboxItem.list_by_user(
        user_id=uid,
        status=query_status,
        sentiment=sentiment_filter or None,
        platform=platform_filter or None,
        limit=100,
        offset=0,
    )
    stats = _get_user_stats(uid)

    user_tier = getattr(current_user, 'subscription_tier', 'free') or getattr(current_user, 'plan', 'free') or 'free'
    tier_label = f"{user_tier.title()} Plan"
    is_pro = _plan_rank(user_tier) >= _plan_rank('pro')

    return render_template(
        'inbox.html',
        items=items,
        stats=stats,
        selected_status=active_status,
        selected_sentiment=sentiment_filter or '',
        selected_platform=platform_filter or '',
        business_name=_business_name(),
        tier_label=tier_label,
        is_pro=is_pro,
        tones=TONES,
    )


# ---------------------------------------------------------------------------
# API: List & Stats
# ---------------------------------------------------------------------------

@inbox_bp.route('/api/inbox/items', methods=['GET'])
@login_required
@require_plan('starter')
def api_list_inbox_items():
    uid = _uid()
    status = request.args.get('status')
    if status == 'all':
        status = None
    sentiment = request.args.get('sentiment') or None
    platform = request.args.get('platform') or None
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    items = InboxItem.list_by_user(
        user_id=uid,
        status=status,
        sentiment=sentiment,
        platform=platform,
        limit=limit,
        offset=offset,
    )
    total = InboxItem.count_by_user(
        user_id=uid,
        status=status,
        sentiment=sentiment,
        platform=platform,
    )
    return jsonify({
        'success': True,
        'items': [i.to_dict() for i in items],
        'total': total,
    })


@inbox_bp.route('/api/inbox/stats', methods=['GET'])
@login_required
@require_plan('starter')
def api_inbox_stats():
    uid = _uid()
    stats = _get_user_stats(uid)
    return jsonify({'success': True, 'stats': stats})


# ---------------------------------------------------------------------------
# API: On-demand Polling
# ---------------------------------------------------------------------------

@inbox_bp.route('/api/inbox/poll_now', methods=['POST'])
@login_required
@require_plan('starter')
def api_poll_now():
    uid = _uid()
    result = poll_user_comments(uid)
    return jsonify({'success': True, 'result': result})


# ---------------------------------------------------------------------------
# API: Moderation Actions (Reply, Regenerate, Hide, Skip)
# ---------------------------------------------------------------------------

@inbox_bp.route('/api/inbox/<int:item_id>/reply', methods=['POST'])
@login_required
@require_plan('pro')
def api_reply_item(item_id: int):
    uid = _uid()
    item = InboxItem.get_by_id(item_id, user_id=uid)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    reply_text = data.get('reply_text', '').strip()
    if not reply_text:
        return jsonify({'success': False, 'error': 'Reply text is required'}), 400

    # Publish reply to platform via Meta Graph API
    tokens = _get_tokens(uid)
    fb_token = tokens.get('facebook_token')
    ig_token = tokens.get('instagram_token') or fb_token
    page_id = tokens.get('facebook_page_id', '')
    ig_id = tokens.get('instagram_id', '')

    access_token = fb_token or ig_token or 'dummy'
    meta_api = MetaAPI(access_token=access_token, page_id=page_id, instagram_id=ig_id)

    try:
        if item.platform in ('fb', 'facebook'):
            meta_api.reply_to_facebook_comment(item.platform_comment_id, reply_text)
        elif item.platform in ('ig', 'instagram'):
            meta_api.reply_to_instagram_comment(item.platform_comment_id, reply_text)
    except Exception as e:
        logger.warning("Meta API reply failed: %s", e)

    InboxItem.mark_replied(item_id, uid, final_reply=reply_text, auto_replied=False)
    updated = InboxItem.get_by_id(item_id, user_id=uid)

    return jsonify({
        'success': True,
        'message': 'Reply sent successfully',
        'item': updated.to_dict() if updated else None,
    })


@inbox_bp.route('/api/inbox/<int:item_id>/regenerate', methods=['POST'])
@login_required
@require_plan('pro')
def api_regenerate_draft(item_id: int):
    uid = _uid()
    item = InboxItem.get_by_id(item_id, user_id=uid)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    tone = data.get('tone') or 'friendly'

    analysis = analyze_and_draft(
        comment_text=item.comment_text,
        post_context=item.post_context,
        tone=tone,
        business_name=_business_name(),
    )

    new_draft = analysis.get('ai_draft_reply', '')
    InboxItem.update_draft(item_id, uid, new_draft)

    return jsonify({
        'success': True,
        'ai_draft_reply': new_draft,
        'sentiment': analysis.get('sentiment', item.sentiment),
        'tone': tone,
    })


@inbox_bp.route('/api/inbox/<int:item_id>/hide', methods=['POST'])
@login_required
@require_plan('pro')
def api_hide_item(item_id: int):
    uid = _uid()
    item = InboxItem.get_by_id(item_id, user_id=uid)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    tokens = _get_tokens(uid)
    access_token = tokens.get('facebook_token') or tokens.get('instagram_token') or 'dummy'
    page_id = tokens.get('facebook_page_id', '')
    ig_id = tokens.get('instagram_id', '')

    meta_api = MetaAPI(access_token=access_token, page_id=page_id, instagram_id=ig_id)

    try:
        if item.platform in ('fb', 'facebook'):
            meta_api.hide_facebook_comment(item.platform_comment_id, is_hidden=True)
        elif item.platform in ('ig', 'instagram'):
            meta_api.hide_instagram_comment(item.platform_comment_id, hide=True)
    except Exception as e:
        logger.warning("Meta API hide comment failed: %s", e)

    InboxItem.mark_hidden(item_id, uid)
    updated = InboxItem.get_by_id(item_id, user_id=uid)

    return jsonify({
        'success': True,
        'message': 'Comment hidden',
        'item': updated.to_dict() if updated else None,
    })


@inbox_bp.route('/api/inbox/<int:item_id>/skip', methods=['POST'])
@login_required
@require_plan('starter')
def api_skip_item(item_id: int):
    uid = _uid()
    item = InboxItem.get_by_id(item_id, user_id=uid)
    if not item:
        return jsonify({'success': False, 'error': 'Item not found'}), 404

    InboxItem.mark_skipped(item_id, uid)
    updated = InboxItem.get_by_id(item_id, user_id=uid)

    return jsonify({
        'success': True,
        'message': 'Comment skipped',
        'item': updated.to_dict() if updated else None,
    })
