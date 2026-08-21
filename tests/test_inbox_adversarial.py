"""
tests/test_inbox_adversarial.py
Adversarial Stress Test Suite for Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller).

Focus:
1. Multi-Tenancy & Cross-User Data Isolation:
   - IDOR attacks on all moderation endpoints (/reply, /regenerate, /hide, /skip).
   - Scoped DB mutation prevention across users.
   - Query isolation for items, stats, and poller tokens.
2. Error Handling & API Resilience:
   - Meta Graph API error codes (OAuth 190, Rate Limit 17, Permissions 200, Server 500).
   - Network faults (timeouts, connection errors, malformed payloads).
   - Multi-user poller resilience under partial network failures.
3. Database Integrity & State Transitions:
   - Comprehensive status transition lifecycle.
   - Deduplication resilience and extreme input sanitization / handling.
"""

import os
import json
import time
from contextlib import contextmanager
import requests
from unittest.mock import patch, MagicMock
import pytest

from modules.database import get_db
from modules.models import InboxItem
from modules.meta_api import MetaAPI
from modules.reply_agent import classify_sentiment, analyze_and_draft, TONES, SENTIMENTS
from modules.comment_poller import poll_user_comments, poll_all_active_users
from tests.conftest import _make_mock_user


USER_A_ID = '00000000-0000-4000-8000-000000000001'
USER_B_ID = '00000000-0000-4000-8000-000000000002'
USER_C_ID = '00000000-0000-4000-8000-000000000003'


@contextmanager
def auth_user_session(client, app, user_id=USER_A_ID, email='user@test.dev', tier='starter'):
    """Helper context manager to set up authenticated session for test user."""
    mock_user = _make_mock_user(user_id, email, tier=tier)

    def _loader(uid):
        if str(uid) == str(user_id):
            return mock_user
        return None

    with patch.object(app.login_manager, '_user_callback', _loader):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True
        client._test_user = mock_user
        yield mock_user


@pytest.fixture(autouse=True)
def clean_inbox_table(app):
    with app.app_context():
        db = get_db()
        db.execute('DELETE FROM inbox_items')
        db.commit()
    yield
    with app.app_context():
        db = get_db()
        db.execute('DELETE FROM inbox_items')
        db.commit()


# ===========================================================================
# 1. Multi-Tenancy & Cross-User Data Isolation
# ===========================================================================

