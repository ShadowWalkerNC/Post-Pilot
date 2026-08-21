"""
tests/test_inbox.py
Comprehensive test suite for Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller).

Tests:
1. InboxItem model queries, mutations, serialization & deduplication.
2. ReplyAgent sentiment analysis (5 classes) and tone fallback matrix (5 tones).
3. MetaAPI comment fetching, replying, and hiding methods.
4. Comment poller ingestion, deduplication, and multi-user execution.
5. Plan tier guards (Free blocked, Starter read/poll, Pro reply/regenerate/hide).
6. Inbox REST APIs (list, stats, poll_now, reply, regenerate, hide, skip).
7. Cross-user isolation and security.
8. Cron comment poller HMAC CRON_SECRET protection.
"""

import os
import json
import time
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
import pytest

from modules.database import get_db
from modules.models import InboxItem
from modules.meta_api import MetaAPI
from modules.reply_agent import classify_sentiment, analyze_and_draft, TONES, SENTIMENTS
from modules.comment_poller import poll_user_comments, poll_all_active_users
from modules.auth_manager import save_token
from tests.conftest import _make_mock_user


USER_A_ID = '00000000-0000-4000-8000-000000000001' # starter / pro user in fixtures
USER_B_ID = '00000000-0000-4000-8000-000000000002'


@contextmanager
def auth_user(client, app, user_id=USER_A_ID, email='user@test.dev', tier='starter'):
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
def clean_inbox_items(app):
    """Clean inbox_items table before and after each test."""
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
# 1. Model Tests
# ===========================================================================

class TestInboxItemModel:
    def test_create_and_get_by_id(self, app):
        with app.app_context():
            item = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='fb_c_101',
                comment_text='Best burger in town! 🔥',
                platform_post_id='post_123',
                author_name='Alice Smith',
                sentiment='positive',
                ai_draft_reply='Thank you so much Alice!',
            )
            assert item is not None
            assert item.id is not None
            assert item.user_id == USER_A_ID
            assert item.sentiment == 'positive'
            assert item.status == InboxItem.STATUS_PENDING

            fetched = InboxItem.get_by_id(item.id)
            assert fetched is not None
            assert fetched.platform_comment_id == 'fb_c_101'
            assert fetched.comment_text == 'Best burger in town! 🔥'

            # Fetch scoped by user
            scoped = InboxItem.get_by_id(item.id, user_id=USER_A_ID)
            assert scoped is not None
            assert InboxItem.get_by_id(item.id, user_id=USER_B_ID) is None

    def test_deduplication_on_create(self, app):
        with app.app_context():
            item1 = InboxItem.create(
                user_id=USER_A_ID,
                platform='ig',
                platform_comment_id='ig_c_202',
                comment_text='Are you open on Sundays?',
                sentiment='question',
            )
            # Re-creating same platform + comment_id returns existing item
            item2 = InboxItem.create(
                user_id=USER_A_ID,
                platform='ig',
                platform_comment_id='ig_c_202',
                comment_text='Different text duplicate attempt',
            )
            assert item1.id == item2.id
            assert item2.comment_text == 'Are you open on Sundays?'

    def test_list_and_count_with_filters(self, app):
        with app.app_context():
            # Seed 3 items for User A, 1 for User B
            InboxItem.create(USER_A_ID, 'fb', 'c1', 'Positive 1', sentiment='positive', status='pending')
            InboxItem.create(USER_A_ID, 'fb', 'c2', 'Question 1', sentiment='question', status='pending')
            InboxItem.create(USER_A_ID, 'ig', 'c3', 'Spam 1', sentiment='spam', status='hidden')
            InboxItem.create(USER_B_ID, 'fb', 'c4', 'User B comment', sentiment='neutral', status='pending')

            assert InboxItem.count_by_user(USER_A_ID) == 3
            assert InboxItem.count_by_user(USER_B_ID) == 1

            # Filter by status
            pending = InboxItem.list_by_user(USER_A_ID, status='pending')
            assert len(pending) == 2
            assert InboxItem.count_by_user(USER_A_ID, status='pending') == 2

            # Filter by sentiment
            pos_items = InboxItem.list_by_user(USER_A_ID, sentiment='positive')
            assert len(pos_items) == 1
            assert pos_items[0].comment_text == 'Positive 1'

            # Filter by platform
            ig_items = InboxItem.list_by_user(USER_A_ID, platform='ig')
            assert len(ig_items) == 1
            assert ig_items[0].platform == 'ig'

    def test_mutations(self, app):
        with app.app_context():
            item = InboxItem.create(USER_A_ID, 'fb', 'c_mut', 'Great food!', sentiment='positive')
            
            # Update draft
            InboxItem.update_draft(item.id, USER_A_ID, 'Updated draft reply')
            item = InboxItem.get_by_id(item.id)
            assert item.ai_draft_reply == 'Updated draft reply'

            # Mark replied
            InboxItem.mark_replied(item.id, USER_A_ID, final_reply='Sent reply message', auto_replied=False)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_APPROVED
            assert item.final_reply == 'Sent reply message'
            assert item.replied_at is not None

            # Mark hidden
            InboxItem.mark_hidden(item.id, USER_A_ID)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_HIDDEN
            assert item.hidden_at is not None

            # Mark skipped
            InboxItem.mark_skipped(item.id, USER_A_ID)
            item = InboxItem.get_by_id(item.id)
            assert item.status == InboxItem.STATUS_SKIPPED

    def test_to_dict_serialization(self, app):
        with app.app_context():
            item = InboxItem.create(USER_A_ID, 'fb', 'c_dict', 'Delicious!', sentiment='positive')
            d = item.to_dict()
            assert isinstance(d, dict)
            assert d['id'] == item.id
            assert d['user_id'] == USER_A_ID
            assert d['platform'] == 'fb'
            assert d['platform_comment_id'] == 'c_dict'
            assert d['sentiment'] == 'positive'


