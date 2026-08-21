"""
tests/test_e2e_suite.py
Comprehensive 4-Tier End-to-End (E2E) Test Suite for Post-Pilot.

Testing Philosophy:
- Opaque-box, requirement-driven assertions.
- Genuine execution of application routes, database queries, and security guards.
- No dummy/facade implementations or hardcoded shortcuts.

Tiers:
  Tier 1: Feature Coverage (R1 Headless API, R2 MCP Tools, R3 Cron Poller, R4 Public Embed)
  Tier 2: Boundary & Corner Cases (Auth 401s, Param 400s, Malformed Dates, Session 302/401s, 404s, 409s)
  Tier 3: Cross-Feature Combinations (Special -> Embed, Publish -> History, Cron Matrix, Key Lifecycle)
  Tier 4: Real-World Application Scenarios (Morning Setup, Lunch Rush, Full Lifecycle)
"""

import os
import sys
import json
import time
import uuid
import secrets
import hashlib
import importlib.util
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

# Ensure repo root is on PYTHONPATH
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from modules.database import get_db


# ---------------------------------------------------------------------------
# Database Schema & Initialization Helpers
# ---------------------------------------------------------------------------

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    display_name TEXT,
    full_name TEXT,
    business_name TEXT,
    subscription_tier TEXT DEFAULT 'free',
    plan TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_sub_id TEXT,
    sub_status TEXT DEFAULT 'active',
    sub_current_period_end TEXT,
    trial_ends_at TEXT,
    is_admin INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_verified INTEGER DEFAULT 1,
    embed_slug TEXT,
    username TEXT,
    business_profile TEXT,
    created_at INTEGER,
    last_login_at INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS business_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    business_type TEXT DEFAULT 'food_truck',
    location TEXT DEFAULT '',
    address TEXT DEFAULT '',
    lat REAL,
    lng REAL,
    hours TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    website_url TEXT DEFAULT '',
    logo_url TEXT DEFAULT '',
    prompt_time TEXT DEFAULT '07:00',
    timezone TEXT DEFAULT 'US/Eastern',
    ai_tone TEXT DEFAULT 'friendly',
    ai_keywords TEXT DEFAULT '',
    subdomain TEXT UNIQUE,
    custom_domain TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS platform_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'default',
    platform TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TEXT,
    token_meta TEXT,
    updated_at TEXT,
    UNIQUE(user_id, platform)
);

CREATE TABLE IF NOT EXISTS post_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    caption TEXT,
    content_type TEXT DEFAULT 'text',
    image_url TEXT,
    video_url TEXT,
    platforms TEXT,
    results TEXT,
    status TEXT DEFAULT 'published',
    scheduled_at INTEGER,
    created_at INTEGER,
    post_url TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT 'My Key',
    key_hash TEXT NOT NULL UNIQUE,
    key_preview TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    last_used_at INTEGER,
    call_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS platform_settings (
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(user_id, platform)
);