class TestMultiTenancyAdversarial:
    """Stress-test strict data isolation between multiple concurrent tenants."""

    def test_idor_cross_user_all_moderation_endpoints(self, client, app):
        """Verify User B cannot alter User A's inbox items through any action."""
        with app.app_context():
            item_a = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='fb_comment_user_a',
                comment_text='User A sensitive comment',
                sentiment='positive',
                ai_draft_reply='Draft A',
                status=InboxItem.STATUS_PENDING,
            )

        # Logged in as User B (Pro tier so permissions would otherwise allow actions)
        with auth_user_session(client, app, USER_B_ID, tier='pro'):
            # 1. Attempt Reply
            resp_reply = client.post(
                f'/api/inbox/{item_a.id}/reply',
                json={'reply_text': 'Hostile reply takeover'}
            )
            assert resp_reply.status_code == 404
            assert resp_reply.get_json()['error'] == 'Item not found'

            # 2. Attempt Regenerate
            resp_regen = client.post(
                f'/api/inbox/{item_a.id}/regenerate',
                json={'tone': 'urgent'}
            )
            assert resp_regen.status_code == 404
            assert resp_regen.get_json()['error'] == 'Item not found'

            # 3. Attempt Hide
            resp_hide = client.post(f'/api/inbox/{item_a.id}/hide')
            assert resp_hide.status_code == 404
            assert resp_hide.get_json()['error'] == 'Item not found'

            # 4. Attempt Skip
            resp_skip = client.post(f'/api/inbox/{item_a.id}/skip')
            assert resp_skip.status_code == 404
            assert resp_skip.get_json()['error'] == 'Item not found'

        # Verify User A's item remains completely untouched
        with app.app_context():
            refreshed = InboxItem.get_by_id(item_a.id)
            assert refreshed is not None
            assert refreshed.status == InboxItem.STATUS_PENDING
            assert refreshed.ai_draft_reply == 'Draft A'
            assert refreshed.final_reply is None
            assert refreshed.hidden_at is None
            assert refreshed.replied_at is None

    def test_model_layer_user_scoped_mutations(self, app):
        """Verify model methods reject updates when user_id does not match."""
        with app.app_context():
            item_a = InboxItem.create(
                user_id=USER_A_ID,
                platform='ig',
                platform_comment_id='ig_comment_user_a',
                comment_text='Original comment',
                sentiment='neutral',
                ai_draft_reply='Original draft',
                status=InboxItem.STATUS_PENDING,
            )

            # User B attempts mutation via model helpers with mismatched user_id
            InboxItem.update_draft(item_a.id, user_id=USER_B_ID, new_draft='Hacked draft')
            refreshed = InboxItem.get_by_id(item_a.id)
            assert refreshed.ai_draft_reply == 'Original draft'

            InboxItem.mark_replied(item_a.id, user_id=USER_B_ID, final_reply='Hacked reply')
            refreshed = InboxItem.get_by_id(item_a.id)
            assert refreshed.status == InboxItem.STATUS_PENDING
            assert refreshed.final_reply is None

            InboxItem.mark_hidden(item_a.id, user_id=USER_B_ID)
            refreshed = InboxItem.get_by_id(item_a.id)
            assert refreshed.status == InboxItem.STATUS_PENDING
            assert refreshed.hidden_at is None

            InboxItem.mark_skipped(item_a.id, user_id=USER_B_ID)
            refreshed = InboxItem.get_by_id(item_a.id)
            assert refreshed.status == InboxItem.STATUS_PENDING

    def test_multi_user_data_leakage_in_lists_and_stats(self, client, app):
        """Verify complete partition of list and aggregation stats among 3 tenants."""
        with app.app_context():
            # User A: 3 items (2 pending, 1 approved)
            InboxItem.create(USER_A_ID, 'fb', 'a1', 'Text A1', sentiment='positive', status='pending')
            InboxItem.create(USER_A_ID, 'fb', 'a2', 'Text A2', sentiment='question', status='pending')
            InboxItem.create(USER_A_ID, 'ig', 'a3', 'Text A3', sentiment='neutral', status='approved')

            # User B: 2 items (1 pending, 1 hidden)
            InboxItem.create(USER_B_ID, 'fb', 'b1', 'Text B1', sentiment='negative', status='pending')
            InboxItem.create(USER_B_ID, 'ig', 'b2', 'Text B2', sentiment='spam', status='hidden')

            # User C: 1 item (1 skipped)
            InboxItem.create(USER_C_ID, 'fb', 'c1', 'Text C1', sentiment='positive', status='skipped')

        # Test User A view
        with auth_user_session(client, app, USER_A_ID, tier='starter'):
            resp = client.get('/api/inbox/items?status=all')
            data = resp.get_json()
            assert data['total'] == 3
            assert {i['platform_comment_id'] for i in data['items']} == {'a1', 'a2', 'a3'}

            resp_stats = client.get('/api/inbox/stats')
            stats_a = resp_stats.get_json()['stats']
            assert stats_a['total'] == 3
            assert stats_a['pending'] == 2
            assert stats_a['approved'] == 1
            assert stats_a['hidden'] == 0
            assert stats_a['skipped'] == 0
            assert stats_a['sentiment']['positive'] == 1
            assert stats_a['sentiment']['question'] == 1
            assert stats_a['sentiment']['neutral'] == 1
            assert stats_a['sentiment']['negative'] == 0

        # Test User B view
        with auth_user_session(client, app, USER_B_ID, tier='starter'):
            resp = client.get('/api/inbox/items?status=all')
            data = resp.get_json()
            assert data['total'] == 2
            assert {i['platform_comment_id'] for i in data['items']} == {'b1', 'b2'}

            resp_stats = client.get('/api/inbox/stats')
            stats_b = resp_stats.get_json()['stats']
            assert stats_b['total'] == 2
            assert stats_b['pending'] == 1
            assert stats_b['hidden'] == 1
            assert stats_b['sentiment']['negative'] == 1
            assert stats_b['sentiment']['spam'] == 1
            assert stats_b['sentiment']['positive'] == 0


# ===========================================================================
# 2. Error Handling & API Resilience
# ===========================================================================

