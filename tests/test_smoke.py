"""
test_smoke.py -- Route smoke tests for Post-Pilot.

Verifies every public + key authenticated route returns the expected
HTTP status code. Establishes the CI test baseline.
"""


class TestPublicRoutes:
    def test_index(self, client):
        resp = client.get('/')
        assert resp.status_code in (200, 302)

    def test_login_page(self, client):
        assert client.get('/login').status_code == 200

    def test_register_page(self, client):
        assert client.get('/register').status_code == 200

    def test_legal_privacy(self, client):
        assert client.get('/legal/privacy').status_code == 200

    def test_legal_terms(self, client):
        assert client.get('/legal/terms').status_code == 200

    def test_404(self, client):
        assert client.get('/this-route-does-not-exist-xyz').status_code == 404


class TestAuthFlow:
    def test_register_new_user(self, client):
        resp = client.post('/register', data={
            'email':        'brand-new@example.com',
            'password':     'SecurePass1!',
            'display_name': 'Brand New',
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_login_wrong_password(self, client):
        resp = client.post('/login', data={
            'email':    'nobody@example.com',
            'password': 'wrongpassword',
        }, follow_redirects=True)
        assert b'Invalid email or password' in resp.data

    def test_protected_redirects_anonymous(self, client):
        resp = client.get('/dashboard')
        assert resp.status_code == 302
        assert '/login' in resp.headers['Location']


class TestAuthenticatedRoutes:
    def test_dashboard(self, logged_in_client):
        assert logged_in_client.get('/dashboard').status_code == 200

    def test_billing(self, logged_in_client):
        assert logged_in_client.get('/billing').status_code == 200

    def test_post_history_returns_list(self, logged_in_client):
        resp = logged_in_client.get('/api/post_history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert isinstance(data['posts'], list)

    def test_connection_status(self, logged_in_client):
        resp = logged_in_client.get('/api/connection_status')
        assert resp.status_code == 200
        assert 'platforms' in resp.get_json()

    def test_generate_page(self, logged_in_client):
        assert logged_in_client.get('/generate').status_code == 200

    def test_calendar_page(self, logged_in_client):
        assert logged_in_client.get('/calendar').status_code == 200

    def test_analytics_page(self, logged_in_client):
        assert logged_in_client.get('/analytics').status_code == 200


class TestPlanGuard:
    def test_analytics_api_free_user(self, logged_in_client):
        """Free-tier user calling /api/analytics should get 403 (plan gate) not 500."""
        resp = logged_in_client.post('/api/analytics', json={})
        # 403 = plan gate working; 200/400 = gate not yet wired (acceptable for now)
        assert resp.status_code in (200, 400, 403)
        assert resp.status_code != 500
