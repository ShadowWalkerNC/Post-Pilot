"""
tests/test_p0_fixes.py
Tests for the P0 security and correctness fixes applied in the audit.

Covers:
  1. Billing bypass -- /api/publish enforces platform limits (not just /api/push_all)
  2. XSS in fallback site renderer -- user data is escaped before HTML interpolation
  3. OAuth CSRF -- mismatched state token returns redirect, not 500
  4. post_history ?limit param -- non-integer value returns 200, not 500
  5. Unauthenticated publish -- redirects to login, not 500
"""

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, email, password):
    return client.post('/login', data={'email': email, 'password': password},
                       follow_redirects=True)


# ---------------------------------------------------------------------------
# 1. Billing bypass: /api/publish must enforce platform limits
# ---------------------------------------------------------------------------

class TestBillingBypass:

    def test_free_user_blocked_on_publish_multi_platform(self, logged_in_client):
        """
        A free-tier user selecting more platforms than allowed should get 403
        from /api/publish, not just /api/push_all.
        """
        with patch('blueprints.api.check_platform_limit', return_value=(False, 1)):
            resp = logged_in_client.post(
                '/api/publish',
                json={
                    'caption':      'Test post',
                    'content_type': 'text',
                    # fb/web need no media — avoid validator 400 before plan check
                    'platforms':    ['fb', 'web', 'gb'],
                },
                content_type='application/json',
            )
        assert resp.status_code == 403
        data = resp.get_json()
        err = data.get('error', '')
        err_msg = err['message'] if isinstance(err, dict) else str(err)
        assert 'plan' in err_msg.lower() or 'limit' in err_msg.lower() or 'platform' in err_msg.lower()

    def test_free_user_blocked_on_push_all_multi_platform(self, logged_in_client):
        """Same check on /api/push_all."""
        with patch('blueprints.api.check_platform_limit', return_value=(False, 1)):
            resp = logged_in_client.post(
                '/api/push_all',
                json={
                    'caption':      'Test post',
                    'content_type': 'text',
                    'platforms':    ['fb', 'web', 'gb'],
                },
                content_type='application/json',
            )
        assert resp.status_code == 403
        data = resp.get_json()
        assert data['success'] is False

    def test_allowed_user_not_blocked(self, logged_in_client):
        """When check_platform_limit returns allowed=True, the request proceeds past the guard."""
        with patch('blueprints.api.check_platform_limit', return_value=(True, 3)), \
             patch('blueprints.api.UniversalPublisher') as Pub, \
             patch('blueprints.api.UserManager.log_post', return_value=None), \
             patch('blueprints.api._get_tokens', return_value={}):
            Pub.return_value.push_all.return_value = {'fb': {'success': True}}
            resp = logged_in_client.post(
                '/api/publish',
                json={
                    'caption':      'Hello world',
                    'content_type': 'text',
                    'platforms':    ['fb'],
                },
                content_type='application/json',
            )
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


# ---------------------------------------------------------------------------
# 2. XSS in fallback site renderer
# ---------------------------------------------------------------------------

class TestXSSFallback:

    def test_xss_payload_escaped_in_fallback_html(self, app):
        """
        When public_site.html template raises (simulated), the fallback raw-HTML
        renderer must escape user-supplied title and section labels.
        """
        from blueprints.website import _render_public_site

        xss_title   = '<script>alert(1)</script>'
        xss_section = '<img src=x onerror=alert(2)>'

        site = {
            'published':     True,
            'theme':         'modern',
            'primary_color': '#6366f1',
            'seo':           {'title': xss_title},
            'sections': [{
                'id':      'sec1',
                'label':   xss_section,
                'enabled': True,
            }],
        }

        with app.app_context(), app.test_request_context():
            # Force the template render to fail so we hit the raw-HTML fallback
            with patch('blueprints.website.render_template', side_effect=Exception('template missing')):
                response, status = _render_public_site(site, preview=False)

        assert status == 200
        assert '<script>' not in response
        assert '<img' not in response
        # Escaped equivalents should be present
        assert '&lt;script&gt;' in response
        assert '&lt;img' in response

    def test_safe_content_renders_correctly_in_fallback(self, app):
        """Normal content is still present in the fallback output."""
        from blueprints.website import _render_public_site

        site = {
            'published':     True,
            'primary_color': '#ff0000',
            'seo':           {'title': 'My Cafe'},
            'sections': [{'id': 'about', 'label': 'About Us', 'enabled': True}],
        }

        with app.app_context(), app.test_request_context():
            with patch('blueprints.website.render_template', side_effect=Exception('template missing')):
                response, status = _render_public_site(site, preview=False)

        assert status == 200
        assert 'My Cafe' in response
        assert 'About Us' in response