class TestErrorHandlingAndResilience:
    """Stress-test network errors, API timeouts, invalid payloads, and error codes."""

    @patch('requests.get')
    def test_meta_api_network_timeout(self, mock_get):
        """Test MetaAPI behavior when network times out."""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out to graph.facebook.com")
        api = MetaAPI(access_token='tok', page_id='page1')

        with pytest.raises(requests.exceptions.Timeout):
            api.get_facebook_comments('post1')

    @patch('requests.get')
    def test_meta_api_graph_error_codes(self, mock_get):
        """Test MetaAPI handling standard Graph API error responses."""
        # 1. OAuth expired
        mock_get.return_value.json.return_value = {
            'error': {
                'message': 'Error validating access token: Session has expired.',
                'type': 'OAuthException',
                'code': 190,
                'error_subcode': 463
            }
        }
        api = MetaAPI(access_token='expired_tok', page_id='page1')
        res = api.get_facebook_comments('post1')
        assert 'error' in res
        assert res['error']['code'] == 190

        # 2. Rate limited
        mock_get.return_value.json.return_value = {
            'error': {
                'message': 'User request limit reached',
                'type': 'OAuthException',
                'code': 17
            }
        }
        res_rl = api.get_instagram_comments('ig_media_1')
        assert 'error' in res_rl
        assert res_rl['error']['code'] == 17

    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    def test_poller_resilience_when_meta_posts_fail(self, mock_get_posts, mock_load_token, app):
        """Verify poller does not crash when get_page_posts raises exception."""
        mock_load_token.return_value = {
            'access_token': 'mock_token',
            'meta': {'page_id': 'fb_page_10', 'ig_id': 'ig_10'}
        }
        mock_get_posts.side_effect = requests.exceptions.ConnectionError("Failed to reach Meta")

        with app.app_context():
            result = poll_user_comments(USER_A_ID)
            assert result['success'] is False
            assert len(result['errors']) > 0
            assert "Facebook comment polling error" in result['errors'][0]

    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    @patch.object(MetaAPI, 'get_instagram_comments')
    def test_poller_partial_failure_isolation(self, mock_ig_comments, mock_get_posts, mock_load_token, app):
        """If Facebook fails, Instagram should still be polled successfully."""
        mock_load_token.return_value = {
            'access_token': 'mock_token',
            'meta': {'page_id': 'fb_page_10', 'ig_id': 'ig_10'}
        }
        # FB fails
        mock_get_posts.side_effect = Exception("FB API down")
        # IG succeeds
        mock_ig_comments.return_value = {
            'data': [
                {'id': 'ig_c_resilient', 'text': 'I love your drinks!', 'username': 'fan', 'timestamp': '2026-08-19T14:00:00Z'}
            ]
        }

        with app.app_context():
            result = poll_user_comments(USER_A_ID)
            assert result['new'] == 1
            assert result['fetched'] == 1
            # IG item was persisted despite FB error
            saved = InboxItem.get_by_comment_id('ig', 'ig_c_resilient', user_id=USER_A_ID)
            assert saved is not None
            assert saved.comment_text == 'I love your drinks!'

    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    @patch.object(MetaAPI, 'get_facebook_comments')
    def test_poller_handles_malformed_comment_objects(self, mock_get_comments, mock_get_posts, mock_load_token, app):
        """Poller skips comments with missing id or empty message safely."""
        mock_load_token.return_value = {
            'access_token': 'mock_token',
            'meta': {'page_id': 'fb_page_10', 'ig_id': ''}
        }
        mock_get_posts.return_value = {
            'data': [{'id': 'post_100', 'message': 'Menu update'}]
        }
        mock_get_comments.return_value = {
            'data': [
                {'id': None, 'message': 'Missing ID'},
                {'id': 'c_valid', 'message': '   '}, # Empty whitespace message
                {'id': 'c_good', 'message': 'Valid positive message!'},
            ]
        }

        with app.app_context():
            result = poll_user_comments(USER_A_ID)
            assert result['success'] is True
            assert result['new'] == 1
            assert InboxItem.get_by_comment_id('fb', 'c_good') is not None

    def test_reply_endpoint_handles_empty_or_malformed_payload(self, client, app):
        """Moderation reply endpoint returns clean 400 on empty or whitespace reply."""
        with app.app_context():
            item = InboxItem.create(USER_A_ID, 'fb', 'c_empty_test', 'Nice place', sentiment='positive')

        with auth_user_session(client, app, USER_A_ID, tier='pro'):
            # Empty JSON
            resp = client.post(f'/api/inbox/{item.id}/reply', json={})
            assert resp.status_code == 400
            assert resp.get_json()['error'] == 'Reply text is required'

            # Whitespace JSON
            resp2 = client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': '   \n  \t'})
            assert resp2.status_code == 400
            assert resp2.get_json()['error'] == 'Reply text is required'

    @patch.object(MetaAPI, 'reply_to_facebook_comment')
    def test_reply_endpoint_survives_meta_api_exception(self, mock_meta_reply, client, app):
        """If Meta API call fails, endpoint logs warning but preserves state transition gracefully."""
        mock_meta_reply.side_effect = requests.exceptions.RequestException("Meta API unreachable")

        with app.app_context():
            item = InboxItem.create(USER_A_ID, 'fb', 'c_err_test', 'Great vibe', sentiment='positive')

        with auth_user_session(client, app, USER_A_ID, tier='pro'):
            resp = client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'Thank you!'})
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True
            
            with app.app_context():
                refreshed = InboxItem.get_by_id(item.id)
                assert refreshed.status == InboxItem.STATUS_APPROVED
                assert refreshed.final_reply == 'Thank you!'