CREATE TABLE IF NOT EXISTS specials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    description TEXT,
    post_date TEXT NOT NULL,
    post_time TEXT NOT NULL,
    platforms TEXT,
    content_type TEXT DEFAULT 'daily_special',
    tone TEXT DEFAULT 'friendly',
    image_url TEXT,
    status TEXT DEFAULT 'pending',
    post_history_id INTEGER,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    event_date TEXT NOT NULL,
    event_end_date TEXT,
    post_date TEXT NOT NULL,
    post_time TEXT NOT NULL,
    event_type TEXT DEFAULT 'event',
    platforms TEXT,
    tone TEXT DEFAULT 'hype',
    image_url TEXT,
    ticket_url TEXT,
    status TEXT DEFAULT 'pending',
    post_history_id INTEGER,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS hours_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    override_type TEXT DEFAULT 'closure',
    post_date TEXT NOT NULL,
    post_time TEXT NOT NULL,
    platforms TEXT,
    tone TEXT DEFAULT 'friendly',
    status TEXT DEFAULT 'pending',
    post_history_id INTEGER,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS websites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    published INTEGER NOT NULL DEFAULT 0,
    theme TEXT NOT NULL DEFAULT 'modern',
    primary_color TEXT NOT NULL DEFAULT '#6366f1',
    auto_sync_posts INTEGER NOT NULL DEFAULT 0,
    custom_domain TEXT,
    url TEXT,
    sections TEXT,
    section_data TEXT,
    seo TEXT,
    socials TEXT,
    config TEXT,
    created_at INTEGER,
    updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS automation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    source_type TEXT,
    source_id INTEGER,
    post_history_id INTEGER,
    status TEXT,
    error_message TEXT,
    created_at INTEGER
);
"""


@pytest.fixture(autouse=True)
def e2e_db(app):
    """Ensure all required tables and columns are present in the test database for every test."""
    with app.app_context():
        db = get_db()
        for statement in SCHEMA_DDL.strip().split(';'):
            stmt = statement.strip()
            if stmt:
                db.execute(stmt)
        # Ensure dynamic columns exist on SQLite users and websites tables if already created by older runs
        try:
            cur = db.execute("PRAGMA table_info(users)")
            cols = {r[1] for r in cur.fetchall()}
            for col, ctype in [
                ('username', 'TEXT'),
                ('embed_slug', 'TEXT'),
                ('business_profile', 'TEXT'),
                ('plan', "TEXT DEFAULT 'free'"),
                ('full_name', 'TEXT'),
                ('business_name', 'TEXT'),
            ]:
                if col not in cols:
                    db.execute(f"ALTER TABLE users ADD COLUMN {col} {ctype}")
        except Exception:
            pass

        try:
            wcur = db.execute("PRAGMA table_info(websites)")
            wcols = {r[1] for r in wcur.fetchall()}
            for col, ctype in [
                ('theme', "TEXT NOT NULL DEFAULT 'modern'"),
                ('primary_color', "TEXT NOT NULL DEFAULT '#6366f1'"),
                ('auto_sync_posts', "INTEGER NOT NULL DEFAULT 0"),
                ('custom_domain', 'TEXT'),
                ('url', 'TEXT'),
                ('sections', 'TEXT'),
                ('section_data', 'TEXT'),
                ('seo', 'TEXT'),
                ('socials', 'TEXT'),
                ('created_at', 'INTEGER'),
                ('config', 'TEXT'),
            ]:
                if col not in wcols:
                    db.execute(f"ALTER TABLE websites ADD COLUMN {col} {ctype}")
        except Exception:
            pass

        db.commit()
        yield db




# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

USER_A_ID = '11111111-1111-4000-8000-111111111111'
USER_B_ID = '22222222-2222-4000-8000-222222222222'


def _create_user_in_db(db, uid, email, username, embed_slug, business_profile=None, tier='starter'):
    profile_json = json.dumps(business_profile or {
        'name': f'Business {username}',
        'tagline': 'Authentic Delicious Food',
        'about': 'Family owned since 2018',
        'hours': {'Monday - Friday': '10am - 8pm', 'Saturday': '11am - 9pm'},
        'services': [{'name': 'Catering', 'price': '$$', 'description': 'Full service catering'}],
    })
    db.execute(
        """
        INSERT INTO users (id, email, username, embed_slug, display_name, full_name,
                           business_name, subscription_tier, plan, business_profile,
                           is_active, is_verified, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
        ON CONFLICT(id) DO UPDATE SET
            email = excluded.email,
            username = excluded.username,
            embed_slug = excluded.embed_slug,
            subscription_tier = excluded.subscription_tier,
            plan = excluded.plan,
            business_profile = excluded.business_profile
        """,
        (uid, email, username, embed_slug, f'User {username}', f'Full {username}',
         f'Business {username}', tier, tier, profile_json, int(time.time()))
    )
    db.commit()


def _create_api_key_for_user(db, user_id, label='Test API Key', ttl_days=30):
    token = 'pp_live_' + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    preview = token[:12] + '...'
    expires_at = int(time.time()) + (ttl_days * 86400) if ttl_days else None
    cur = db.execute(
        """
        INSERT INTO api_keys (user_id, label, key_hash, key_preview, is_active, created_at, expires_at, call_count)
        VALUES (?, ?, ?, ?, 1, ?, ?, 0)
        """,
        (user_id, label, key_hash, preview, int(time.time()), expires_at)
    )
    db.commit()
    return token, cur.lastrowid


@pytest.fixture
def user_a(e2e_db):
    profile = {
        'name': 'Smokey Bandit BBQ',
        'tagline': 'Best Brisket in Town',
        'about': 'Slow smoked woodfired meats',
        'hours': {'Mon-Fri': '11am - 9pm', 'Sat-Sun': '12pm - 10pm'},
        'services': [{'name': 'Brisket Platter', 'price': '$18', 'description': 'Half pound brisket'}],
    }
    _create_user_in_db(e2e_db, USER_A_ID, 'smokey@postpilot.dev', 'smokey_bandit', 'smokey-bandit', profile, 'starter')
    return {
        'id': USER_A_ID,
        'email': 'smokey@postpilot.dev',
        'username': 'smokey_bandit',
        'embed_slug': 'smokey-bandit',
        'profile': profile,
    }


@pytest.fixture
def user_b(e2e_db):
    profile = {
        'name': 'Bella Italia Cafe',
        'tagline': 'Authentic Espresso & Pastries',
        'about': 'Roman coffee bar',
        'hours': {'Daily': '7am - 4pm'},
        'services': [{'name': 'Espresso', 'price': '$3.50', 'description': 'Double shot'}],
    }
    _create_user_in_db(e2e_db, USER_B_ID, 'bella@postpilot.dev', 'bella_italia', 'bella-italia', profile, 'starter')
    return {
        'id': USER_B_ID,
        'email': 'bella@postpilot.dev',
        'username': 'bella_italia',
        'embed_slug': 'bella-italia',
        'profile': profile,
    }


@pytest.fixture
def user_a_api_key(e2e_db, user_a):
    token, key_id = _create_api_key_for_user(e2e_db, user_a['id'], 'User A Primary Key')
    return token


@pytest.fixture
def user_b_api_key(e2e_db, user_b):
    token, key_id = _create_api_key_for_user(e2e_db, user_b['id'], 'User B Primary Key')
    return token


def _mock_user_model(uid, email, tier='starter', username=None, embed_slug=None, business_profile=None):
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_anonymous = False
    user.id = uid
    user.email = email
    user.subscription_tier = tier
    user.plan = tier
    user.username = username or email.split('@')[0]
    user.embed_slug = embed_slug or user.username
    user.business_name = f'Business {user.username}'
    user.business_profile = business_profile or {}
    user.get_id = lambda: uid
    return user


@pytest.fixture
def logged_in_user_a_client(client, user_a, app):
    mock_user = _mock_user_model(user_a['id'], user_a['email'], 'starter', user_a['username'], user_a['embed_slug'], user_a['profile'])
    def _loader(uid):
        return mock_user if str(uid) == user_a['id'] else None

    with patch.object(app.login_manager, '_user_callback', _loader):
        with client.session_transaction() as sess:
            sess['_user_id'] = user_a['id']
            sess['_fresh'] = True
        client._test_user = mock_user
        yield client


@pytest.fixture
def logged_in_user_b_client(client, user_b, app):
    mock_user = _mock_user_model(user_b['id'], user_b['email'], 'starter', user_b['username'], user_b['embed_slug'], user_b['profile'])
    def _loader(uid):
        return mock_user if str(uid) == user_b['id'] else None

    with patch.object(app.login_manager, '_user_callback', _loader):
        with client.session_transaction() as sess:
            sess['_user_id'] = user_b['id']
            sess['_fresh'] = True
        client._test_user = mock_user
        yield client


def _load_mcp_server_module():
    mcp_path = os.path.join(REPO_ROOT, 'mcp', 'server.py')
    spec = importlib.util.spec_from_file_location('postpilot_mcp_server_mod', mcp_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ===========================================================================
# TIER 1: FEATURE COVERAGE (>=5 tests per feature for R1, R2, R3, R4)
# ===========================================================================

class TestR1HeadlessRestApi:
    """R1: Headless REST API (/v1/*) & Schedule Endpoints (/api/specials, /api/events, /api/hours)."""

    def test_r1_v1_health_public(self, client):
        resp = client.get('/v1/health')
        assert resp.status_code == 200
        data = resp.get_json()
        health = data.get('data') if isinstance(data.get('data'), dict) else data
        assert health.get('status') == 'ok' or data.get('status') in ('ok', 'success')
        assert health.get('app') == 'post-pilot' or data.get('app') == 'post-pilot'
        assert health.get('version') == '1.0.0' or data.get('version') == '1.0.0'
        assert isinstance(health.get('uptime', data.get('uptime')), int)

    def test_r1_v1_manifest_with_bearer_token(self, client, user_a_api_key):
        resp = client.get('/v1/manifest', headers={'Authorization': f'Bearer {user_a_api_key}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True or data.get('status') == 'success'
        tools_obj = data.get('data', {})
        tools = tools_obj.get('tools') if isinstance(tools_obj, dict) else tools_obj
        assert isinstance(tools, list)
        assert len(tools) >= 4

    def test_r1_v1_generate_post_success(self, client, user_a_api_key):
        resp = client.post(
            '/v1/generate_post',
            headers={'Authorization': f'Bearer {user_a_api_key}'},
            json={
                'topic': 'Brisket Platter Special with Apple Slaw',
                'platform': 'instagram',
                'tone': 'hype',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True or data.get('status') == 'success'
        res_data = data.get('data', data)
        assert 'caption' in res_data
        assert isinstance(res_data['caption'], str)
        assert len(res_data['caption']) > 10

    def test_r1_v1_publish_post_success(self, client, user_a_api_key):
        with patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True}, 'instagram': {'success': True}}):
            resp = client.post(
                '/v1/publish_post',
                headers={'Authorization': f'Bearer {user_a_api_key}'},
                json={
                    'caption': 'Fresh smoked brisket right out of the pit!',
                    'platforms': ['facebook', 'instagram'],
                    'image_url': 'https://example.com/brisket.jpg',
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True or data.get('status') == 'success'
        res_data = data.get('data', data)
        assert 'post_id' in res_data
        assert res_data['results']['facebook']['success'] is True

    def test_r1_v1_generate_and_publish_oneshot(self, client, user_a_api_key):
        with patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True}}):
            resp = client.post(
                '/v1/generate_and_publish',
                headers={'Authorization': f'Bearer {user_a_api_key}'},
                json={
                    'topic': 'Smoked Wings Special $12',
                    'platforms': ['facebook'],
                    'tone': 'friendly',
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True or data.get('status') == 'success'
        res_data = data.get('data', data)
        assert 'caption' in res_data
        assert 'post_id' in res_data


    def test_r1_v1_get_history(self, client, user_a_api_key, user_a, e2e_db):
        e2e_db.execute(
            """
            INSERT INTO post_history (user_id, caption, content_type, platforms, status, created_at)
            VALUES (?, 'Test history post 1', 'text', '["facebook"]', 'published', ?)
            """,
            (user_a['id'], int(time.time()))
        )
        e2e_db.commit()

        resp = client.get('/v1/get_history?limit=10', headers={'Authorization': f'Bearer {user_a_api_key}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['count'] >= 1
        assert any(p['caption'] == 'Test history post 1' for p in data['data']['posts'])

    def test_r1_v1_get_site_config_and_set_published(self, client, user_a_api_key):
        # 1. get config
        resp = client.get('/v1/get_site_config', headers={'Authorization': f'Bearer {user_a_api_key}'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'theme' in data['data']

        # 2. set published true
        resp2 = client.post(
            '/v1/set_published',
            headers={'Authorization': f'Bearer {user_a_api_key}'},
            json={'published': True},
        )
        assert resp2.status_code == 200
        assert resp2.get_json()['success'] is True

    def test_r1_api_specials_crud(self, logged_in_user_a_client):
        # Create
        create_resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Truffle Mac & Cheese',
            'post_date': '2026-09-01',
            'post_time': '11:30',
            'description': 'Four cheese blend with black truffle',
            'platforms': ['fb', 'ig'],
            'tone': 'friendly',
        })
        assert create_resp.status_code == 201
        special_id = create_resp.get_json()['id']

        # List
        list_resp = logged_in_user_a_client.get('/api/specials')
        assert list_resp.status_code == 200
        specials = list_resp.get_json()['specials']
        assert any(s['id'] == special_id for s in specials)

        # Update
        update_resp = logged_in_user_a_client.put(f'/api/specials/{special_id}', json={
            'item_name': 'Smoked Truffle Mac & Cheese',
            'post_time': '12:00',
        })
        assert update_resp.status_code == 200
        assert update_resp.get_json()['success'] is True

        # Cancel
        cancel_resp = logged_in_user_a_client.post(f'/api/specials/{special_id}/cancel')
        assert cancel_resp.status_code == 200

        # Delete
        del_resp = logged_in_user_a_client.delete(f'/api/specials/{special_id}')
        assert del_resp.status_code == 200

    def test_r1_api_events_crud(self, logged_in_user_a_client):
        # Create
        create_resp = logged_in_user_a_client.post('/api/events', json={
            'title': 'Live Blues & BBQ Night',
            'post_date': '2026-09-05',
            'post_time': '10:00',
            'event_date': '2026-09-05',
            'event_type': 'concert',
            'description': 'Live music with Delta Blues band',
            'platforms': ['fb', 'ig'],
            'tone': 'hype',
        })
        assert create_resp.status_code == 201
        event_id = create_resp.get_json()['id']

        # List
        list_resp = logged_in_user_a_client.get('/api/events')
        assert list_resp.status_code == 200
        events = list_resp.get_json()['events']
        assert any(e['id'] == event_id for e in events)

        # Update
        update_resp = logged_in_user_a_client.put(f'/api/events/{event_id}', json={
            'title': 'Live Blues & Smoke Night - Updated',
        })
        assert update_resp.status_code == 200

        # Cancel
        cancel_resp = logged_in_user_a_client.post(f'/api/events/{event_id}/cancel')
        assert cancel_resp.status_code == 200

        # Delete
        del_resp = logged_in_user_a_client.delete(f'/api/events/{event_id}')
        assert del_resp.status_code == 200

    def test_r1_api_hours_crud(self, logged_in_user_a_client):
        # Create
        create_resp = logged_in_user_a_client.post('/api/hours', json={
            'title': 'Labor Day Special Hours',
            'message': 'Open 12pm - 10pm for the holiday',
            'post_date': '2026-09-07',
            'post_time': '09:00',
            'override_type': 'holiday',
            'platforms': ['fb', 'web'],
        })
        assert create_resp.status_code == 201
        hours_id = create_resp.get_json()['id']

        # List
        list_resp = logged_in_user_a_client.get('/api/hours')
        assert list_resp.status_code == 200
        hours = list_resp.get_json()['hours']
        assert any(h['id'] == hours_id for h in hours)

        # Update
        update_resp = logged_in_user_a_client.put(f'/api/hours/{hours_id}', json={
            'title': 'Labor Day Extended Hours',
        })
        assert update_resp.status_code == 200

        # Cancel
        cancel_resp = logged_in_user_a_client.post(f'/api/hours/{hours_id}/cancel')
        assert cancel_resp.status_code == 200

        # Delete
        del_resp = logged_in_user_a_client.delete(f'/api/hours/{hours_id}')
        assert del_resp.status_code == 200


class TestR2MCPServerTools:
    """R2: MCP Server Tools in mcp/server.py."""

    @pytest.fixture
    def mcp_mod(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'gh_test_dummy_token'}):
            return _load_mcp_server_module()

    def test_r2_mcp_get_repo_structure(self, mcp_mod):
        mock_file1 = MagicMock(name='app.py', size=8000, type='file')
        mock_file1.name = 'app.py'
        mock_file2 = MagicMock(name='modules', size=0, type='dir')
        mock_file2.name = 'modules'

        mock_repo = MagicMock()
        mock_repo.get_contents.return_value = [mock_file1, mock_file2]

        with patch.object(mcp_mod, '_gh', return_value=mock_repo):
            res = mcp_mod.get_repo_structure('ShadowWalkerNC', 'Post-Pilot')
            assert res['repo'] == 'ShadowWalkerNC/Post-Pilot'
            assert len(res['files']) == 2
            assert res['files'][0]['name'] == 'app.py'

    def test_r2_mcp_read_file(self, mcp_mod):
        mock_file = MagicMock()
        mock_file.sha = 'abc123sha'
        mock_file.decoded_content = b'print("hello post-pilot")'

        mock_repo = MagicMock()
        mock_repo.get_contents.return_value = mock_file

        with patch.object(mcp_mod, '_gh', return_value=mock_repo):
            res = mcp_mod.read_file('ShadowWalkerNC', 'Post-Pilot', 'app.py')
            assert res['path'] == 'app.py'
            assert res['sha'] == 'abc123sha'
            assert 'hello post-pilot' in res['content']

    def test_r2_mcp_audit_repo(self, mcp_mod):
        mock_repo = MagicMock()
        # Mock successful check finds
        req_file = MagicMock()
        req_file.decoded_content = b'psycopg2\nAPScheduler\npytest\nsentry-sdk\n'
        def _get_contents(path):
            if path == 'requirements.txt':
                return req_file
            return MagicMock()

        mock_repo.get_contents.side_effect = _get_contents

        with patch.object(mcp_mod, '_gh', return_value=mock_repo):
            res = mcp_mod.audit_repo('ShadowWalkerNC', 'Post-Pilot')
            assert res['repo'] == 'ShadowWalkerNC/Post-Pilot'
            assert 'score' in res
            assert res['checks']['tests/ directory'] == 'PASS'
            assert res['checks']['requirements: pytest'] == 'PASS'

    def test_r2_mcp_write_file_create_and_update(self, mcp_mod):
        mock_repo = MagicMock()
        # Existing file update
        mock_existing = MagicMock(sha='old_sha_123')
        mock_repo.get_contents.return_value = mock_existing
        mock_repo.update_file.return_value = {
            'commit': MagicMock(sha='commit_sha_update', html_url='https://github.com/commit/1')
        }

        with patch.object(mcp_mod, '_gh', return_value=mock_repo):
            res = mcp_mod.write_file('ShadowWalkerNC', 'Post-Pilot', 'test.py', 'code', 'commit msg')
            assert res['path'] == 'test.py'
            assert res['commit_sha'] == 'commit_sha_update'
            mock_repo.update_file.assert_called_once()

    def test_r2_mcp_issues_and_commits(self, mcp_mod):
        mock_repo = MagicMock()
        # Mock issues
        label_mock = MagicMock()
        label_mock.name = 'bug'
        mock_issue = MagicMock(number=42, title='Fix token rotation', html_url='https://github.com/issues/42', labels=[label_mock])
        mock_repo.get_issues.return_value = [mock_issue]
        mock_repo.create_issue.return_value = mock_issue

        # Mock commits
        mock_commit = MagicMock()
        mock_commit.sha = 'abcdef123456'
        mock_commit.commit.message = 'feat: add MCP server'
        mock_commit.commit.author.name = 'Test Author'
        mock_commit.commit.author.date.isoformat.return_value = '2026-08-19T12:00:00Z'
        mock_commit.html_url = 'https://github.com/commits/1'
        mock_repo.get_commits.return_value = [mock_commit]

        with patch.object(mcp_mod, '_gh', return_value=mock_repo):
            # List issues
            issues = mcp_mod.list_open_issues('ShadowWalkerNC', 'Post-Pilot')
            assert len(issues) == 1
            assert issues[0]['number'] == 42

            # Create issue
            new_issue = mcp_mod.create_issue('ShadowWalkerNC', 'Post-Pilot', 'New Bug', 'Body text')
            assert new_issue['number'] == 42

            # List commits
            commits = mcp_mod.list_recent_commits('ShadowWalkerNC', 'Post-Pilot')
            assert len(commits) == 1
            assert commits[0]['sha'] == 'abcdef1'


class TestR3AICommentModerationAndCronPoller:
    """R3: AI Comment Moderation & Auto-Reply Poller (Cron endpoints & Cron Auth)."""

    TEST_CRON_SECRET = 'postpilot_secure_cron_secret_777'

    def test_r3_cron_health_endpoint(self, client):
        resp = client.get('/api/cron/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert 'publish' in data['endpoints']
        assert 'generate' in data['endpoints']

    def test_r3_cron_publish_with_valid_secret(self, client):
        with patch('blueprints.cron._CRON_SECRET', self.TEST_CRON_SECRET), \
             patch('modules.scheduler_worker._publish_scheduled_posts') as mock_pub:
            resp = client.get('/api/cron/publish', headers={'Authorization': f'Bearer {self.TEST_CRON_SECRET}'})
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True
            mock_pub.assert_called_once()

    def test_r3_cron_publish_post_method_supported(self, client):
        with patch('blueprints.cron._CRON_SECRET', self.TEST_CRON_SECRET), \
             patch('modules.scheduler_worker._publish_scheduled_posts'):
            resp = client.post('/api/cron/publish', headers={'Authorization': f'Bearer {self.TEST_CRON_SECRET}'})
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_r3_cron_generate_with_valid_secret(self, client):
        summary_result = {'processed': 1, 'queued': 2, 'skipped': 0, 'errors': 0}
        with patch('blueprints.cron._CRON_SECRET', self.TEST_CRON_SECRET), \
             patch('modules.automation_agent.run_for_all_users', return_value=summary_result):
            resp = client.post('/api/cron/generate', headers={'Authorization': f'Bearer {self.TEST_CRON_SECRET}'})
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert data['summary']['queued'] == 2

    def test_r3_cron_auth_failures_and_unset_secret(self, client):
        # 1. Missing header
        with patch('blueprints.cron._CRON_SECRET', self.TEST_CRON_SECRET):
            resp1 = client.get('/api/cron/publish')
            assert resp1.status_code == 401

            # 2. Wrong token
            resp2 = client.post('/api/cron/generate', headers={'Authorization': 'Bearer wrong-secret'})
            assert resp2.status_code == 401

        # 3. Unset CRON_SECRET rejects all requests
        with patch('blueprints.cron._CRON_SECRET', ''):
            resp3 = client.get('/api/cron/publish', headers={'Authorization': f'Bearer {self.TEST_CRON_SECRET}'})
            assert resp3.status_code == 401


class TestR4PublicEmbedAndWidget:
    """R4: Public Embed Feed & Drop-in Widget."""

    def test_r4_public_embed_by_embed_slug(self, client, user_a, e2e_db):
        resp = client.get(f'/api/embed/{user_a["embed_slug"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['name'] == 'Smokey Bandit BBQ'
        assert 'Mon-Fri' in data['hours']
        assert len(data['services']) >= 1

    def test_r4_public_embed_by_username_fallback(self, client, user_b, e2e_db):
        resp = client.get(f'/api/embed/{user_b["username"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['name'] == 'Bella Italia Cafe'

    def test_r4_public_embed_unknown_slug_returns_404(self, client):
        resp = client.get('/api/embed/nonexistent-business-xyz-999')
        assert resp.status_code == 404
        data = resp.get_json()
        assert data['success'] is False
        assert 'not found' in data['error'].lower()

    def test_r4_public_embed_recent_posts_filtering(self, client, user_a, e2e_db):
        # Clear prior posts for clean isolation
        e2e_db.execute("DELETE FROM post_history WHERE user_id = ?", (user_a['id'],))
        e2e_db.commit()

        # Insert 1 published post, 1 success post, 1 scheduled post (should be excluded), 1 draft post (should be excluded)
        now_ts = int(time.time())
        e2e_db.execute(
            """
            INSERT INTO post_history (user_id, caption, content_type, image_url, status, created_at)
            VALUES
                (?, 'Published special promo', 'text', 'https://example.com/p1.jpg', 'published', ?),
                (?, 'Success weekend announcement', 'text', 'https://example.com/p2.jpg', 'success', ?),
                (?, 'Draft post not visible', 'text', NULL, 'draft', ?),
                (?, 'Scheduled post future', 'text', NULL, 'scheduled', ?)
            """,
            (user_a['id'], now_ts,
             user_a['id'], now_ts - 100,
             user_a['id'], now_ts - 200,
             user_a['id'], now_ts - 300)
        )
        e2e_db.commit()


        resp = client.get(f'/api/embed/{user_a["embed_slug"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        recent_captions = [p['caption'] for p in data['recent_posts']]
        assert 'Published special promo' in recent_captions
        assert 'Success weekend announcement' in recent_captions
        assert 'Draft post not visible' not in recent_captions
        assert 'Scheduled post future' not in recent_captions

    def test_r4_static_embed_js_asset_and_structure(self, client):
        js_path = os.path.join(REPO_ROOT, 'static', 'embed.js')
        assert os.path.exists(js_path), "static/embed.js must exist on disk"
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Structural assertions on widget JS
        assert 'data-postpilot-slug' in content
        assert 'THEMES' in content
        assert 'buildWidget' in content
        assert 'DOMContentLoaded' in content


# ===========================================================================
# TIER 2: BOUNDARY & CORNER CASES (>=5 per feature area)
# ===========================================================================

class TestTier2MissingBearerTokenUnauthorized:
    """Tier 2: Missing Bearer token / unauthorized access (401)."""

    def test_generate_post_without_auth_header(self, client):
        resp = client.post('/v1/generate_post', json={'topic': 'Test'})
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'MISSING_AUTH'

    def test_manifest_without_auth_header(self, client):
        resp = client.get('/v1/manifest')
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'MISSING_AUTH'

    def test_publish_post_with_invalid_token(self, client):
        resp = client.post(
            '/v1/publish_post',
            headers={'Authorization': 'Bearer pp_live_completely_fake_token_123'},
            json={'caption': 'Test'},
        )
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'INVALID_KEY'

    def test_get_history_with_expired_api_key(self, client, e2e_db, user_a):
        token = 'pp_live_' + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        e2e_db.execute(
            """
            INSERT INTO api_keys (user_id, label, key_hash, key_preview, is_active, created_at, expires_at)
            VALUES (?, 'Expired Key', ?, 'pp_live_exp...', 1, ?, ?)
            """,
            (user_a['id'], key_hash, int(time.time()) - 10000, int(time.time()) - 100)
        )
        e2e_db.commit()

        resp = client.get('/v1/get_history', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'KEY_EXPIRED'

    def test_cron_publish_unauthorized(self, client):
        with patch('blueprints.cron._CRON_SECRET', 'secret_xyz'):
            resp = client.get('/api/cron/publish')
            assert resp.status_code == 401

    def test_cron_generate_unauthorized_token(self, client):
        with patch('blueprints.cron._CRON_SECRET', 'secret_xyz'):
            resp = client.post('/api/cron/generate', headers={'Authorization': 'Bearer bad-secret'})
            assert resp.status_code == 401


class TestTier2EmptyStringsAndMissingParams:
    """Tier 2: Empty strings / missing required parameters (400)."""

    def test_generate_post_missing_topic(self, client, user_a_api_key):
        resp = client.post('/v1/generate_post', headers={'Authorization': f'Bearer {user_a_api_key}'}, json={'topic': '   '})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_TOPIC'

    def test_publish_post_missing_caption(self, client, user_a_api_key):
        resp = client.post('/v1/publish_post', headers={'Authorization': f'Bearer {user_a_api_key}'}, json={'caption': ''})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_CAPTION'

    def test_set_published_missing_published_flag(self, client, user_a_api_key):
        resp = client.post('/v1/set_published', headers={'Authorization': f'Bearer {user_a_api_key}'}, json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_PUBLISHED'

    def test_create_special_missing_item_name(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': '',
            'post_date': '2026-09-01',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('item_name is required' in err for err in resp.get_json()['errors'])

    def test_create_special_empty_platforms(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Brisket',
            'post_date': '2026-09-01',
            'platforms': [],
        })
        assert resp.status_code == 400
        assert any('platforms must be a non-empty list' in err for err in resp.get_json()['errors'])

    def test_create_event_missing_title(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/events', json={
            'title': '',
            'post_date': '2026-09-05',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('title is required' in err for err in resp.get_json()['errors'])

    def test_revoke_key_missing_key_id(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/v1/keys/revoke', json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_KEY_ID'


class TestTier2MalformedDatesAndTimes:
    """Tier 2: Malformed dates (e.g. invalid YYYY-MM-DD or HH:MM)."""

    def test_special_malformed_post_date(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Burger',
            'post_date': '2026-13-45',
            'post_time': '11:00',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('post_date must be YYYY-MM-DD' in err for err in resp.get_json()['errors'])

    def test_special_malformed_post_time(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Burger',
            'post_date': '2026-09-01',
            'post_time': '25:70',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('post_time must be HH:MM' in err for err in resp.get_json()['errors'])

    def test_special_update_malformed_date(self, logged_in_user_a_client):
        # Create first
        c_resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Burger',
            'post_date': '2026-09-01',
            'platforms': ['fb'],
        })
        sid = c_resp.get_json()['id']
        # Update with bad date
        u_resp = logged_in_user_a_client.put(f'/api/specials/{sid}', json={'post_date': 'not-a-date'})
        assert u_resp.status_code == 400
        assert 'post_date must be YYYY-MM-DD' in u_resp.get_json()['error']

    def test_event_malformed_date(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/events', json={
            'title': 'Concert',
            'post_date': '2026-02-31',
            'event_date': '2026-02-31',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('YYYY-MM-DD' in err for err in resp.get_json()['errors'])

    def test_hours_malformed_time(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.post('/api/hours', json={
            'title': 'Closed',
            'post_date': '2026-09-01',
            'post_time': '99:99',
            'platforms': ['fb'],
        })
        assert resp.status_code == 400
        assert any('post_time must be HH:MM' in err for err in resp.get_json()['errors'])


class TestTier2UnauthenticatedSessionEndpoints:
    """Tier 2: Unauthenticated session endpoints."""

    def test_schedule_page_redirects_unauth(self, client):
        resp = client.get('/schedule')
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_specials_api_redirects_unauth(self, client):
        resp = client.get('/api/specials')
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_events_api_redirects_unauth(self, client):
        resp = client.post('/api/events', json={'title': 'test'})
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_hours_api_redirects_unauth(self, client):
        resp = client.get('/api/hours')
        assert resp.status_code == 302
        assert 'login' in resp.headers.get('Location', '').lower()

    def test_keys_create_unauthenticated_returns_401(self, client):
        resp = client.post('/v1/keys/create', json={'label': 'No Auth'})
        assert resp.status_code == 401
        assert resp.get_json()['code'] in ('UNAUTHENTICATED', 'MISSING_AUTH')

    def test_keys_list_unauthenticated_returns_401(self, client):
        resp = client.get('/v1/keys')
        assert resp.status_code == 401
        assert resp.get_json()['code'] in ('UNAUTHENTICATED', 'MISSING_AUTH')

    def test_keys_revoke_unauthenticated_returns_401(self, client):
        resp = client.post('/v1/keys/revoke', json={'key_id': 1})
        assert resp.status_code == 401
        assert resp.get_json()['code'] in ('UNAUTHENTICATED', 'MISSING_AUTH')



class TestTier2UnknownIdUpdatesAndDeletes:
    """Tier 2: Unknown/missing ID updates and deletes (404)."""

    def test_update_nonexistent_special_returns_404(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.put('/api/specials/999999', json={'item_name': 'Ghost'})
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_update_nonexistent_event_returns_404(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.put('/api/events/999999', json={'title': 'Ghost Event'})
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_update_nonexistent_hours_returns_404(self, logged_in_user_a_client):
        resp = logged_in_user_a_client.put('/api/hours/999999', json={'title': 'Ghost Hours'})
        assert resp.status_code == 404
        assert 'not found' in resp.get_json()['error'].lower()

    def test_special_cross_tenant_update_isolation(self, logged_in_user_b_client, e2e_db, user_a):
        # Insert a special owned by User A
        cur = e2e_db.execute(
            """
            INSERT INTO specials (user_id, item_name, post_date, post_time, status)
            VALUES (?, 'User A Secret Item', '2026-09-01', '11:00', 'pending')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        special_id = cur.lastrowid

        # User B attempts to edit User A's special
        u_resp = logged_in_user_b_client.put(f'/api/specials/{special_id}', json={
            'item_name': 'Hacked Item Name',
        })
        assert u_resp.status_code == 404
        assert 'not found' in u_resp.get_json()['error'].lower()

    def test_event_cross_tenant_update_isolation(self, logged_in_user_b_client, e2e_db, user_a):
        # Insert an event owned by User A
        cur = e2e_db.execute(
            """
            INSERT INTO events (user_id, title, event_date, post_date, post_time, status)
            VALUES (?, 'User A Private Tasting', '2026-09-05', '2026-09-05', '18:00', 'pending')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        event_id = cur.lastrowid

        # User B attempts to edit User A's event
        u_resp = logged_in_user_b_client.put(f'/api/events/{event_id}', json={
            'title': 'Hacked Event Title',
        })
        assert u_resp.status_code == 404
        assert 'not found' in u_resp.get_json()['error'].lower()



class TestTier2NonPendingStatusRejection:
    """Tier 2: Non-pending status update rejection (409)."""

    def test_cannot_update_published_special(self, logged_in_user_a_client, e2e_db, user_a):
        cur = e2e_db.execute(
            """
            INSERT INTO specials (user_id, item_name, post_date, post_time, status)
            VALUES (?, 'Already Published Special', '2026-09-01', '11:00', 'published')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        sid = cur.lastrowid

        resp = logged_in_user_a_client.put(f'/api/specials/{sid}', json={'item_name': 'New Name'})
        assert resp.status_code == 409
        assert 'cannot edit a published special' in resp.get_json()['error'].lower()

    def test_cannot_update_queued_special(self, logged_in_user_a_client, e2e_db, user_a):
        cur = e2e_db.execute(
            """
            INSERT INTO specials (user_id, item_name, post_date, post_time, status)
            VALUES (?, 'Queued Special', '2026-09-01', '11:00', 'queued')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        sid = cur.lastrowid

        resp = logged_in_user_a_client.put(f'/api/specials/{sid}', json={'item_name': 'New Name'})
        assert resp.status_code == 409
        assert 'cannot edit a queued special' in resp.get_json()['error'].lower()

    def test_cannot_update_published_event(self, logged_in_user_a_client, e2e_db, user_a):
        cur = e2e_db.execute(
            """
            INSERT INTO events (user_id, title, event_date, post_date, post_time, status)
            VALUES (?, 'Published Event', '2026-09-01', '2026-09-01', '11:00', 'published')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        eid = cur.lastrowid

        resp = logged_in_user_a_client.put(f'/api/events/{eid}', json={'title': 'Updated Title'})
        assert resp.status_code == 409
        assert 'cannot edit a published event' in resp.get_json()['error'].lower()

    def test_cannot_update_cancelled_event(self, logged_in_user_a_client, e2e_db, user_a):
        cur = e2e_db.execute(
            """
            INSERT INTO events (user_id, title, event_date, post_date, post_time, status)
            VALUES (?, 'Cancelled Event', '2026-09-01', '2026-09-01', '11:00', 'cancelled')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        eid = cur.lastrowid

        resp = logged_in_user_a_client.put(f'/api/events/{eid}', json={'title': 'Updated Title'})
        assert resp.status_code == 409
        assert 'cannot edit a cancelled event' in resp.get_json()['error'].lower()

    def test_cannot_update_published_hours(self, logged_in_user_a_client, e2e_db, user_a):
        cur = e2e_db.execute(
            """
            INSERT INTO hours_overrides (user_id, title, post_date, post_time, status)
            VALUES (?, 'Published Hours', '2026-09-01', '09:00', 'published')
            """,
            (user_a['id'],)
        )
        e2e_db.commit()
        hid = cur.lastrowid

        resp = logged_in_user_a_client.put(f'/api/hours/{hid}', json={'title': 'Updated Title'})
        assert resp.status_code == 409
        assert 'cannot edit a published override' in resp.get_json()['error'].lower()


# ===========================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ===========================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Cross-Feature Integration flows."""

    def test_special_creation_to_database_and_embed_feed(self, logged_in_user_a_client, client, user_a, e2e_db):
        # 1. User creates special via schedule API
        resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Chili Crisp Smoked Brisket',
            'post_date': '2026-09-02',
            'post_time': '11:00',
            'description': 'Crispy spicy smoked beef',
            'platforms': ['fb', 'ig'],
            'tone': 'hype',
        })
        assert resp.status_code == 201
        sid = resp.get_json()['id']

        # 2. Verify row exists in DB
        row = e2e_db.execute('SELECT * FROM specials WHERE id = ?', (sid,)).fetchone()
        assert row['item_name'] == 'Chili Crisp Smoked Brisket'
        assert row['status'] == 'pending'

        # 3. Simulate publication into post_history
        e2e_db.execute(
            """
            INSERT INTO post_history (user_id, caption, content_type, image_url, status, created_at)
            VALUES (?, 'TODAY SPECIAL: Chili Crisp Smoked Brisket is LIVE!', 'text', 'https://example.com/chili.jpg', 'published', ?)
            """,
            (user_a['id'], int(time.time()))
        )
        e2e_db.commit()

        # 4. Query public embed feed
        embed_resp = client.get(f'/api/embed/{user_a["embed_slug"]}')
        assert embed_resp.status_code == 200
        embed_data = embed_resp.get_json()
        captions = [p['caption'] for p in embed_data['recent_posts']]
        assert any('Chili Crisp Smoked Brisket' in c for c in captions)

    def test_post_publish_to_v1_get_history_and_db(self, client, user_a_api_key, user_a, e2e_db):
        # 1. Publish post via V1 API
        unique_caption = f"Unique pitmaster drop at {int(time.time())}"
        with patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True, 'url': 'https://fb.com/post1'}}):
            pub_resp = client.post(
                '/v1/publish_post',
                headers={'Authorization': f'Bearer {user_a_api_key}'},
                json={
                    'caption': unique_caption,
                    'platforms': ['facebook'],
                },
            )
        assert pub_resp.status_code == 200

        # 2. Retrieve history via V1 API
        hist_resp = client.get('/v1/get_history?limit=5', headers={'Authorization': f'Bearer {user_a_api_key}'})
        assert hist_resp.status_code == 200
        hist_data = hist_resp.get_json()
        matching = [p for p in hist_data['data']['posts'] if p['caption'] == unique_caption]
        assert len(matching) == 1
        assert matching[0]['status'] == 'published'

    def test_cron_secret_enforcement_matrix(self, client):
        secret = 'matrix_test_cron_secret_888'
        with patch('blueprints.cron._CRON_SECRET', secret), \
             patch('modules.scheduler_worker._publish_scheduled_posts'), \
             patch('modules.automation_agent.run_for_all_users', return_value={'processed': 0, 'queued': 0}):

            # Public health check: always 200
            assert client.get('/api/cron/health').status_code == 200

            # Cron publish: 401 without auth, 200 with auth
            assert client.get('/api/cron/publish').status_code == 401
            assert client.get('/api/cron/publish', headers={'Authorization': f'Bearer {secret}'}).status_code == 200

            # Cron generate: 401 without auth, 200 with auth
            assert client.post('/api/cron/generate').status_code == 401
            assert client.post('/api/cron/generate', headers={'Authorization': f'Bearer {secret}'}).status_code == 200

    def test_api_key_lifecycle_create_use_revoke_reject(self, logged_in_user_a_client, client):
        # 1. Create new API key from authenticated dashboard
        create_resp = logged_in_user_a_client.post('/v1/keys/create', json={'label': 'Automated Bot Key', 'ttl_days': 7})
        assert create_resp.status_code == 200
        key_data = create_resp.get_json()['data']
        token = key_data['key']
        assert token.startswith('pp_live_')

        # 2. Use key in Bearer auth
        manifest_resp = client.get('/v1/manifest', headers={'Authorization': f'Bearer {token}'})
        assert manifest_resp.status_code == 200
        assert manifest_resp.get_json()['success'] is True

        # 3. List keys and find the key ID
        list_resp = logged_in_user_a_client.get('/v1/keys')
        assert list_resp.status_code == 200
        keys = list_resp.get_json()['data']['keys']
        bot_key = next((k for k in keys if k['label'] == 'Automated Bot Key'), None)
        assert bot_key is not None
        key_id = bot_key['id']

        # 4. Revoke key
        revoke_resp = logged_in_user_a_client.post('/v1/keys/revoke', json={'key_id': key_id})
        assert revoke_resp.status_code == 200
        assert revoke_resp.get_json()['data']['revoked'] is True

        # 5. Subsequent request with revoked token is rejected with 401
        reject_resp = client.get('/v1/manifest', headers={'Authorization': f'Bearer {token}'})
        assert reject_resp.status_code == 401
        assert reject_resp.get_json()['code'] in ('INVALID_KEY', 'REVOKED_KEY')



# ===========================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ===========================================================================

class TestTier4RealWorldScenarios:
    """Tier 4: Realistic end-to-end operational user stories."""

    def test_scenario_food_truck_morning_setup(self, logged_in_user_a_client, client, user_a, e2e_db):
        """
        Scenario 1: Food truck morning setup
        - Update business profile
        - Add daily lunch special
        - Add holiday hours override
        - Query public embed feed to verify customer visibility
        """
        # Step A: Update business profile on user record
        updated_profile = {
            'name': 'Smokey Bandit BBQ Smokehouse',
            'tagline': 'Craft Texas BBQ in Downtown',
            'about': 'Post oak smoked beef brisket and ribs',
            'hours': {'Mon-Sun': '11am - Sold Out'},
            'services': [
                {'name': 'Monster Brisket Sandwich', 'price': '$15', 'description': 'With pickled jalapenos'},
                {'name': 'Rack of Ribs', 'price': '$28', 'description': 'Full rack glazed in peach habanero'}
            ],
        }
        e2e_db.execute(
            'UPDATE users SET business_profile = ? WHERE id = ?',
            (json.dumps(updated_profile), user_a['id'])
        )
        e2e_db.commit()

        # Step B: Add daily specials
        special_resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Monster Brisket Sandwich Combo',
            'post_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'post_time': '10:30',
            'description': 'Includes mac & cheese and drink',
            'platforms': ['fb', 'ig', 'web'],
            'tone': 'hype',
        })
        assert special_resp.status_code == 201

        # Step C: Add holiday hours override
        hours_resp = logged_in_user_a_client.post('/api/hours', json={
            'title': 'Downtown Festival Hours',
            'message': 'Open until midnight for the music festival',
            'post_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'post_time': '09:00',
            'override_type': 'holiday',
            'platforms': ['fb', 'web'],
        })
        assert hours_resp.status_code == 201

        # Step D: Query public embed feed
        embed_resp = client.get(f'/api/embed/{user_a["embed_slug"]}')
        assert embed_resp.status_code == 200
        embed_data = embed_resp.get_json()
        assert embed_data['name'] == 'Smokey Bandit BBQ Smokehouse'
        assert embed_data['hours']['Mon-Sun'] == '11am - Sold Out'
        assert len(embed_data['services']) == 2

    def test_scenario_lunch_rush_automation(self, client, user_a_api_key, user_a, e2e_db):
        """
        Scenario 2: Lunch rush automation
        - Generate AI post draft
        - Publish post immediately
        - Verify history record
        - Queue a scheduled post due now
        - Trigger cron publish runner to auto-publish
        """
        # Step A: Generate draft
        gen_resp = client.post(
            '/v1/generate_post',
            headers={'Authorization': f'Bearer {user_a_api_key}'},
            json={
                'topic': 'Lunch rush special: 2 Brisket Sandwiches + 2 Fries for $25',
                'platform': 'facebook',
                'tone': 'urgent',
            },
        )
        assert gen_resp.status_code == 200
        caption = gen_resp.get_json()['data']['caption']

        # Step B: Publish immediately
        with patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True}}):
            pub_resp = client.post(
                '/v1/publish_post',
                headers={'Authorization': f'Bearer {user_a_api_key}'},
                json={
                    'caption': caption,
                    'platforms': ['facebook'],
                },
            )
        assert pub_resp.status_code == 200

        # Step C: Verify history record
        hist_resp = client.get('/v1/get_history?limit=1', headers={'Authorization': f'Bearer {user_a_api_key}'})
        assert hist_resp.status_code == 200
        assert hist_resp.get_json()['data']['count'] >= 1

        # Step D: Insert a scheduled post due right now
        past_ts = int(time.time()) - 10
        cur = e2e_db.execute(
            """
            INSERT INTO post_history (user_id, caption, content_type, platforms, status, scheduled_at, created_at)
            VALUES (?, 'Afternoon Flash Sale!', 'text', '["facebook"]', 'scheduled', ?, ?)
            """,
            (user_a['id'], past_ts, past_ts)
        )
        e2e_db.commit()
        scheduled_id = cur.lastrowid

        # Step E: Trigger cron publish runner
        cron_secret = 'lunch_rush_cron_key'
        with patch('blueprints.cron._CRON_SECRET', cron_secret), \
             patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True}}):
            cron_resp = client.get('/api/cron/publish', headers={'Authorization': f'Bearer {cron_secret}'})
            assert cron_resp.status_code == 200

        # Verify status transitioned from 'scheduled' to 'published'
        row = e2e_db.execute('SELECT status FROM post_history WHERE id = ?', (scheduled_id,)).fetchone()
        assert row['status'] == 'published'

    def test_scenario_full_business_operational_lifecycle(self, logged_in_user_a_client, client, user_a, e2e_db):
        """
        Scenario 3: Full business operational lifecycle
        1. API key creation & validation
        2. Website config & publish status
        3. Specials, events, and hours schedule creation
        4. One-shot content generation & publishing
        5. Cron automation execution
        6. Public embed widget data retrieval
        7. History audit
        8. API key cleanup
        """
        # 1. API key creation
        key_resp = logged_in_user_a_client.post('/v1/keys/create', json={'label': 'Full Lifecycle Key'})
        assert key_resp.status_code == 200
        token = key_resp.get_json()['data']['key']

        # 2. Website config & publish
        set_pub_resp = client.post(
            '/v1/set_published',
            headers={'Authorization': f'Bearer {token}'},
            json={'published': True},
        )
        assert set_pub_resp.status_code == 200

        site_cfg_resp = client.get('/v1/get_site_config', headers={'Authorization': f'Bearer {token}'})
        assert site_cfg_resp.status_code == 200
        assert site_cfg_resp.get_json()['data']['published'] == 1

        # 3. Schedule specials, events, hours
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        s_resp = logged_in_user_a_client.post('/api/specials', json={
            'item_name': 'Brisket Burrito', 'post_date': today_str, 'platforms': ['fb']
        })
        assert s_resp.status_code == 201

        e_resp = logged_in_user_a_client.post('/api/events', json={
            'title': 'Weekend Cookout', 'post_date': today_str, 'event_date': today_str, 'platforms': ['fb']
        })
        assert e_resp.status_code == 201

        h_resp = logged_in_user_a_client.post('/api/hours', json={
            'title': 'Early Open', 'post_date': today_str, 'platforms': ['fb']
        })
        assert h_resp.status_code == 201

        # 4. Generate & publish
        with patch('modules.publisher.UniversalPublisher.push_all', return_value={'facebook': {'success': True}}):
            gen_pub_resp = client.post(
                '/v1/generate_and_publish',
                headers={'Authorization': f'Bearer {token}'},
                json={'topic': 'Cookout Announcement', 'platforms': ['facebook']},
            )
        assert gen_pub_resp.status_code == 200

        # 5. Cron generate poller
        cron_secret = 'lifecycle_cron_secret'
        with patch('blueprints.cron._CRON_SECRET', cron_secret), \
             patch('modules.ai_generator.generate_caption', return_value='Generated caption for special'):
            cron_resp = client.post('/api/cron/generate', headers={'Authorization': f'Bearer {cron_secret}'})
            assert cron_resp.status_code == 200

        # 6. Public embed verification
        embed_resp = client.get(f'/api/embed/{user_a["embed_slug"]}')
        assert embed_resp.status_code == 200
        assert embed_resp.get_json()['name'] == 'Smokey Bandit BBQ'

        # 7. History audit
        hist_resp = client.get('/v1/get_history?limit=10', headers={'Authorization': f'Bearer {token}'})
        assert hist_resp.status_code == 200
        assert hist_resp.get_json()['data']['count'] >= 1

        # 8. API key cleanup
        keys_resp = logged_in_user_a_client.get('/v1/keys')
        k_list = keys_resp.get_json()['data']['keys']
        target_k = next(k for k in k_list if k['label'] == 'Full Lifecycle Key')
        rev_resp = logged_in_user_a_client.post('/v1/keys/revoke', json={'key_id': target_k['id']})
        assert rev_resp.status_code == 200

        # Confirm rejection
        assert client.get('/v1/manifest', headers={'Authorization': f'Bearer {token}'}).status_code == 401


# ===========================================================================
# TIER 6: INDUSTRY WORKFLOWS & LOGIC SUITE (Buffer, Later, Sprout, Mixpost, Typefully)
# ===========================================================================

class TestIndustryWorkflowsSuite:
    """Tests for advanced industry workflows adopted across PostPilot Pro."""

    def test_sprout_engagement_scorer(self):
        from modules.ai_generator import calculate_engagement_score
        caption = "🔥 Craving the best smashburger in town? Come taste why our double bacon burger went viral!\n\nOrder online or tap link in bio for 20% off. #smashburger #foodtruck #bestfood #lunchspecial"
        res = calculate_engagement_score(caption, platform='instagram')
        assert res['score'] >= 75
        assert res['tier'] in ('strong', 'moderate')
        assert res['has_cta'] is True
        assert res['hashtag_count'] == 4

    def test_later_first_comment_and_typefully_retry(self):
        from modules.publisher import UniversalPublisher
        tokens = {
            'instagram_token': 'test_ig_token',
            'instagram_id': 'test_ig_id',
        }
        publisher = UniversalPublisher(tokens=tokens)

        mock_container = MagicMock()
        mock_container.status_code = 200
        mock_container.json.return_value = {'id': 'container_123'}

        mock_publish = MagicMock()
        mock_publish.status_code = 200
        mock_publish.json.return_value = {'id': 'media_post_456'}

        mock_comment = MagicMock()
        mock_comment.status_code = 200
        mock_comment.json.return_value = {'id': 'comment_789'}

        with patch('requests.request', side_effect=[mock_container, mock_publish, mock_comment]):
            res = publisher._publish_instagram(
                caption='Fresh Tacos on the grill!',
                media_url='https://example.com/taco.jpg',
                first_comment='#tacos #foodie #lunch #streetfood'
            )
            assert res['success'] is True
            assert res['post_id'] == 'media_post_456'
            assert res['first_comment']['id'] == 'comment_789'

    def test_buffer_queue_slot_api(self, client, user_a_api_key):
        resp = client.post(
            '/api/v1/posts/queue',
            headers={'Authorization': f'Bearer {user_a_api_key}'},
            json={
                'caption': 'Queued lunch special for the rush!',
                'platforms': ['facebook', 'instagram'],
                'first_comment': '#food #lunch',
            }
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] == 'scheduled'
        assert 'queued_slot' in data['data']

    def test_sprout_analyze_api(self, client, user_a_api_key):
        resp = client.post(
            '/api/v1/posts/analyze',
            headers={'Authorization': f'Bearer {user_a_api_key}'},
            json={
                'caption': 'What is your favorite taco topping? Let us know in the comments below! 🌮',
                'platform': 'instagram',
            }
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['score'] > 50
        assert data['data']['has_cta'] is True

    def test_mixpost_rss_and_json_syndication_feeds(self, client, user_a):
        # 1. RSS XML
        rss_resp = client.get(f'/api/feed/{user_a["username"]}.xml')
        assert rss_resp.status_code == 200
        assert 'xml' in rss_resp.content_type
        assert '<rss version="2.0">' in rss_resp.get_data(as_text=True)

        # 2. JSON Feed
        json_resp = client.get(f'/api/feed/{user_a["username"]}.json')
        assert json_resp.status_code == 200
        j_data = json_resp.get_json()
        assert j_data['version'] == 'https://jsonfeed.org/version/1.1'
        assert 'items' in j_data