# ===========================================================================
# 2. Reply Agent Tests
# ===========================================================================

class TestReplyAgent:
    def test_sentiment_classification_5_classes(self):
        # Spam
        assert classify_sentiment("Earn $5000 a day! Check bio link: https://bit.ly/crypto-money") == 'spam'
        assert classify_sentiment("DM me to buy followers now!") == 'spam'

        # Negative
        assert classify_sentiment("The food was cold and the service was terrible. Never coming back.") == 'negative'
        assert classify_sentiment("Disgusting experience and rude waiter, 1/10.") == 'negative'

        # Question
        assert classify_sentiment("What time are you open today?") == 'question'
        assert classify_sentiment("Do you guys offer gluten-free vegan options?") == 'question'
        assert classify_sentiment("Where is the parking located?") == 'question'

        # Positive
        assert classify_sentiment("The tacos were absolutely amazing and delicious! 10/10 🔥") == 'positive'
        assert classify_sentiment("Best coffee in the city! Love this place ❤️") == 'positive'

        # Neutral
        assert classify_sentiment("Saw you guys on the corner.") == 'neutral'

    def test_tone_fallback_matrix(self):
        for tone in TONES:
            res_pos = analyze_and_draft("Amazing food!", tone=tone, business_name="Taco Haven")
            assert res_pos['sentiment'] == 'positive'
            assert "Taco Haven" in res_pos['ai_draft_reply'] or "Thank you" in res_pos['ai_draft_reply'] or "Thanks" in res_pos['ai_draft_reply']
            assert res_pos['tone'] == tone

            res_q = analyze_and_draft("Are you open at 5pm?", tone=tone, business_name="Taco Haven")
            assert res_q['sentiment'] == 'question'
            assert len(res_q['ai_draft_reply']) > 10

            res_neg = analyze_and_draft("Terrible service yesterday", tone=tone, business_name="Taco Haven")
            assert res_neg['sentiment'] == 'negative'
            assert "sorry" in res_neg['ai_draft_reply'].lower() or "feedback" in res_neg['ai_draft_reply'].lower() or "apologize" in res_neg['ai_draft_reply'].lower()

    def test_spam_reply_is_empty(self):
        res_spam = analyze_and_draft("DM me for crypto signals https://t.me/scam")
        assert res_spam['sentiment'] == 'spam'
        assert res_spam['ai_draft_reply'] == ""


