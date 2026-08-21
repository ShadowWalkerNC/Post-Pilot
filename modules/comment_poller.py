"""
modules/comment_poller.py
Background Poller for Meta (Facebook / Instagram) Social Comments.

Fetches recent comments from connected Meta accounts, classifies sentiment,
generates AI draft replies, and persists them into inbox_items.
"""

import logging
from typing import Dict, Any, List, Optional

from modules.db import get_connection, placeholder, USE_POSTGRES
from modules.auth_manager import load_token
from modules.meta_api import MetaAPI
from modules.models import InboxItem
from modules.reply_agent import analyze_and_draft

logger = logging.getLogger(__name__)


def _get_user_business_info(user_id: str) -> Dict[str, str]:
    """Retrieve business profile details (name, tone, type) for user."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        p = placeholder
        sql = f"SELECT business_name, full_name, email FROM users WHERE id = {p}"
        cur.execute(sql, (str(user_id),))
        row = cur.fetchone()
        if not row:
            return {'business_name': 'Our Business', 'tone': 'friendly', 'business_type': 'restaurant'}
        
        if isinstance(row, dict):
            biz = row.get('business_name') or row.get('full_name') or 'Our Business'
        else:
            biz = row[0] or row[1] or 'Our Business'
        return {
            'business_name': biz,
            'tone': 'friendly',
            'business_type': 'restaurant',
            'location': '',
        }
    except Exception as e:
        logger.debug("Could not fetch user profile: %s", e)
        return {'business_name': 'Our Business', 'tone': 'friendly', 'business_type': 'restaurant'}
    finally:
        conn.close()


def poll_user_comments(user_id: str) -> Dict[str, Any]:
    """
    Poll recent comments across Facebook & Instagram for a single user.
    Deduplicates comments, generates AI draft replies, and saves to inbox_items.
    """
    total_fetched = 0
    total_new = 0
    errors: List[str] = []

    user_info = _get_user_business_info(user_id)
    biz_name = user_info.get('business_name', 'Our Business')
    tone = user_info.get('tone', 'friendly')

    # 1. Facebook & Instagram via facebook token
    fb_token_rec = load_token('facebook', user_id)
    if fb_token_rec and fb_token_rec.get('access_token'):
        access_token = fb_token_rec['access_token']
        meta = fb_token_rec.get('meta') or {}
        page_id = meta.get('page_id') or ''
        ig_id = meta.get('ig_id') or ''

        api = MetaAPI(access_token=access_token, page_id=page_id, instagram_id=ig_id)

        # -------------------------------------------------------------
        # Facebook Posts & Comments
        # -------------------------------------------------------------
        if page_id:
            try:
                posts_res = api.get_page_posts(limit=10)
                posts_list = posts_res.get('data', []) if isinstance(posts_res, dict) else []
                for post in posts_list:
                    post_id = post.get('id')
                    post_msg = post.get('message') or post.get('story') or ''
                    if not post_id:
                        continue

                    comments_res = api.get_facebook_comments(post_id, limit=25)
                    comments = comments_res.get('data', []) if isinstance(comments_res, dict) else []
                    for c in comments:
                        total_fetched += 1
                        c_id = c.get('id')
                        c_text = c.get('message') or ''
                        if not c_id or not c_text.strip():
                            continue

                        existing = InboxItem.get_by_comment_id('fb', str(c_id), user_id=user_id)
                        if not existing:
                            from_data = c.get('from') or {}
                            author_id = from_data.get('id')
                            author_name = from_data.get('name') or 'Facebook User'
                            created_time = c.get('created_time')

                            # AI draft and sentiment
                            analysis = analyze_and_draft(
                                comment_text=c_text,
                                post_context=post_msg,
                                tone=tone,
                                business_name=biz_name,
                            )

                            InboxItem.create(
                                user_id=user_id,
                                platform='fb',
                                platform_post_id=post_id,
                                platform_comment_id=str(c_id),
                                author_id=str(author_id) if author_id else None,
                                author_name=author_name,
                                comment_text=c_text,
                                comment_time=created_time,
                                post_context=post_msg,
                                sentiment=analysis['sentiment'],
                                ai_draft_reply=analysis['ai_draft_reply'],
                                status=InboxItem.STATUS_PENDING,
                            )
                            total_new += 1
            except Exception as e:
                err_msg = f"Facebook comment polling error for user {user_id}: {str(e)}"
                logger.warning(err_msg)
                errors.append(err_msg)

        # -------------------------------------------------------------
        # Instagram Comments
        # -------------------------------------------------------------
        if ig_id:
            try:
                # Direct media or recent comments
                ig_comments_res = api.get_instagram_comments(ig_id, limit=25)
                ig_comments = ig_comments_res.get('data', []) if isinstance(ig_comments_res, dict) else []
                for c in ig_comments:
                    total_fetched += 1
                    c_id = c.get('id')
                    c_text = c.get('text') or ''
                    if not c_id or not c_text.strip():
                        continue

                    existing = InboxItem.get_by_comment_id('ig', str(c_id), user_id=user_id)
                    if not existing:
                        author_name = c.get('username') or 'Instagram User'
                        created_time = c.get('timestamp')

                        analysis = analyze_and_draft(
                            comment_text=c_text,
                            post_context=None,
                            tone=tone,
                            business_name=biz_name,
                        )

                        InboxItem.create(
                            user_id=user_id,
                            platform='ig',
                            platform_post_id=None,
                            platform_comment_id=str(c_id),
                            author_id=None,
                            author_name=author_name,
                            comment_text=c_text,
                            comment_time=created_time,
                            post_context=None,
                            sentiment=analysis['sentiment'],
                            ai_draft_reply=analysis['ai_draft_reply'],
                            status=InboxItem.STATUS_PENDING,
                        )
                        total_new += 1
            except Exception as e:
                err_msg = f"Instagram comment polling error for user {user_id}: {str(e)}"
                logger.warning(err_msg)
                errors.append(err_msg)

    return {
        'success': len(errors) == 0,
        'user_id': user_id,
        'fetched': total_fetched,
        'new': total_new,
        'errors': errors,
    }


def poll_all_active_users() -> Dict[str, Any]:
    """
    Poll comments for all users with connected Facebook/Instagram accounts.
    """
    conn = get_connection()
    user_ids: List[str] = []
    try:
        cur = conn.cursor()
        sql = "SELECT DISTINCT user_id FROM platform_tokens WHERE platform IN ('facebook', 'instagram')"
        cur.execute(sql)
        rows = cur.fetchall()
        for r in rows:
            uid = r['user_id'] if isinstance(r, dict) else r[0]
            if uid:
                user_ids.append(str(uid))
    except Exception as e:
        logger.error("Failed to query active platform users: %s", e)
        return {'success': False, 'error': str(e), 'users_polled': 0, 'total_new_comments': 0}
    finally:
        conn.close()

    total_new = 0
    all_errors: List[str] = []

    for uid in user_ids:
        res = poll_user_comments(uid)
        total_new += res.get('new', 0)
        all_errors.extend(res.get('errors', []))

    logger.info("poll_all_active_users: %d users polled, %d new comments ingested", len(user_ids), total_new)

    return {
        'success': True,
        'users_polled': len(user_ids),
        'total_new_comments': total_new,
        'errors': all_errors,
    }
