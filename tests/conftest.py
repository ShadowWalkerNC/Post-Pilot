"""
conftest.py -- pytest fixtures for Post-Pilot.

Forces SQLite in-memory so no real DB is needed to run tests.
Disables CSRF so form posts work in tests.
"""

import os

# Set env before any app imports
os.environ.setdefault('DATABASE_URL', '')
os.environ.setdefault('DATABASE_PATH', ':memory:')
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-key-for-ci-only')
os.environ.setdefault('TOKEN_ENCRYPTION_KEY', 'dGVzdC1lbmNyeXB0aW9uLWtleS1mb3ItY2ktb25seQ==')
os.environ.setdefault('FLASK_ENV', 'testing')
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
        flask_app.init_db()
    yield flask_app.app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def registered_user(client):
    email    = 'testuser@postpilot.dev'
    password = 'TestPass123!'
    client.post('/register', data={
        'email':        email,
        'password':     password,
        'display_name': 'Test User',
    }, follow_redirects=True)
    return {'email': email, 'password': password}


@pytest.fixture()
def logged_in_client(client, registered_user):
    client.post('/login', data={
        'email':    registered_user['email'],
        'password': registered_user['password'],
    }, follow_redirects=True)
    return client