# ===========================================================================
# 3. Meta API Client Comment Methods Tests
# ===========================================================================

class TestMetaAPIComments:
    @patch('requests.get')
    def test_get_facebook_comments(self, mock_get):
        mock_get.return_value.json.return_value = {
            'data': [
                {'id': 'c_fb_1', 'message': 'Loved the pizza!', 'from': {'id': 'u1', 'name': 'John Doe'}, 'created_time': '2026-08-19T10:00:00Z'}
            ]
        }
        api = MetaAPI(access_token='test_token', page_id='page_123')
        res = api.get_facebook_comments('post_123', limit=10)
        assert 'data' in res
        assert len(res['data']) == 1
        assert res['data'][0]['id'] == 'c_fb_1'

    @patch('requests.get')
    def test_get_instagram_comments(self, mock_get):
        mock_get.return_value.json.return_value = {
            'data': [
                {'id': 'c_ig_1', 'text': 'Super yummy!', 'username': 'foodie_gal', 'timestamp': '2026-08-19T11:00:00Z'}
            ]
        }
        api = MetaAPI(access_token='test_token', page_id='page_123', instagram_id='ig_999')
        res = api.get_instagram_comments('ig_999', limit=10)
        assert 'data' in res
        assert res['data'][0]['username'] == 'foodie_gal'

    @patch('requests.post')
    def test_reply_to_comment_fb_and_ig(self, mock_post):
        mock_post.return_value.json.return_value = {'id': 'reply_123'}
        api = MetaAPI(access_token='test_token', page_id='page_123', instagram_id='ig_999')
        
        fb_res = api.reply_to_comment('fb', 'c_fb_1', 'Thanks for coming!')
        assert fb_res.get('id') == 'reply_123'

        ig_res = api.reply_to_comment('ig', 'c_ig_1', 'Glad you loved it!')
        assert ig_res.get('id') == 'reply_123'

    @patch('requests.post')
    def test_hide_comment_fb_and_ig(self, mock_post):
        mock_post.return_value.json.return_value = {'success': True}
        api = MetaAPI(access_token='test_token', page_id='page_123', instagram_id='ig_999')
        
        fb_res = api.hide_comment('fb', 'c_fb_1', hide=True)
        assert fb_res.get('success') is True

        ig_res = api.hide_comment('ig', 'c_ig_1', hide=True)
        assert ig_res.get('success') is True


# ===========================================================================
# 4. Comment Poller Tests
# ===========================================================================

