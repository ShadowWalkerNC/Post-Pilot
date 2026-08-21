"""
tests/test_api_v1.py
Comprehensive unit and integration tests for Unified Headless REST API (/api/v1/*).

Coverage:
  1. Authentication & Security (Bearer keys, hashing, expiry, revocation, SRN secret, IDOR prevention)
  2. Health & SRN Manifest
  3. Post Drafts (/api/v1/posts/draft)
  4. AI Caption Generation (/api/v1/posts/generate & /v1/generate_post)
  5. Post Dispatch & Publishing (/api/v1/posts/dispatch, /v1/publish_post, /v1/generate_and_publish)
  6. Post Scheduling (/api/v1/posts/schedule)
  7. Post History (/api/v1/posts/history & /v1/get_history)
  8. Specials CRUD (/api/v1/specials)
  9. Events CRUD (/api/v1/events)
  10. Hours Overrides CRUD (/api/v1/hours/overrides)
  11. Analytics Summary (/api/v1/analytics/summary)
  12. Response Envelopes (Standard status/data and status/error/code)
  13. API Key Management (/api/v1/keys/*)
"""

import time
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. Authentication & Security
# ---------------------------------------------------------------------------

class TestAPIv1Auth:

    def test_missing_auth_header_rejected_401(self, client):
        resp = client.get('/api/v1/posts/history')
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'MISSING_AUTH'
        assert data['success'] is False

    def test_invalid_api_key_rejected_401(self, client):
        headers = {'Authorization': 'Bearer pp_live_nonexistent_key_999'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'INVALID_KEY'

    def test_expired_api_key_rejected_401(self, client, expired_api_key):
        headers = {'Authorization': f'Bearer {expired_api_key}'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'KEY_EXPIRED'

    def test_revoked_api_key_rejected_401(self, client, revoked_api_key):
        headers = {'Authorization': f'Bearer {revoked_api_key}'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] in ('INVALID_KEY', 'REVOKED_KEY')

    def test_valid_api_key_accepted(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get('/api/v1/posts/history', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'posts' in data['data']

    def test_srn_secret_bypass_accepted(self, client, monkeypatch):
        monkeypatch.setenv('SRN_SECRET', 'test_srn_secret_12345')
        headers = {
            'Authorization': 'Bearer test_srn_secret_12345',
            'X-SRN-App': 'SigilBot',
        }
        resp = client.get('/api/v1/posts/history?user_id=00000000-0000-4000-8000-000000000001', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'

    def test_idor_prevention_user_id_pinned_to_api_key_owner(self, client, valid_api_key, registered_user):
        """User API key must never operate on a different user's data even if supplied."""
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/draft',
            headers=headers,
            json={
                'user_id': 'victim_user_id_9999',  # Attacker attempts IDOR
                'caption': 'IDOR test draft',
                'platforms': ['fb'],
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        post_id = int(data['data']['post_id'])

        # Verify draft was created for registered_user['id'], not victim_user_id_9999
        from modules.database import get_db
        with client.application.app_context():
            db = get_db()
            row = db.execute('SELECT user_id FROM post_history WHERE id = ?', (post_id,)).fetchone()
            assert row['user_id'] == registered_user['id']


# ---------------------------------------------------------------------------
# 2. Health & Manifest
# ---------------------------------------------------------------------------

class TestAPIv1HealthAndManifest:

    def test_health_public_no_auth(self, client):
        resp = client.get('/api/v1/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'ok'
        assert data['data']['app'] == 'post-pilot'

    def test_health_legacy_alias(self, client):
        resp = client.get('/v1/health')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success' or data.get('status') == 'ok'

    def test_manifest_requires_auth(self, client):
        resp = client.get('/api/v1/manifest')
        assert resp.status_code == 401

    def test_manifest_with_auth(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get('/api/v1/manifest', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'tools' in data['data']
        tools = [t['name'] for t in data['data']['tools']]
        assert 'draft_post' in tools
        assert 'generate_post' in tools
        assert 'dispatch_post' in tools


# ---------------------------------------------------------------------------
# 3. Post Drafts
# ---------------------------------------------------------------------------

class TestAPIv1PostsDraft:

    def test_create_draft_minimal(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/draft',
            headers=headers,
            json={'caption': 'Draft test caption'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'draft'
        assert data['data']['caption'] == 'Draft test caption'
        assert 'post_id' in data['data']

    def test_create_draft_full_payload(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        payload = {
            'caption': 'Full draft with media and scheduled time',
            'platforms': ['fb', 'ig', 'tw'],
            'media_urls': ['https://example.com/image.jpg'],
            'scheduled_time': '2026-09-01T12:00:00Z',
            'tags': ['#foodtruck', '#special'],
        }
        resp = client.post('/api/v1/posts/draft', headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['image_url'] == 'https://example.com/image.jpg'
        assert data['data']['tags'] == ['#foodtruck', '#special']

    def test_create_draft_missing_caption_fails(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/draft', headers=headers, json={'caption': ''})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'MISSING_CAPTION'


# ---------------------------------------------------------------------------
# 4. AI Caption Generation
# ---------------------------------------------------------------------------

class TestAPIv1PostsGenerate:

    def test_generate_missing_topic_fails(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/generate', headers=headers, json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'MISSING_TOPIC'

    def test_generate_happy_path(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        payload = {
            'topic': 'Smoked Brisket Tacos special',
            'platforms': ['fb', 'ig'],
            'tone': 'hype',
        }
        resp = client.post('/api/v1/posts/generate', headers=headers, json=payload)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'caption' in data['data']
        assert 'master' in data['data']
        assert 'adapted' in data['data']
        assert 'fb' in data['data']['adapted']
        assert 'ig' in data['data']['adapted']

    def test_generate_legacy_alias(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/v1/generate_post',
            headers=headers,
            json={'topic': 'Friday Burger Night', 'platform': 'instagram'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success' or data.get('success') is True
        assert 'caption' in data.get('data', {})


# ---------------------------------------------------------------------------
# 5. Post Dispatch & Publishing
# ---------------------------------------------------------------------------

class TestAPIv1PostsDispatch:

    def test_dispatch_missing_caption_fails(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/posts/dispatch', headers=headers, json={'caption': ''})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'MISSING_CAPTION'

    def test_dispatch_validation_failure_for_ig_without_image(self, client, valid_api_key):
        """Instagram requires image_url for image posts."""
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/dispatch',
            headers=headers,
            json={
                'caption': 'Post to instagram without image',
                'platforms': ['ig'],
                'content_type': 'image',
                'image_url': None,
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'VALIDATION_ERROR'

    @patch('modules.publisher.UniversalPublisher.push_all')
    def test_dispatch_happy_path(self, mock_push_all, client, valid_api_key):
        mock_push_all.return_value = {
            'fb': {'success': True, 'post_id': 'fb_12345'},
            'web': {'success': True},
        }
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/dispatch',
            headers=headers,
            json={
                'caption': 'Dispatch test caption for facebook and website',
                'platforms': ['fb', 'web'],
                'content_type': 'text',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'published'
        assert 'post_id' in data['data']
        assert data['data']['results']['fb']['success'] is True

    @patch('modules.publisher.UniversalPublisher.push_all')
    def test_dispatch_one_shot_generate_and_publish(self, mock_push_all, client, valid_api_key):
        mock_push_all.return_value = {'fb': {'success': True}}
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/generate_and_publish',
            headers=headers,
            json={'topic': 'One shot special tacos', 'platforms': ['fb']},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'post_id' in data['data']


# ---------------------------------------------------------------------------
# 6. Post Scheduling
# ---------------------------------------------------------------------------

class TestAPIv1PostsSchedule:

    def test_schedule_missing_time_fails(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/schedule',
            headers=headers,
            json={'caption': 'Scheduled post test'},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'MISSING_SCHEDULE_TIME'

    def test_schedule_happy_path_unix_timestamp(self, client, valid_api_key):
        future_ts = int(time.time()) + 86400
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/schedule',
            headers=headers,
            json={
                'caption': 'Future post scheduled with unix timestamp',
                'scheduled_time': future_ts,
                'platforms': ['fb', 'ig'],
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'scheduled'
        assert data['data']['scheduled_at'] == future_ts

    def test_schedule_happy_path_iso_string(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post(
            '/api/v1/posts/schedule',
            headers=headers,
            json={
                'caption': 'Future post scheduled with ISO datetime',
                'scheduled_time': '2026-10-15T15:30:00Z',
                'platforms': ['fb'],
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['data']['status'] == 'scheduled'
        assert isinstance(data['data']['scheduled_at'], int)


# ---------------------------------------------------------------------------
# 7. Post History
# ---------------------------------------------------------------------------

class TestAPIv1PostsHistory:

    def test_history_pagination_and_filters(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # Seed 2 draft posts and 1 scheduled post
        client.post('/api/v1/posts/draft', headers=headers, json={'caption': 'History draft 1'})
        client.post('/api/v1/posts/draft', headers=headers, json={'caption': 'History draft 2'})
        client.post(
            '/api/v1/posts/schedule',
            headers=headers,
            json={'caption': 'History sched 1', 'scheduled_time': int(time.time()) + 3600},
        )

        # Get all history
        resp = client.get('/api/v1/posts/history?limit=10&offset=0', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert len(data['data']['posts']) >= 3

        # Filter by draft status
        resp_drafts = client.get('/api/v1/posts/history?status=draft', headers=headers)
        assert resp_drafts.status_code == 200
        data_drafts = resp_drafts.get_json()
        assert all(p['status'] == 'draft' for p in data_drafts['data']['posts'])

        # Legacy alias test
        resp_legacy = client.get('/v1/get_history?limit=5', headers=headers)
        assert resp_legacy.status_code == 200


# ---------------------------------------------------------------------------
# 8. Specials CRUD
# ---------------------------------------------------------------------------

class TestAPIv1SpecialsCRUD:

    def test_create_special_happy_path(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        payload = {
            'item_name': 'Truffle Mushroom Burger',
            'description': 'With aged swiss and garlic aioli',
            'post_date': '2026-08-25',
            'post_time': '11:30',
            'platforms': ['fb', 'ig', 'tt'],
            'content_type': 'daily_special',
            'tone': 'hype',
        }
        resp = client.post('/api/v1/specials', headers=headers, json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'id' in data['data']
        assert data['data']['id'] is not None

    def test_create_special_validation_error(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.post('/api/v1/specials', headers=headers, json={'item_name': ''})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['status'] == 'error'
        assert data['code'] == 'VALIDATION_ERROR'

    def test_specials_lifecycle_crud(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # 1. Create
        create_resp = client.post(
            '/api/v1/specials',
            headers=headers,
            json={
                'item_name': 'Birria Ramen',
                'post_date': '2026-08-28',
                'post_time': '12:00',
                'platforms': ['fb', 'ig'],
            },
        )
        assert create_resp.status_code == 201
        special_id = create_resp.get_json()['data']['id']

        # 2. Get Single
        get_resp = client.get(f'/api/v1/specials/{special_id}', headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.get_json()['data']['special']['item_name'] == 'Birria Ramen'

        # 3. List
        list_resp = client.get('/api/v1/specials?post_date=2026-08-28', headers=headers)
        assert list_resp.status_code == 200
        assert any(s['id'] == special_id for s in list_resp.get_json()['data']['specials'])

        # 4. Update (PUT/PATCH)
        update_resp = client.patch(
            f'/api/v1/specials/{special_id}',
            headers=headers,
            json={'item_name': 'Mega Birria Ramen', 'tone': 'urgent'},
        )
        assert update_resp.status_code == 200

        get_updated = client.get(f'/api/v1/specials/{special_id}', headers=headers)
        assert get_updated.get_json()['data']['special']['item_name'] == 'Mega Birria Ramen'
        assert get_updated.get_json()['data']['special']['tone'] == 'urgent'

        # 5. Cancel
        cancel_resp = client.post(f'/api/v1/specials/{special_id}/cancel', headers=headers)
        assert cancel_resp.status_code == 200
        get_cancelled = client.get(f'/api/v1/specials/{special_id}', headers=headers)
        assert get_cancelled.get_json()['data']['special']['status'] == 'cancelled'

        # 6. Cannot update cancelled special (conflict 409)
        fail_update = client.put(
            f'/api/v1/specials/{special_id}',
            headers=headers,
            json={'item_name': 'Illegal update'},
        )
        assert fail_update.status_code == 409

        # 7. Delete
        del_resp = client.delete(f'/api/v1/specials/{special_id}', headers=headers)
        assert del_resp.status_code == 200

        # Verify 404 after delete
        not_found_resp = client.get(f'/api/v1/specials/{special_id}', headers=headers)
        assert not_found_resp.status_code == 404


# ---------------------------------------------------------------------------
# 9. Events CRUD
# ---------------------------------------------------------------------------

class TestAPIv1EventsCRUD:

    def test_events_lifecycle_crud(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # 1. Create
        create_resp = client.post(
            '/api/v1/events',
            headers=headers,
            json={
                'title': 'Live Jazz Night',
                'description': 'Enjoy craft cocktails and smooth tunes',
                'event_date': '2026-09-10',
                'post_date': '2026-09-08',
                'post_time': '18:00',
                'event_type': 'concert',
                'tone': 'hype',
                'platforms': ['fb', 'ig', 'gb'],
            },
        )
        assert create_resp.status_code == 201
        event_id = create_resp.get_json()['data']['id']

        # 2. Get Single
        get_resp = client.get(f'/api/v1/events/{event_id}', headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.get_json()['data']['event']['title'] == 'Live Jazz Night'

        # 3. List with filters
        list_resp = client.get('/api/v1/events?event_type=concert', headers=headers)
        assert list_resp.status_code == 200
        assert any(e['id'] == event_id for e in list_resp.get_json()['data']['events'])

        # 4. Update
        update_resp = client.put(
            f'/api/v1/events/{event_id}',
            headers=headers,
            json={'title': 'Live Jazz & Wine Night'},
        )
        assert update_resp.status_code == 200

        # 5. Cancel
        cancel_resp = client.post(f'/api/v1/events/{event_id}/cancel', headers=headers)
        assert cancel_resp.status_code == 200

        # 6. Delete
        del_resp = client.delete(f'/api/v1/events/{event_id}', headers=headers)
        assert del_resp.status_code == 200

        not_found_resp = client.get(f'/api/v1/events/{event_id}', headers=headers)
        assert not_found_resp.status_code == 404


# ---------------------------------------------------------------------------
# 10. Hours Overrides CRUD
# ---------------------------------------------------------------------------

class TestAPIv1HoursOverridesCRUD:

    def test_hours_overrides_lifecycle_crud(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # 1. Create
        create_resp = client.post(
            '/api/v1/hours/overrides',
            headers=headers,
            json={
                'title': 'Closed for Labor Day',
                'message': 'We will be back on Tuesday with fresh specials!',
                'override_type': 'holiday',
                'post_date': '2026-09-06',
                'post_time': '09:00',
                'platforms': ['fb', 'ig', 'gb', 'web'],
            },
        )
        assert create_resp.status_code == 201
        override_id = create_resp.get_json()['data']['id']

        # 2. Get Single
        get_resp = client.get(f'/api/v1/hours/overrides/{override_id}', headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.get_json()['data']['override']['title'] == 'Closed for Labor Day'

        # 3. List
        list_resp = client.get('/api/v1/hours/overrides?override_type=holiday', headers=headers)
        assert list_resp.status_code == 200
        assert any(o['id'] == override_id for o in list_resp.get_json()['data']['overrides'])

        # 4. Update
        update_resp = client.patch(
            f'/api/v1/hours/overrides/{override_id}',
            headers=headers,
            json={'message': 'Updated message for holiday closure'},
        )
        assert update_resp.status_code == 200

        # 5. Cancel
        cancel_resp = client.post(f'/api/v1/hours/overrides/{override_id}/cancel', headers=headers)
        assert cancel_resp.status_code == 200

        # 6. Delete
        del_resp = client.delete(f'/api/v1/hours/overrides/{override_id}', headers=headers)
        assert del_resp.status_code == 200

        not_found_resp = client.get(f'/api/v1/hours/overrides/{override_id}', headers=headers)
        assert not_found_resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. Analytics Summary
# ---------------------------------------------------------------------------

class TestAPIv1Analytics:

    def test_analytics_summary_empty_tokens(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}
        resp = client.get('/api/v1/analytics/summary?days=30', headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'kpis' in data['data']
        assert 'chart' in data['data']
        assert data['data']['kpis']['posts'] == 0


# ---------------------------------------------------------------------------
# 12. Response Envelopes & Error Consistency
# ---------------------------------------------------------------------------

class TestAPIv1EnvelopeConsistency:

    def test_success_envelope_structure(self, client):
        resp = client.get('/api/v1/health')
        data = resp.get_json()
        assert 'status' in data
        assert data['status'] == 'success'
        assert 'data' in data

    def test_error_envelope_structure(self, client):
        resp = client.get('/api/v1/posts/history')
        assert resp.status_code == 401
        data = resp.get_json()
        assert 'status' in data
        assert data['status'] == 'error'
        assert 'message' in data
        assert 'code' in data


# ---------------------------------------------------------------------------
# 13. API Key Management
# ---------------------------------------------------------------------------

class TestAPIv1KeyManagement:

    def test_key_creation_list_and_revoke(self, client, valid_api_key):
        headers = {'Authorization': f'Bearer {valid_api_key}'}

        # 1. Create key
        create_resp = client.post(
            '/api/v1/keys/create',
            headers=headers,
            json={'label': 'Integration Bot', 'ttl_days': 30},
        )
        assert create_resp.status_code == 200
        data = create_resp.get_json()
        assert data['status'] == 'success'
        new_key = data['data']['key']
        assert new_key.startswith('pp_live_')

        # 2. List keys
        list_resp = client.get('/api/v1/keys', headers=headers)
        assert list_resp.status_code == 200
        keys = list_resp.get_json()['data']['keys']
        assert any(k['label'] == 'Integration Bot' for k in keys)

        # 3. Revoke key
        key_id = next(k['id'] for k in keys if k['label'] == 'Integration Bot')
        revoke_resp = client.post(
            '/api/v1/keys/revoke',
            headers=headers,
            json={'key_id': key_id},
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.get_json()['data']['revoked'] is True