# ===========================================================================
# 3. Database Integrity & State Transitions
# ===========================================================================

class TestDatabaseIntegrityAndStateTransitions:
    """Verify state transitions and database schema integrity."""

    def test_full_status_transition_lifecycle(self, app):
        """Verify item transitions from pending through all legal statuses."""
        with app.app_context():
            item = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='c_lifecycle',
                comment_text='Where are you located?',
                sentiment='question',
                ai_draft_reply='We are at 123 Main St.',
                status=InboxItem.STATUS_PENDING,
            )
            assert item.status == InboxItem.STATUS_PENDING
            assert item.replied_at is None
            assert item.hidden_at is None

            # 1. Skip item
            InboxItem.mark_skipped(item.id, USER_A_ID)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_SKIPPED

            # 2. Re-moderate: hide skipped item
            InboxItem.mark_hidden(item.id, USER_A_ID)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_HIDDEN
            assert item.hidden_at is not None

            # 3. Re-moderate: approve & reply to hidden item
            InboxItem.mark_replied(item.id, USER_A_ID, final_reply='123 Main St, open till 9!')
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_APPROVED
            assert item.final_reply == '123 Main St, open till 9!'
            assert item.replied_at is not None
            assert item.auto_replied is False

            # 4. Auto-replied status transition
            InboxItem.mark_replied(item.id, USER_A_ID, final_reply='Auto reply', auto_replied=True)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_AUTO_REPLIED
            assert item.auto_replied is True

    def test_extreme_and_adversarial_comment_inputs(self, app):
        """Test model and reply agent with extreme, unicode, XSS, and SQL injection inputs."""
        with app.app_context():
            # SQL injection payload as comment
            sqli_text = "'; DROP TABLE inbox_items; -- ' OR '1'='1"
            item_sqli = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='c_sqli',
                comment_text=sqli_text,
            )
            assert item_sqli.comment_text == sqli_text
            # Verify table still intact
            assert InboxItem.get_by_id(item_sqli.id) is not None

            # XSS script injection
            xss_text = "<script>alert('XSS')</script><img src=x onerror=alert(1)>"
            item_xss = InboxItem.create(
                user_id=USER_A_ID,
                platform='ig',
                platform_comment_id='c_xss',
                comment_text=xss_text,
            )
            assert item_xss.comment_text == xss_text

            # Emoji flood
            emoji_text = "🍔🔥🍕❤️💯🎉✨🚀" * 50
            item_emoji = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='c_emoji',
                comment_text=emoji_text,
            )
            assert item_emoji.comment_text == emoji_text

            # Very long string (10,000 chars)
            long_text = "Super awesome restaurant " * 400
            analysis = analyze_and_draft(long_text, tone='hype', business_name='Awesome Place')
            assert analysis['sentiment'] in SENTIMENTS
            assert len(analysis['ai_draft_reply']) > 0

    def test_filter_matrix_combinatorics(self, app):
        """Test combinations of status, sentiment, and platform filters."""
        with app.app_context():
            InboxItem.create(USER_A_ID, 'fb', 'f1', 'fb pos pending', sentiment='positive', status='pending')
            InboxItem.create(USER_A_ID, 'fb', 'f2', 'fb pos approved', sentiment='positive', status='approved')
            InboxItem.create(USER_A_ID, 'ig', 'f3', 'ig pos pending', sentiment='positive', status='pending')
            InboxItem.create(USER_A_ID, 'ig', 'f4', 'ig neg pending', sentiment='negative', status='pending')
            InboxItem.create(USER_A_ID, 'ig', 'f5', 'ig spam hidden', sentiment='spam', status='hidden')

            # Platform fb + status pending
            fb_pending = InboxItem.list_by_user(USER_A_ID, platform='fb', status='pending')
            assert len(fb_pending) == 1
            assert fb_pending[0].platform_comment_id == 'f1'

            # Sentiment positive + platform ig
            ig_pos = InboxItem.list_by_user(USER_A_ID, platform='ig', sentiment='positive')
            assert len(ig_pos) == 1
            assert ig_pos[0].platform_comment_id == 'f3'

            # Status replied (matches both approved and auto_replied)
            replied = InboxItem.list_by_user(USER_A_ID, status='replied')
            assert len(replied) == 1
            assert replied[0].platform_comment_id == 'f2'

            count_replied = InboxItem.count_by_user(USER_A_ID, status='replied')
            assert count_replied == 1
