"""
conftest.py -- pytest fixtures for Post-Pilot.

Forces SQLite so no real DB is needed to run tests.
Disables CSRF so form posts work in tests (unless a test re-enables it).
"""

import os
from unittest.mock import MagicMock, patch

# Set env before any app imports.
# Force a file-backed SQLite DB — CI previously set DATABASE_PATH=:memory:, which
# gives each connection a separate empty DB and breaks platform_tokens init.
os.environ['DATABASE_URL'] = ''
os.environ['DATABASE_PATH'] = 'test_postpilot.db'
try:
    if os.path.exists('test_postpilot.db'):
        os.remove('test_postpilot.db')
except Exception:
    pass
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-key-for-ci-only')
os.environ.setdefault('TOKEN_ENCRYPTION_KEY', 'nZeXTE9lxj2Vt5nUWGvfeVacq9+sz5XPLBuiA9wqjy4=')

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('APP_ENV', 'development')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')
os.environ.setdefault('STRIPE_SECRET_KEY', 'dummy')
os.environ.setdefault('FACEBOOK_APP_ID', 'dummy')
os.environ.setdefault('FACEBOOK_APP_SECRET', 'dummy')
os.environ.setdefault('GOOGLE_CLIENT_ID', 'dummy')
os.environ.setdefault('GOOGLE_CLIENT_SECRET', 'dummy')
os.environ.setdefault('TIKTOK_CLIENT_KEY', 'dummy')
os.environ.setdefault('TIKTOK_CLIENT_SECRET', 'dummy')

import pytest


@pytest.fixture(scope='session')
def app():
    import app as flask_app
    flask_app.app.config.update({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'LOGIN_DISABLED': False,
    })
    with flask_app.app.app_context():
        from modules.auth_manager import init_db as auth_init_db
        auth_init_db()
        from modules.database import get_db
        from modules.api_manager import CREATE_API_KEYS_TABLE
        db = get_db()
        db.execute(CREATE_API_KEYS_TABLE)
        db.commit()
    yield flask_app.app
    try:
        import gc
        gc.collect()
        if os.path.exists('test_postpilot.db'):
            os.remove('test_postpilot.db')
    except Exception:
        pass


@pytest.fixture()
def client(app):
    return app.test_client()


def _make_mock_user(uid='00000000-0000-4000-8000-000000000001',
                    email='testuser@postpilot.dev',
                    tier='starter'):
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_anonymous = False
    user.id = uid
    user.email = email
    user.subscription_tier = tier
    user.plan = tier
    user.get_id = lambda: uid
    return user


@pytest.fixture()
def registered_user():
    return {
        'email': 'testuser@postpilot.dev',
        'password': 'unused',
        'id': '00000000-0000-4000-8000-000000000001',
    }


@pytest.fixture()
def logged_in_client(client, registered_user, app):
    """
    Authenticated test client. Magic-link auth has no password login,
    so we stub flask-login's user_loader for the session.
    """
    user = _make_mock_user(registered_user['id'], registered_user['email'], 'starter')

    def _loader(uid):
        if str(uid) == registered_user['id']:
            return user
        return None

    with patch.object(app.login_manager, '_user_callback', _loader):
        with client.session_transaction() as sess:
            sess['_user_id'] = registered_user['id']
            sess['_fresh'] = True
        client._test_user = user
        yield client
