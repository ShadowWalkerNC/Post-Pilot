# website_manager.py — Post-Pilot Session 11
# Manages white-label website config, publish state, SEO, and site preview.

import json
import time
import socket
from modules.database import get_db


class WebsiteManager:
    """Handles all website hub operations for a given user."""

    DEFAULT_SECTIONS = [
        {'id': 'hero',        'label': 'Hero Banner',     'icon': 'H', 'enabled': True},
        {'id': 'about',       'label': 'About Us',        'icon': 'A', 'enabled': True},
        {'id': 'menu',        'label': 'Menu / Services', 'icon': 'M', 'enabled': True},
        {'id': 'specials',    'label': 'Daily Specials',  'icon': 'S', 'enabled': True},
        {'id': 'gallery',     'label': 'Photo Gallery',   'icon': 'G', 'enabled': True},
        {'id': 'reviews',     'label': 'Reviews',         'icon': 'R', 'enabled': False},
        {'id': 'hours',       'label': 'Hours & Location','icon': 'L', 'enabled': True},
        {'id': 'contact',     'label': 'Contact / Book',  'icon': 'C', 'enabled': False},
        {'id': 'social_feed', 'label': 'Social Feed',     'icon': 'F', 'enabled': False},
    ]

    # ------------------------------------------------------------------ init
    def __init__(self, user_id: str):
        self.user_id = user_id
        self._ensure_row()

    def _ensure_row(self):
        """Create a website row for the user if it doesn't exist yet."""
        db = get_db()
        existing = db.execute(
            'SELECT id FROM websites WHERE user_id = ?', (self.user_id,)
        ).fetchone()
        if not existing:
            db.execute(
                '''
                INSERT INTO websites
                  (user_id, published, theme, primary_color, auto_sync_posts,
                   sections, seo, socials, created_at, updated_at)
                VALUES (?, 0, 'modern', '#6366f1', 0, ?, '{}', '{}', ?, ?)
                ''',
                (
                    self.user_id,
                    json.dumps(self.DEFAULT_SECTIONS),
                    int(time.time()), int(time.time()),
                ),
            )
            db.commit()

    # ------------------------------------------------------------------ read
    def get_site(self) -> dict:
        """Return the full website config dict for this user."""
        db  = get_db()
        row = db.execute(
            'SELECT * FROM websites WHERE user_id = ?', (self.user_id,)
        ).fetchone()
        if not row:
            return {}
        site = dict(row)
        # Deserialise JSON blobs
        for field in ('sections', 'seo', 'socials', 'section_data'):
            if site.get(field):
                try:
                    site[field] = json.loads(site[field])
                except (ValueError, TypeError):
                    site[field] = {} if field != 'sections' else self.DEFAULT_SECTIONS
        # Build public URL
        site['url'] = self._site_url(site)
        return site

    def _site_url(self, site: dict) -> str:
        if site.get('custom_domain'):
            return f"https://{site['custom_domain']}"
        return f"/site/{self.user_id}"

    # ------------------------------------------------------------------ write
    def save_site(self, payload: dict) -> dict:
        """Persist section/SEO/social/theme changes."""
        db = get_db()
        db.execute(
            '''
            UPDATE websites SET
              sections      = ?,
              theme         = ?,
              primary_color = ?,
              auto_sync_posts = ?,
              seo           = ?,
              socials       = ?,
              updated_at    = ?
            WHERE user_id = ?
            ''',
            (
                json.dumps(payload.get('sections', self.DEFAULT_SECTIONS)),
                payload.get('theme', 'modern'),
                payload.get('primary_color', '#6366f1'),
                1 if payload.get('auto_sync') else 0,
                json.dumps(payload.get('seo', {})),
                json.dumps(payload.get('socials', {})),
                int(time.time()),
                self.user_id,
            ),
        )
        db.commit()
        return {'success': True}

    def set_published(self, published: bool) -> dict:
        """Toggle live/draft state."""
        db = get_db()
        db.execute(
            'UPDATE websites SET published = ?, updated_at = ? WHERE user_id = ?',
            (1 if published else 0, int(time.time()), self.user_id),
        )
        db.commit()
        return {'success': True, 'published': published}

    def set_custom_domain(self, domain: str) -> dict:
        """Save custom domain after verification."""
        db = get_db()
        db.execute(
            'UPDATE websites SET custom_domain = ?, updated_at = ? WHERE user_id = ?',
            (domain.strip().lower(), int(time.time()), self.user_id),
        )
        db.commit()
        return {'success': True}

    # ------------------------------------------------------------------ domain verify
    def verify_domain(self, domain: str) -> dict:
        """
        Basic DNS verification: checks if the domain resolves to our IP,
        or if a CNAME exists. In production, compare against your server IP.
        """
        domain = domain.strip().lower().replace('https://', '').replace('http://', '')
        try:
            resolved = socket.gethostbyname(domain)
            # In production: compare resolved against your server's IP
            # For now, if it resolves at all, we consider it plausible
            if resolved:
                self.set_custom_domain(domain)
                return {'success': True, 'resolved_ip': resolved}
        except socket.gaierror as e:
            return {'success': False, 'error': str(e)}
        return {'success': False, 'error': 'Could not resolve domain'}

    # ------------------------------------------------------------------ SRN manifest tools
    def get_manifest_tools(self) -> list:
        """
        Returns the SRN tool definitions this module exposes.
        Used by api_manager.py to populate GET /v1/manifest.
        """
        return [
            {
                'name':        'get_site_config',
                'description': 'Get the current website config for this user',
                'method':      'GET',
                'path':        '/v1/get_site_config',
                'input':       {},
                'output':      {'success': 'boolean', 'data': 'object'},
            },
            {
                'name':        'set_published',
                'description': 'Publish or unpublish the user website',
                'method':      'POST',
                'path':        '/v1/set_published',
                'input':       {'published': {'type': 'boolean', 'required': True}},
                'output':      {'success': 'boolean'},
            },
        ]

    # ------------------------------------------------------------------ DB schema helper
    @staticmethod
    def create_table_sql() -> str:
        return '''
        CREATE TABLE IF NOT EXISTS websites (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         TEXT    NOT NULL UNIQUE,
            published       INTEGER NOT NULL DEFAULT 0,
            theme           TEXT    NOT NULL DEFAULT 'modern',
            primary_color   TEXT    NOT NULL DEFAULT '#6366f1',
            auto_sync_posts INTEGER NOT NULL DEFAULT 0,
            custom_domain   TEXT,
            url             TEXT,
            sections        TEXT,
            section_data    TEXT,
            seo             TEXT,
            socials         TEXT,
            created_at      INTEGER,
            updated_at      INTEGER
        );
        '''
