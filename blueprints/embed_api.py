"""
blueprints/embed_api.py
Public (no auth required) embed API endpoint.

GET /api/embed/<slug>
    Returns JSON with the business's public data:
    name, tagline, logo_url, hours, services, recent_posts.
    Used by static/embed.js to populate widgets on external sites.
"""

import json
import logging

from flask import Blueprint, jsonify

embed_bp = Blueprint('embed', __name__)
logger   = logging.getLogger(__name__)


@embed_bp.route('/api/embed/<slug>', methods=['GET'])
def public_embed(slug):
    """
    Public endpoint — no login required.
    Slug is matched against users.embed_slug (falls back to username).
    """
    from modules.database import get_db
    db = get_db()

    # ── Look up the user by embed_slug or username ────────────────────
    user_row = None
    try:
        user_row = db.execute(
            'SELECT id FROM users WHERE embed_slug = ? OR username = ? LIMIT 1',
            (slug, slug)
        ).fetchone()
    except Exception:
        # Column embed_slug may not exist yet on older schemas — fall back
        try:
            user_row = db.execute(
                'SELECT id FROM users WHERE username = ? LIMIT 1', (slug,)
            ).fetchone()
        except Exception:
            logger.exception('embed lookup failed for slug %s', slug)

    if not user_row:
        return jsonify({'success': False, 'error': 'Business not found'}), 404

    uid = user_row['id']

    # ── Load business profile ─────────────────────────────────────────
    profile = {}
    try:
        row = db.execute(
            'SELECT business_profile FROM users WHERE id = ?', (uid,)
        ).fetchone()
        if row and row['business_profile']:
            raw = row['business_profile']
            profile = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        logger.exception('embed profile load failed for uid %s', uid)

    # ── Load recent published posts ───────────────────────────────────
    recent_posts = []
    try:
        rows = db.execute(
            '''
            SELECT caption, image_url, created_at
            FROM   post_history
            WHERE  user_id = ?
              AND  status  IN ("published", "success")
            ORDER  BY created_at DESC
            LIMIT  6
            ''',
            (uid,)
        ).fetchall()
        recent_posts = [
            {
                'caption':    row['caption'] or '',
                'image_url':  row['image_url'],
                'created_at': str(row['created_at'] or ''),
            }
            for row in rows
        ]
    except Exception:
        logger.exception('embed posts load failed for uid %s', uid)

    # ── Parse hours (stored as string or dict) ────────────────────────
    hours = profile.get('hours', {})
    if isinstance(hours, str):
        # e.g. "Mon-Fri 9am-5pm" stored as a plain string
        hours = {'Hours': hours}

    return jsonify({
        'success':      True,
        'name':         profile.get('name', ''),
        'tagline':      profile.get('tagline', ''),
        'logo_url':     profile.get('logo_url', ''),
        'about':        profile.get('about', ''),
        'hours':        hours,
        'services':     profile.get('services', []),
        'recent_posts': recent_posts,
    })


# ---------------------------------------------------------------------------
# RSS 2.0 & JSON Feed Syndication (Mixpost/Postiz Pattern)
# ---------------------------------------------------------------------------

@embed_bp.route('/api/feed/<slug>.xml', methods=['GET'])
def public_rss_feed(slug):
    """Public RSS 2.0 XML syndication feed for website builders (WordPress/Webflow/Squarespace)."""
    from app import get_db
    from flask import Response
    import xml.sax.saxutils as saxutils

    db = get_db()
    user_row = None
    try:
        user_row = db.execute(
            'SELECT id, username FROM users WHERE embed_slug = ? OR username = ? LIMIT 1',
            (slug, slug)
        ).fetchone()
    except Exception:
        pass

    if not user_row:
        return Response('<error>Feed not found</error>', status=404, mimetype='application/xml')

    uid = user_row['id']
    profile = {}
    try:
        row = db.execute('SELECT business_profile FROM users WHERE id = ?', (uid,)).fetchone()
        if row and row['business_profile']:
            raw = row['business_profile']
            profile = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass

    b_name = profile.get('name') or user_row['username'] or 'PostPilot Social Feed'
    b_desc = profile.get('tagline') or profile.get('about') or f'Latest updates from {b_name}'

    posts = []
    try:
        rows = db.execute(
            '''
            SELECT id, caption, image_url, created_at
            FROM post_history
            WHERE user_id = ? AND status IN ("published", "success")
            ORDER BY created_at DESC LIMIT 20
            ''',
            (uid,)
        ).fetchall()
        posts = rows or []
    except Exception:
        pass

    items_xml = []
    for p in posts:
        title = saxutils.escape((p['caption'] or '').split('\n')[0][:80] or 'Update')
        desc = saxutils.escape(p['caption'] or '')
        img_tag = f'<enclosure url="{saxutils.escape(p["image_url"])}" type="image/jpeg" />' if p['image_url'] else ''
        guid = f"post-{p['id']}"
        items_xml.append(f"""
        <item>
            <title>{title}</title>
            <description>{desc}</description>
            <guid isPermaLink="false">{guid}</guid>
            {img_tag}
        </item>
        """)

    xml_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
    <channel>
        <title>{saxutils.escape(b_name)}</title>
        <description>{saxutils.escape(b_desc)}</description>
        <link>https://postpilot.app/api/feed/{slug}.xml</link>
        {''.join(items_xml)}
    </channel>
</rss>
"""
    return Response(xml_content.strip(), mimetype='application/rss+xml')


@embed_bp.route('/api/feed/<slug>.json', methods=['GET'])
def public_json_feed(slug):
    """JSON Feed 1.1 standard specification for micro-clients and headless CMSs."""
    from app import get_db
    db = get_db()

    user_row = None
    try:
        user_row = db.execute(
            'SELECT id, username FROM users WHERE embed_slug = ? OR username = ? LIMIT 1',
            (slug, slug)
        ).fetchone()
    except Exception:
        pass

    if not user_row:
        return jsonify({'error': 'Feed not found'}), 404

    uid = user_row['id']
    profile = {}
    try:
        row = db.execute('SELECT business_profile FROM users WHERE id = ?', (uid,)).fetchone()
        if row and row['business_profile']:
            raw = row['business_profile']
            profile = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        pass

    b_name = profile.get('name') or user_row['username'] or 'PostPilot Social Feed'

    posts = []
    try:
        rows = db.execute(
            '''
            SELECT id, caption, image_url, created_at
            FROM post_history
            WHERE user_id = ? AND status IN ("published", "success")
            ORDER BY created_at DESC LIMIT 20
            ''',
            (uid,)
        ).fetchall()
        posts = rows or []
    except Exception:
        pass

    items = []
    for p in posts:
        item = {
            'id': str(p['id']),
            'content_text': p['caption'] or '',
            'title': (p['caption'] or '').split('\n')[0][:80] or 'Update',
            'date_published': str(p['created_at'] or ''),
        }
        if p['image_url']:
            item['image'] = p['image_url']
        items.append(item)

    return jsonify({
        'version': 'https://jsonfeed.org/version/1.1',
        'title': b_name,
        'home_page_url': f'https://postpilot.app/api/embed/{slug}',
        'feed_url': f'https://postpilot.app/api/feed/{slug}.json',
        'items': items,
    })