class TestCommentPoller:
    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    @patch.object(MetaAPI, 'get_facebook_comments')
    def test_poll_user_comments_ingestion(self, mock_get_comments, mock_get_posts, mock_load_token, app):
        mock_load_token.return_value = {
            'access_token': 'mock_token',
            'meta': {'page_id': 'fb_page_10', 'ig_id': ''}
        }
        mock_get_posts.return_value = {
            'data': [{'id': 'post_100', 'message': 'Check out our new Taco Tuesday menu!'}]
        }
        mock_get_comments.return_value = {
            'data': [
                {'id': 'c_poller_1', 'message': 'Is this available all day?', 'from': {'id': 'u1', 'name': 'Bob'}, 'created_time': '2026-08-19T12:00:00Z'},
                {'id': 'c_poller_2', 'message': 'Best tacos ever! 🔥', 'from': {'id': 'u2', 'name': 'Sara'}, 'created_time': '2026-08-19T12:05:00Z'},
            ]
        }

        with app.app_context():
            result = poll_user_comments(USER_A_ID)
            assert result['success'] is True
            assert result['new'] == 2
            assert result['fetched'] == 2

            # Verify in DB
            items = InboxItem.list_by_user(USER_A_ID)
            assert len(items) == 2

            # Deduplication on second poll
            result2 = poll_user_comments(USER_A_ID)
            assert result2['new'] == 0
            assert InboxItem.count_by_user(USER_A_ID) == 2

    @patch('modules.comment_poller.get_connection')
    @patch('modules.comment_poller.poll_user_comments')
    def test_poll_all_active_users(self, mock_poll_user, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [{'user_id': USER_A_ID}, {'user_id': USER_B_ID}]
        mock_conn.cursor.return_value = mock_cur
        mock_get_conn.return_value = mock_conn

        mock_poll_user.side_effect = [
            {'success': True, 'new': 3, 'errors': []},
            {'success': True, 'new': 2, 'errors': []},
        ]

        summary = poll_all_active_users()
        assert summary['success'] is True
        assert summary['users_polled'] == 2
        assert summary['total_new_comments'] == 5


# ===========================================================================
# 5. Plan Guards & Access Control Tests
# ===========================================================================

class TestPlanGuardsInbox:
    def test_free_user_blocked_from_inbox(self, client, app):
        with auth_user(client, app, USER_A_ID, tier='free'):
            # Page redirects to billing
            resp = client.get('/inbox')
            assert resp.status_code == 302
            assert '/billing' in resp.headers.get('Location', '')

            # API returns 403 JSON
            resp_api = client.get('/api/inbox/items')
            assert resp_api.status_code == 403
            data = resp_api.get_json()
            assert data['error']['code'] == 'PLAN_REQUIRED'

    def test_starter_user_can_view_and_poll_but_cannot_reply(self, client, app):
        with auth_user(client, app, USER_A_ID, tier='starter'):
            # Seed item
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_start', 'Nice post!', sentiment='positive')

            # Can view /inbox page
            resp_page = client.get('/inbox')
            assert resp_page.status_code == 200

            # Can list API items
            resp_list = client.get('/api/inbox/items')
            assert resp_list.status_code == 200
            assert len(resp_list.get_json()['items']) == 1

            # Blocked from replying (Requires Pro)
            resp_reply = client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'Thanks!'})
            assert resp_reply.status_code == 403
            assert resp_reply.get_json()['error']['code'] == 'PLAN_REQUIRED'

            # Blocked from regenerating draft (Requires Pro)
            resp_regen = client.post(f'/api/inbox/{item.id}/regenerate', json={'tone': 'hype'})
            assert resp_regen.status_code == 403

            # Blocked from hiding (Requires Pro)
            resp_hide = client.post(f'/api/inbox/{item.id}/hide')
            assert resp_hide.status_code == 403

            # Starter CAN skip / archive
            resp_skip = client.post(f'/api/inbox/{item.id}/skip')
            assert resp_skip.status_code == 200

    def test_pro_user_can_reply_regenerate_hide(self, client, app):
        with auth_user(client, app, USER_A_ID, tier='pro'):
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_pro', 'Love this place!', sentiment='positive')

            # Regenerate AI draft
            resp_regen = client.post(f'/api/inbox/{item.id}/regenerate', json={'tone': 'hype'})
            assert resp_regen.status_code == 200
            assert resp_regen.get_json()['success'] is True
            assert len(resp_regen.get_json()['ai_draft_reply']) > 5

            # Reply
            with patch.object(MetaAPI, 'reply_to_facebook_comment', return_value={'id': 'rep_1'}):
                resp_reply = client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'Thank you so much! 🙌'})
                assert resp_reply.status_code == 200
                data = resp_reply.get_json()
                assert data['success'] is True
                assert data['item']['status'] == InboxItem.STATUS_APPROVED

            # Hide
            with patch.object(MetaAPI, 'hide_facebook_comment', return_value={'success': True}):
                resp_hide = client.post(f'/api/inbox/{item.id}/hide')
                assert resp_hide.status_code == 200
                assert resp_hide.get_json()['item']['status'] == InboxItem.STATUS_HIDDEN


# ===========================================================================
# 6. REST API & Stats Tests
# ===========================================================================