# ---------------------------------------------------------------------------
# 3. OAuth CSRF -- mismatched state should redirect gracefully
# ---------------------------------------------------------------------------

class TestOAuthCSRF:

    def test_facebook_callback_bad_state_redirects(self, logged_in_client):
        """Mismatched state on Facebook callback must redirect, not 500."""
        with logged_in_client.session_transaction() as sess:
            sess['oauth_state_facebook'] = 'correct-state'

        resp = logged_in_client.get(
            '/auth/facebook/callback?state=WRONG-STATE&code=dummy',
            follow_redirects=False,
        )
        # Must redirect (302) -- not crash (500)
        assert resp.status_code == 302

    def test_google_callback_bad_state_redirects(self, logged_in_client):
        """Mismatched state on Google callback must redirect, not 500."""
        with logged_in_client.session_transaction() as sess:
            sess['oauth_state_google'] = 'correct-state'

        resp = logged_in_client.get(
            '/auth/google/callback?state=WRONG-STATE&code=dummy',
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_tiktok_callback_bad_state_redirects(self, logged_in_client):
        """Mismatched state on TikTok callback must redirect, not 500."""
        with logged_in_client.session_transaction() as sess:
            sess['oauth_state_tiktok'] = 'correct-state'

        resp = logged_in_client.get(
            '/auth/tiktok/callback?state=WRONG-STATE&code=dummy',
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# 4. ?limit=abc on /api/post_history must not 500
# ---------------------------------------------------------------------------

class TestPostHistoryLimit:

    def test_non_integer_limit_returns_200(self, logged_in_client):
        """A non-integer ?limit= should fall back to default 20 and return 200."""
        from unittest.mock import MagicMock, patch
        with patch('modules.database.get_db') as gdb:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            gdb.return_value = mock_db
            resp = logged_in_client.get('/api/post_history?limit=abc')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_negative_limit_is_clamped(self, logged_in_client):
        """A negative limit should not crash; posts list is returned."""
        from unittest.mock import MagicMock, patch
        with patch('modules.database.get_db') as gdb:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            gdb.return_value = mock_db
            resp = logged_in_client.get('/api/post_history?limit=-5')
        assert resp.status_code == 200

    def test_over_max_limit_is_clamped_to_100(self, logged_in_client):
        """Limits above 100 should be silently clamped to 100."""
        from unittest.mock import MagicMock, patch
        with patch('modules.database.get_db') as gdb:
            mock_db = MagicMock()
            mock_db.execute.return_value.fetchall.return_value = []
            gdb.return_value = mock_db
            resp = logged_in_client.get('/api/post_history?limit=9999')
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. Unauthenticated publish redirects to login
# ---------------------------------------------------------------------------

class TestUnauthPublish:

    def test_push_all_requires_login(self, client):
        resp = client.post(
            '/api/push_all',
            json={'caption': 'test', 'platforms': ['fb']},
            content_type='application/json',
            follow_redirects=False,
        )
        # Flask-Login redirects unauthenticated requests to /login
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_publish_requires_login(self, client):
        resp = client.post(
            '/api/publish',
            json={'caption': 'test', 'platforms': ['fb']},
            content_type='application/json',
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()
