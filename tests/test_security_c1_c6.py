"""
tests/test_security_c1_c6.py
Regression tests for critical security fixes C1–C6.
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# C2 — /v1 IDOR: user API keys cannot act as another user_id
# ---------------------------------------------------------------------------

class TestV1UserIdBinding:

    def test_resolve_scoped_user_id_binds_api_key_owner(self, app):
        from modules.api_manager import _resolve_scoped_user_id
        with app.test_request_context():
            from flask import g
            g.api_key_row = {'id': 1}
            g.api_user_id = 'key-owner'
            assert _resolve_scoped_user_id('attacker-supplied') == 'key-owner'

    def test_resolve_scoped_user_id_allows_srn_explicit(self, app):
        from modules.api_manager import _resolve_scoped_user_id
        with app.test_request_context():
            from flask import g
            g.api_key_row = None
            g.api_user_id = None
            assert _resolve_scoped_user_id('srn-target') == 'srn-target'


# ---------------------------------------------------------------------------
# C1 — CSRF enforced on session API when enabled
# ---------------------------------------------------------------------------

class TestCSRFEnforced:

    def test_publish_without_csrf_rejected_when_enabled(self, app, registered_user):
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            user = MagicMock()
            user.is_authenticated = True
            user.is_active = True
            user.is_anonymous = False
            user.id = registered_user['id']
            user.subscription_tier = 'starter'
            user.get_id = lambda: registered_user['id']

            def _loader(uid):
                return user if str(uid) == registered_user['id'] else None

            client = app.test_client()
            with patch.object(app.login_manager, '_user_callback', _loader):
                with client.session_transaction() as sess:
                    sess['_user_id'] = registered_user['id']
                    sess['_fresh'] = True
                resp = client.post(
                    '/api/publish',
                    json={
                        'caption': 'csrf test',
                        'content_type': 'text',
                        'platforms': ['fb'],
                    },
                    content_type='application/json',
                )
            assert resp.status_code == 400
        finally:
            app.config['WTF_CSRF_ENABLED'] = False


# ---------------------------------------------------------------------------
# C6 — setup_tokens always gone (OAuth-only; matches main Wave A)
# ---------------------------------------------------------------------------

class TestSetupTokensLocked:

    def test_setup_tokens_gone_in_production(self, logged_in_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'production')
        monkeypatch.setenv('FLASK_ENV', 'production')
        resp = logged_in_client.post(
            '/api/setup_tokens',
            json={'tokens': {'facebook_token': 'stolen'}},
            content_type='application/json',
        )
        assert resp.status_code == 410
        data = resp.get_json()
        assert data['success'] is False
        assert data['error']['code'] == 'GONE'

    def test_setup_tokens_gone_in_dev(self, logged_in_client, monkeypatch):
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('FLASK_ENV', 'development')
        resp = logged_in_client.post(
            '/api/setup_tokens',
            json={'tokens': {'tiktok_token': 'dev-token'}},
            content_type='application/json',
        )
        assert resp.status_code == 410
        assert resp.get_json()['success'] is False


# ---------------------------------------------------------------------------
# C3 — TOKEN_ENCRYPTION_KEY fail-closed helper
# ---------------------------------------------------------------------------

class TestEncryptionKeyPolicy:

    def test_is_production_helper(self, monkeypatch):
        from modules.auth_manager import _is_production
        monkeypatch.delenv('VERCEL_ENV', raising=False)
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('FLASK_ENV', 'development')
        assert _is_production() is False
        monkeypatch.setenv('APP_ENV', 'production')
        assert _is_production() is True
        monkeypatch.setenv('APP_ENV', 'development')
        monkeypatch.setenv('VERCEL_ENV', 'preview')
        assert _is_production() is False
        monkeypatch.setenv('VERCEL_ENV', 'production')
        assert _is_production() is True


# ---------------------------------------------------------------------------
# C5 — get_db import path
# ---------------------------------------------------------------------------

class TestGetDbImport:

    def test_modules_database_get_db_callable(self, app):
        from modules.database import get_db
        with app.app_context():
            db = get_db()
            assert db is not None
            row = db.execute('SELECT 1 AS n').fetchone()
            assert row is not None