class TestInboxAPIs:
    def test_inbox_stats_endpoint(self, client, app):
        with auth_user(client, app, USER_A_ID, tier='starter'):
            with app.app_context():
                InboxItem.create(USER_A_ID, 'fb', 'c1', 'Tacos are life 🔥', sentiment='positive', status='pending')
                InboxItem.create(USER_A_ID, 'fb', 'c2', 'When are you open?', sentiment='question', status='pending')
                InboxItem.create(USER_A_ID, 'ig', 'c3', 'Buy crypto bit.ly', sentiment='spam', status='hidden')

            resp = client.get('/api/inbox/stats')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            stats = data['stats']
            assert stats['pending'] == 2
            assert stats['hidden'] == 1
            assert stats['sentiment']['positive'] == 1
            assert stats['sentiment']['question'] == 1
            assert stats['sentiment']['spam'] == 1

    def test_on_demand_poll_now(self, client, app):
        with auth_user(client, app, USER_A_ID, tier='starter'):
            with patch('blueprints.inbox.poll_user_comments', return_value={'success': True, 'new': 2}) as mock_poll:
                resp = client.post('/api/inbox/poll_now')
                assert resp.status_code == 200
                assert resp.get_json()['success'] is True
                assert resp.get_json()['result']['new'] == 2
                mock_poll.assert_called_once_with(USER_A_ID)


# ===========================================================================
# 7. Cross-User Data Isolation Tests
# ===========================================================================

class TestCrossUserIsolation:
    def test_user_cannot_view_or_moderate_other_user_items(self, client, app):
        with app.app_context():
            item_a = InboxItem.create(USER_A_ID, 'fb', 'ca', 'User A item', sentiment='positive')
            item_b = InboxItem.create(USER_B_ID, 'fb', 'cb', 'User B item', sentiment='positive')

        # Logged in as User A
        with auth_user(client, app, USER_A_ID, tier='pro'):
            # User A cannot reply to User B item -> 404
            resp = client.post(f'/api/inbox/{item_b.id}/reply', json={'reply_text': 'Hacked reply'})
            assert resp.status_code == 404

            # User A cannot hide User B item -> 404
            resp_hide = client.post(f'/api/inbox/{item_b.id}/hide')
            assert resp_hide.status_code == 404

            # User A cannot regenerate User B item -> 404
            resp_regen = client.post(f'/api/inbox/{item_b.id}/regenerate')
            assert resp_regen.status_code == 404

            # User A list only contains item_a
            resp_list = client.get('/api/inbox/items')
            items = resp_list.get_json()['items']
            assert len(items) == 1
            assert items[0]['id'] == item_a.id


# ===========================================================================
# 8. Cron Comment Poller Security Tests
# ===========================================================================

class TestCronCommentPoller:
    def test_cron_rejected_without_secret(self, client):
        resp = client.get('/api/cron/poll_comments')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'Unauthorized'

        resp_post = client.post('/api/cron/poll_comments')
        assert resp_post.status_code == 401

    def test_cron_rejected_with_invalid_secret(self, client):
        with patch.dict(os.environ, {'CRON_SECRET': 'real-secret-123'}):
            from blueprints import cron
            cron._CRON_SECRET = 'real-secret-123'
            try:
                resp = client.get(
                    '/api/cron/poll_comments',
                    headers={'Authorization': 'Bearer wrong-secret'}
                )
                assert resp.status_code == 401
            finally:
                cron._CRON_SECRET = os.getenv('CRON_SECRET', '')

    def test_cron_accepted_with_valid_hmac_secret(self, client):
        secret = 'secure-cron-secret-xyz'
        with patch.dict(os.environ, {'CRON_SECRET': secret}):
            from blueprints import cron
            cron._CRON_SECRET = secret
            try:
                with patch('modules.comment_poller.poll_all_active_users', return_value={'success': True, 'total_new_comments': 4}) as mock_poll:
                    resp = client.get(
                        '/api/cron/poll_comments',
                        headers={'Authorization': f'Bearer {secret}'}
                    )
                    assert resp.status_code == 200
                    assert resp.get_json()['success'] is True
                    assert resp.get_json()['summary']['total_new_comments'] == 4
                    mock_poll.assert_called_once()
            finally:
                cron._CRON_SECRET = os.getenv('CRON_SECRET', '')
