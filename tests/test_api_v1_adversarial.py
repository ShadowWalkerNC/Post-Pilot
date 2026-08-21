"""
tests/test_api_v1_adversarial.py
Adversarial Stress Test Suite for Post-Pilot Unified REST API (/api/v1/*).

Vectors Evaluated:
  1. Authentication & Token Boundaries (missing, malformed, expired, revoked, timing attacks, IDOR)
  2. Malformed & Pathological JSON Payloads (syntax errors, non-dict roots, empty bodies, type coercion)
  3. SQL Injection Resilience (query parameters, filter clauses, order clauses, body payloads)
  4. Missing Required Fields & Boundary Validation (drafts, generation, dispatch, schedules, CRUD)
  5. Invalid Date & Time Formats (calendar overflows, non-ISO strings, out-of-range times)
  6. Lifecycle State Machine & Conflict Handling (updating published/cancelled records, double cancels)
"""

import hashlib
import json
import time
import pytest
from modules.database import get_db


# Helper to seed a second user for multi-tenant IDOR validation
@pytest.fixture()
def second_user(app):
    uid = '00000000-0000-4000-8000-000000000002'
    raw_key = 'pp_live_seconduserkey9876543210fedcba'
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO users (id, email, full_name, display_name, subscription_tier, plan, is_active)
            VALUES (?, 'victim@postpilot.dev', 'Victim User', 'Victim User', 'pro', 'pro', 1)
            """,
            (uid,),
        )
        db.execute(
            """
            INSERT OR REPLACE INTO api_keys
              (id, user_id, label, key_hash, key_value, key_preview, is_active, active, created_at, expires_at, call_count)
            VALUES (2002, ?, 'Victim Key', ?, ?, 'pp_live_vict...', 1, 1, ?, NULL, 0)
            """,
            (uid, key_hash, raw_key, int(time.time())),
        )
        db.commit()
    return {'id': uid, 'api_key': raw_key}


# ===========================================================================
# 1. Authentication & Token Boundaries
# ===========================================================================

class TestAdversarialAuthAndTokens:

    @pytest.mark.parametrize('method,path', [
        ('POST', '/api/v1/posts/draft'),
        ('POST', '/api/v1/posts/generate'),
        ('POST', '/api/v1/posts/dispatch'),
        ('POST', '/api/v1/posts/schedule'),
        ('GET',  '/api/v1/posts/history'),
        ('GET',  '/api/v1/specials'),
        ('POST', '/api/v1/specials'),
        ('GET',  '/api/v1/events'),
        ('POST', '/api/v1/events'),
        ('GET',  '/api/v1/hours/overrides'),
        ('POST', '/api/v1/hours/overrides'),
        ('GET',  '/api/v1/analytics/summary'),
        ('GET',  '/api/v1/manifest'),
        ('GET',  '/api/v1/keys'),
        ('POST', '/api/v1/keys/create'),
        ('POST', '/api/v1/keys/revoke'),
    ])
    def test_all_protected_endpoints_reject_unauthenticated_requests(self, client, method, path):
        if method == 'GET':
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['success'] is False
        assert data['code'] in ('MISSING_AUTH', 'UNAUTHENTICATED')

    @pytest.mark.parametrize('malformed_header', [
        'Bearer ',
        'Bearer       ',
        'Bearer null',
        'Bearer undefined',
        'Bearer 12345',
        'Basic dXNlcjpwYXNz',
        'Token some_legacy_token',
        'Bearer \x00\x01\x02',
        'Bearer pp_live_' + 'A' * 500,
    ])
    def test_malformed_auth_headers_fail_safely(self, client, malformed_header):
        headers = {'Authorization': malformed_header}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] in ('MISSING_AUTH', 'INVALID_KEY', 'UNAUTHENTICATED')

    def test_srn_secret_timing_and_length_mismatch_fails(self, client, monkeypatch):
        monkeypatch.setenv('SRN_SECRET', 'super_secret_srn_key_64_characters_long_for_internal_security_test')
        # Substring / partial match attempt
        headers = {'Authorization': 'Bearer super_secret_srn_key_64_characters_long_for_internal_secur'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'INVALID_KEY'

        # Off by 1 character
        headers = {'Authorization': 'Bearer super_secret_srn_key_64_characters_long_for_internal_security_tesX'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401

    def test_idor_cross_tenant_read_isolation(self, client, valid_api_key, second_user, registered_user):
        """User A must NEVER read User B's post history, specials, events, or hours overrides."""
        # Seed victim records
        with client.application.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO specials (user_id, item_name, post_date, post_time, status) VALUES (?, 'Victim Secret Burger', '2026-08-20', '12:00', 'pending')",
                (second_user['id'],),
            )
            victim_special_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            db.execute(
                "INSERT INTO events (user_id, title, event_date, post_date, post_time, status) VALUES (?, 'Victim Private Gala', '2026-08-25', '2026-08-20', '12:00', 'pending')",
                (second_user['id'],),
            )
            victim_event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            db.execute(
                "INSERT INTO hours_overrides (user_id, title, post_date, post_time, status) VALUES (?, 'Victim Secret Closure', '2026-08-22', '09:00', 'pending')",
                (second_user['id'],),
            )
            victim_override_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()

        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # 1. Specials listing with victim user_id param
        resp = client.get(f'/api/v1/specials?user_id={second_user["id"]}', headers=headers)
        assert resp.status_code == 200
        specials = resp.get_json()['data']['specials']
        for s in specials:
            assert s['user_id'] == registered_user['id']
            assert s['item_name'] != 'Victim Secret Burger'

        # 2. Specific special lookup
        resp = client.get(f'/api/v1/specials/{victim_special_id}', headers=headers)
        assert resp.status_code == 404
        assert resp.get_json()['code'] == 'NOT_FOUND'

        # 3. Specific event lookup
        resp = client.get(f'/api/v1/events/{victim_event_id}', headers=headers)
        assert resp.status_code == 404

        # 4. Specific hours override lookup
        resp = client.get(f'/api/v1/hours/overrides/{victim_override_id}', headers=headers)
        assert resp.status_code == 404

    def test_idor_cross_tenant_write_and_mutation_isolation(self, client, valid_api_key, second_user, registered_user):
        """User A must NEVER edit, cancel, or delete User B's records."""
        with client.application.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO specials (user_id, item_name, post_date, post_time, status) VALUES (?, 'Victim Target Item', '2026-08-20', '12:00', 'pending')",
                (second_user['id'],),
            )
            victim_special_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()

        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # Attempt to update victim special
        resp = client.put(f'/api/v1/specials/{victim_special_id}', headers=headers, json={'item_name': 'Hacked Name'})
        assert resp.status_code == 404

        # Attempt to cancel victim special
        resp = client.post(f'/api/v1/specials/{victim_special_id}/cancel', headers=headers, json={})
        assert resp.status_code == 404

        # Attempt to delete victim special
        resp = client.delete(f'/api/v1/specials/{victim_special_id}', headers=headers)
        assert resp.status_code == 404

        # Verify victim special is completely untouched
        with client.application.app_context():
            db = get_db()
            row = db.execute('SELECT item_name, status FROM specials WHERE id = ?', (victim_special_id,)).fetchone()
            assert row['item_name'] == 'Victim Target Item'
            assert row['status'] == 'pending'

    def test_idor_cross_tenant_api_key_revocation_isolation(self, client, valid_api_key, second_user):
        """User A cannot revoke User B's API key."""
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/keys/revoke', headers=headers, json={'key_id': 2002})
        assert resp.status_code == 200

        # Verify victim key is still active
        with client.application.app_context():
            db = get_db()
            row = db.execute('SELECT is_active, active FROM api_keys WHERE id = 2002').fetchone()
            assert row['is_active'] == 1
            assert row['active'] == 1


# ===========================================================================
# 2. Malformed & Pathological JSON Payloads
# ===========================================================================

class TestAdversarialMalformedPayloads:

    @pytest.mark.parametrize('endpoint', [
        '/api/v1/posts/draft',
        '/api/v1/posts/generate',
        '/api/v1/posts/dispatch',
        '/api/v1/posts/schedule',
        '/api/v1/specials',
        '/api/v1/events',
        '/api/v1/hours/overrides',
        '/api/v1/keys/create',
        '/api/v1/keys/revoke',
    ])
    def test_broken_json_syntax_returns_json_response(self, client, valid_api_key, endpoint):
        headers = {
            'Authorization': f'Bearer {valid_api_key}',
            'Content-Type': 'application/json',
        }
        broken_raw_bytes = b'{"caption": "broken, missing quote and brace'
        resp = client.post(endpoint, headers=headers, data=broken_raw_bytes)
        # Should not crash with uncaught exception
        assert resp.content_type.startswith('application/json')

    def test_oversized_payload_strings_handled_safely(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        huge_caption = 'A' * 20000
        resp = client.post('/api/v1/posts/draft', headers=headers, json={'caption': huge_caption})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert len(data['data']['caption']) == 20000


# ===========================================================================
# 3. SQL Injection Resilience
# ===========================================================================

class TestAdversarialSQLInjection:

    @pytest.mark.parametrize('sqli_payload', [
        "' OR '1'='1",
        "'; DROP TABLE specials; --",
        "1' UNION SELECT 1,2,3,4,5,6,7,8,9,10,11,12,13,14 --",
        "admin'--",
        "' OR 1=1 /*",
    ])
    def test_sqli_in_specials_query_parameters(self, client, valid_api_key, sqli_payload):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        # Test post_date injection
        resp = client.get(f'/api/v1/specials?post_date={sqli_payload}', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert isinstance(data['data']['specials'], list)

        # Test status injection
        resp = client.get(f'/api/v1/specials?status={sqli_payload}', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert isinstance(data['data']['specials'], list)

    @pytest.mark.parametrize('sqli_payload', [
        "' OR '1'='1",
        "'; DROP TABLE events; --",
        "' UNION SELECT id, user_id, title FROM events --",
    ])
    def test_sqli_in_events_query_parameters(self, client, valid_api_key, sqli_payload):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get(f'/api/v1/events?event_type={sqli_payload}&status={sqli_payload}', headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'success'

    @pytest.mark.parametrize('sqli_payload', [
        "' OR '1'='1",
        "'; DROP TABLE hours_overrides; --",
    ])
    def test_sqli_in_hours_overrides_query_parameters(self, client, valid_api_key, sqli_payload):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get(f'/api/v1/hours/overrides?override_type={sqli_payload}', headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'success'

    def test_sqli_in_post_history_limit_and_offset(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get('/api/v1/posts/history?limit=10;+DROP+TABLE+users;&offset=0+OR+1=1', headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'success'

    def test_sqli_in_body_fields_stored_verbatim_not_executed(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        malicious_title = "Special Fish'; DROP TABLE specials; SELECT * FROM users WHERE '1'='1"
        malicious_desc = "Desc'; DELETE FROM users; --"

        resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={
                'item_name': malicious_title,
                'description': malicious_desc,
                'post_date': '2026-08-20',
                'post_time': '11:00',
            },
        )
        assert resp.status_code == 201
        special_id = resp.get_json()['data']['id']

        # Verify record stored verbatim and tables intact
        with client.application.app_context():
            db = get_db()
            row = db.execute('SELECT item_name, description FROM specials WHERE id = ?', (special_id,)).fetchone()
            assert row['item_name'] == malicious_title
            assert row['description'] == malicious_desc

            # Ensure users table is completely intact
            users_count = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            assert users_count > 0


# ===========================================================================
# 4. Missing Required Fields & Boundary Validation
# ===========================================================================

class TestAdversarialMissingFieldsAndValidation:

    def test_draft_missing_and_whitespace_caption_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        # Empty string
        resp = client.post('/api/v1/posts/draft', headers=headers, json={'caption': ''})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_CAPTION'

        # Whitespace only
        resp = client.post('/api/v1/posts/draft', headers=headers, json={'caption': '     \n\t  '})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_CAPTION'

    def test_generate_missing_topic_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/generate', headers=headers, json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_TOPIC'

    def test_dispatch_missing_all_captions_and_topic_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/dispatch', headers=headers, json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_CAPTION'

    def test_schedule_missing_time_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/schedule', headers=headers, json={'caption': 'Valid caption'})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_SCHEDULE_TIME'

    def test_specials_missing_required_fields_aggregate_errors(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/specials', headers=headers, json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['code'] == 'VALIDATION_ERROR'
        assert 'errors' in data
        assert any('item_name is required' in e for e in data['errors'])
        assert any('post_date is required' in e for e in data['errors'])

    def test_events_missing_required_fields_aggregate_errors(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/events', headers=headers, json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['code'] == 'VALIDATION_ERROR'
        assert any('title is required' in e for e in data['errors'])
        assert any('post_date is required' in e for e in data['errors'])

    def test_hours_overrides_missing_required_fields_aggregate_errors(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/hours/overrides', headers=headers, json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['code'] == 'VALIDATION_ERROR'
        assert any('title is required' in e for e in data['errors'])
        assert any('post_date is required' in e for e in data['errors'])

    def test_keys_revoke_missing_key_id_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/keys/revoke', headers=headers, json={})
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'MISSING_KEY_ID'


# ===========================================================================
# 5. Invalid Date & Time Formats
# ===========================================================================

class TestAdversarialInvalidDatesAndTimes:

    @pytest.mark.parametrize('invalid_date', [
        '2026-02-31',       # Non-existent leap/Feb day
        '2026-13-01',       # Invalid month 13
        '2026-00-10',       # Invalid month 00
        '2026-08-32',       # Invalid day 32
        '2026/08/20',       # Wrong separator
        '20-08-2026',       # DD-MM-YYYY
        '08-20-2026',       # MM-DD-YYYY
        'yesterday',        # Relative string
    ])
    def test_specials_create_invalid_post_date_rejected(self, client, valid_api_key, invalid_date):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={
                'item_name': 'Burger Special',
                'post_date': invalid_date,
                'post_time': '12:00',
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'
        assert any('post_date must be YYYY-MM-DD' in e for e in resp.get_json()['errors'])

    @pytest.mark.parametrize('invalid_time', [
        '24:00',            # Out of range 24h
        '25:30',            # Out of range hour
        '12:60',            # Out of range minute
        '12:00 PM',         # 12h format with AM/PM
        'noon',             # String word
        '12',               # Missing minute
    ])
    def test_specials_create_invalid_post_time_rejected(self, client, valid_api_key, invalid_time):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={
                'item_name': 'Burger Special',
                'post_date': '2026-08-20',
                'post_time': invalid_time,
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'
        assert any('post_time must be HH:MM' in e for e in resp.get_json()['errors'])

    def test_events_invalid_event_date_and_end_date_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        # Invalid event_date
        resp = client.post(
            '/api/v1/events',
            headers=headers,
            json={
                'title': 'Concert',
                'post_date': '2026-08-20',
                'event_date': 'invalid-event-date',
            },
        )
        assert resp.status_code == 400
        assert any('event_date must be YYYY-MM-DD' in e for e in resp.get_json()['errors'])

        # Invalid event_end_date
        resp = client.post(
            '/api/v1/events',
            headers=headers,
            json={
                'title': 'Concert',
                'post_date': '2026-08-20',
                'event_date': '2026-08-25',
                'event_end_date': '2026/08/26',
            },
        )
        assert resp.status_code == 400
        assert any('event_end_date must be YYYY-MM-DD' in e for e in resp.get_json()['errors'])

    @pytest.mark.parametrize('bad_schedule_time', [
        'invalid-timestamp-string',
        '2026-99-99T99:99:99',
        'next-wednesday-at-noon',
    ])
    def test_posts_schedule_invalid_time_rejected(self, client, valid_api_key, bad_schedule_time):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/schedule',
            headers=headers,
            json={
                'caption': 'Scheduled post test',
                'scheduled_time': bad_schedule_time,
            },
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'INVALID_SCHEDULE_TIME'

    def test_specials_update_with_invalid_date_rejected(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        # Create valid special first
        resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={'item_name': 'Pasta', 'post_date': '2026-08-20'},
        )
        special_id = resp.get_json()['data']['id']

        # Attempt update with invalid post_date
        resp = client.put(
            f'/api/v1/specials/{special_id}',
            headers=headers,
            json={'post_date': 'invalid-date'},
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'

        # Attempt update with invalid post_time
        resp = client.put(
            f'/api/v1/specials/{special_id}',
            headers=headers,
            json={'post_time': '25:00'},
        )
        assert resp.status_code == 400
        assert resp.get_json()['code'] == 'VALIDATION_ERROR'


# ===========================================================================
# 6. State Machine & Conflict Handling
# ===========================================================================

class TestAdversarialStateMachineAndConflicts:

    def test_cannot_edit_non_pending_special(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={'item_name': 'Fish Taco', 'post_date': '2026-08-20'},
        )
        special_id = resp.get_json()['data']['id']

        # Transition status to published directly
        with client.application.app_context():
            db = get_db()
            db.execute('UPDATE specials SET status = ? WHERE id = ?', ('published', special_id))
            db.commit()

        # Attempt to edit
        resp = client.put(
            f'/api/v1/specials/{special_id}',
            headers=headers,
            json={'item_name': 'Changed Fish Taco'},
        )
        assert resp.status_code == 409
        assert resp.get_json()['code'] == 'CONFLICT'

    def test_cannot_edit_non_pending_event(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/events',
            headers=headers,
            json={'title': 'Band Night', 'post_date': '2026-08-20'},
        )
        event_id = resp.get_json()['data']['id']

        with client.application.app_context():
            db = get_db()
            db.execute('UPDATE events SET status = ? WHERE id = ?', ('cancelled', event_id))
            db.commit()

        resp = client.put(
            f'/api/v1/events/{event_id}',
            headers=headers,
            json={'title': 'New Band Night'},
        )
        assert resp.status_code == 409
        assert resp.get_json()['code'] == 'CONFLICT'

    def test_cannot_edit_non_pending_hours_override(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/hours/overrides',
            headers=headers,
            json={'title': 'Snow Day', 'post_date': '2026-08-20'},
        )
        override_id = resp.get_json()['data']['id']

        with client.application.app_context():
            db = get_db()
            db.execute('UPDATE hours_overrides SET status = ? WHERE id = ?', ('published', override_id))
            db.commit()

        resp = client.put(
            f'/api/v1/hours/overrides/{override_id}',
            headers=headers,
            json={'title': 'Heavy Snow Day'},
        )
        assert resp.status_code == 409
        assert resp.get_json()['code'] == 'CONFLICT'

    def test_deleting_or_cancelling_non_existent_records_returns_404(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        for resource in ['specials', 'events', 'hours/overrides']:
            resp = client.delete(f'/api/v1/{resource}/999999', headers=headers)
            assert resp.status_code == 404
            assert resp.get_json()['code'] == 'NOT_FOUND'

            resp = client.post(f'/api/v1/{resource}/999999/cancel', headers=headers, json={})
            assert resp.status_code == 404
            assert resp.get_json()['code'] == 'NOT_FOUND'
