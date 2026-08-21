"""
tests/test_inbox_stress.py
Adversarial Stress Testing and Empirical Validation for Milestone M3.

Harness includes:
1. Extreme & adversarial sentiment inputs (SQLi, XSS, Unicode, zero-width, emojis, massive strings, null handling).
2. Tone fallback matrix exhaustive permutations & fuzzing.
3. Poller deduplication under repeated and edge-case ingestion.
4. Cron authentication security matrix & header variations.
5. Plan gating exhaustive matrix (Free, Starter, Pro, Agency).
"""

import os
import re
from contextlib import contextmanager
import pytest
from unittest.mock import patch, MagicMock

from modules.database import get_db
from modules.models import InboxItem
from modules.meta_api import MetaAPI
from modules.reply_agent import classify_sentiment, analyze_and_draft, _get_fallback_reply, TONES, SENTIMENTS
from modules.comment_poller import poll_user_comments, poll_all_active_users
from tests.conftest import _make_mock_user


USER_A_ID = '00000000-0000-4000-8000-000000000001'
USER_B_ID = '00000000-0000-4000-8000-000000000002'


@contextmanager
def auth_user_stress(client, app, user_id=USER_A_ID, email='user@test.dev', tier='starter'):
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
def clean_inbox_items_stress(app):
    """Clean inbox_items table before and after each stress test."""
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
# 1. Adversarial Sentiment Classification & Tone Fallback Fuzzing
# ===========================================================================

class TestAdversarialSentimentAndDrafting:
    @pytest.mark.parametrize("empty_input", [
        "",
        "   ",
        "\t\t",
        "\n\r\n",
        None,
        " \u200b \u200c ",  # zero-width spaces
    ])
    def test_empty_and_whitespace_inputs_return_neutral(self, empty_input):
        sentiment = classify_sentiment(empty_input)
        assert sentiment == 'neutral'
        res = analyze_and_draft(empty_input, business_name="Taco Test")
        assert res['sentiment'] == 'neutral'
        assert len(res['ai_draft_reply']) > 0

    @pytest.mark.parametrize("sqli_input", [
        "' OR '1'='1' --",
        "'; DROP TABLE inbox_items; --",
        "' UNION SELECT username, password FROM users --",
        "1; WAITFOR DELAY '0:0:5'--",
        "\" OR \"\"=\"",
    ])
    def test_sql_injection_payloads_do_not_crash(self, sqli_input):
        sentiment = classify_sentiment(sqli_input)
        assert sentiment in SENTIMENTS
        res = analyze_and_draft(sqli_input, business_name="Taco Test")
        assert res['sentiment'] in SENTIMENTS
        assert isinstance(res['ai_draft_reply'], str)

    @pytest.mark.parametrize("xss_input", [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert('xss')>",
        "<svg/onload=alert('XSS')>",
        "javascript:alert(document.cookie)",
        "{{ 7 * 7 }}",
        "${7*7}",
        "<%= 7*7 %>",
    ])
    def test_xss_and_template_injections_handled_safely(self, xss_input):
        sentiment = classify_sentiment(xss_input)
        assert sentiment in SENTIMENTS
        res = analyze_and_draft(xss_input, business_name="Taco Test")
        assert res['sentiment'] in SENTIMENTS
        assert isinstance(res['ai_draft_reply'], str)

    @pytest.mark.parametrize("emoji_input, expected_sentiment", [
        ("🔥🔥🔥🔥", "positive"),
        ("😍😍😍", "positive"),
        ("👏🙌", "positive"),
        ("🤤👌✨", "positive"),
        ("🥰🤩🎉", "positive"),
        ("👍", "neutral"),
    ])
    def test_emoji_sentiment_handling(self, emoji_input, expected_sentiment):
        sentiment = classify_sentiment(emoji_input)
        assert sentiment == expected_sentiment

    @pytest.mark.parametrize("spam_input", [
        "Earn $5000 a day! https://bit.ly/quickcash",
        "Check my bio for crypto signals wa.me/1234567890",
        "DM me to buy followers now!",
        "Inbox me if you want a sugar daddy paying weekly",
        "Follow back to gain 10k free followers!",
        "Invest with our forex broker on telegram t.me/profit",
        "Visit www.scam-deal-now.xyz for free gifts",
    ])
    def test_spam_detection_and_empty_reply(self, spam_input):
        sentiment = classify_sentiment(spam_input)
        assert sentiment == 'spam'
        res = analyze_and_draft(spam_input, business_name="Taco Test")
        assert res['sentiment'] == 'spam'
        assert res['ai_draft_reply'] == ""

    @pytest.mark.parametrize("negative_input", [
        "Terrible food, rude waiter, cold soup, 1/10.",
        "Worst dining experience of my life. Never coming back.",
        "Disgusting and stale. Got food poisoning after eating here.",
        "Overpriced rip-off and slow service. Waited forever.",
        "0 stars if I could! Horrible staff and nasty tables.",
    ])
    def test_negative_review_detection(self, negative_input):
        sentiment = classify_sentiment(negative_input)
        assert sentiment == 'negative'
        res = analyze_and_draft(negative_input, business_name="Taco Test")
        assert res['sentiment'] == 'negative'
        reply = res['ai_draft_reply'].lower()
        assert any(k in reply for k in ['sorry', 'apologize', 'resolve', 'right', 'feedback', 'connect'])

    @pytest.mark.parametrize("question_input", [
        "What time do you guys open today?",
        "Are you open right now?",
        "Where is your parking located?",
        "Do you serve vegan and gluten-free tacos?",
        "How much does the lunch combo cost?",
        "Can we reserve a table for 6 people tonight?",
        "Is there outdoor seating available?",
    ])
    def test_question_detection(self, question_input):
        sentiment = classify_sentiment(question_input)
        assert sentiment == 'question'
        res = analyze_and_draft(question_input, business_name="Taco Test")
        assert res['sentiment'] == 'question'
        assert len(res['ai_draft_reply']) > 15

    def test_massive_string_input(self):
        massive_text = "Love the pizza! " * 1000  # ~16,000 characters
        sentiment = classify_sentiment(massive_text)
        assert sentiment == 'positive'
        res = analyze_and_draft(massive_text, business_name="Big Pizza")
        assert res['sentiment'] == 'positive'
        assert len(res['ai_draft_reply']) < 500  # Concise reply generated

    def test_exhaustive_tone_and_sentiment_fallback_matrix(self):
        for s in SENTIMENTS:
            for t in TONES:
                reply = _get_fallback_reply(s, tone=t, business_name="The Burger Joint", location="Austin")
                if s == 'spam':
                    assert reply == ""
                else:
                    assert isinstance(reply, str)
                    assert len(reply) > 5
                    assert "The Burger Joint" in reply or "We" in reply or "Thanks" in reply or "Thank you" in reply

    def test_invalid_tone_falls_back_to_friendly(self):
        for invalid_tone in ['angry', 'sarcastic', '123', None, '']:
            res = analyze_and_draft("Great tacos!", tone=invalid_tone, business_name="Taco Test")
            assert res['tone'] == 'friendly'
            assert len(res['ai_draft_reply']) > 0


# ===========================================================================
# 2. Poller Deduplication & Edge-Case Ingestion Stress
# ===========================================================================

class TestPollerDeduplicationStress:
    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    @patch.object(MetaAPI, 'get_facebook_comments')
    def test_repeated_ingestion_idempotence(self, mock_get_comments, mock_get_posts, mock_load_token, app):
        mock_load_token.return_value = {
            'access_token': 'test_token',
            'meta': {'page_id': 'fb_p_1', 'ig_id': ''}
        }
        mock_get_posts.return_value = {
            'data': [{'id': 'post_999', 'message': 'Grand opening specials!'}]
        }
        mock_get_comments.return_value = {
            'data': [
                {'id': 'c_stress_dup_1', 'message': 'Super excited to visit!', 'from': {'id': 'u1', 'name': 'Chris'}, 'created_time': '2026-08-19T14:00:00Z'},
                {'id': 'c_stress_dup_2', 'message': 'Where are you located?', 'from': {'id': 'u2', 'name': 'Pat'}, 'created_time': '2026-08-19T14:01:00Z'},
            ]
        }

        with app.app_context():
            # First poll: 2 new comments
            res1 = poll_user_comments(USER_A_ID)
            assert res1['success'] is True
            assert res1['new'] == 2
            assert InboxItem.count_by_user(USER_A_ID) == 2

            # Repeat poll 10 times: 0 new comments each time
            for i in range(10):
                res_repeat = poll_user_comments(USER_A_ID)
                assert res_repeat['success'] is True
                assert res_repeat['new'] == 0
                assert res_repeat['fetched'] == 2
                assert InboxItem.count_by_user(USER_A_ID) == 2

    def test_same_comment_id_across_different_platforms_coexist(self, app):
        with app.app_context():
            item_fb = InboxItem.create(
                user_id=USER_A_ID,
                platform='fb',
                platform_comment_id='shared_stress_id_777',
                comment_text='Facebook comment',
            )
            item_ig = InboxItem.create(
                user_id=USER_A_ID,
                platform='ig',
                platform_comment_id='shared_stress_id_777',
                comment_text='Instagram comment',
            )
            assert item_fb.id != item_ig.id
            assert InboxItem.count_by_user(USER_A_ID) == 2

    @patch('modules.comment_poller.load_token')
    @patch.object(MetaAPI, 'get_page_posts')
    @patch.object(MetaAPI, 'get_facebook_comments')
    def test_poller_filters_empty_or_whitespace_comments(self, mock_get_comments, mock_get_posts, mock_load_token, app):
        mock_load_token.return_value = {
            'access_token': 'test_token',
            'meta': {'page_id': 'fb_p_1', 'ig_id': ''}
        }
        mock_get_posts.return_value = {'data': [{'id': 'post_10', 'message': 'Hi'}]}
        mock_get_comments.return_value = {
            'data': [
                {'id': 'c_stress_empty_1', 'message': ''},
                {'id': 'c_stress_empty_2', 'message': '   \n  '},
                {'id': '', 'message': 'Valid text but empty ID'},
                {'id': 'c_stress_valid_3', 'message': 'Valid comment!'},
            ]
        }

        with app.app_context():
            res = poll_user_comments(USER_A_ID)
            assert res['success'] is True
            assert res['new'] == 1
            assert InboxItem.count_by_user(USER_A_ID) == 1
            item = InboxItem.list_by_user(USER_A_ID)[0]
            assert item.platform_comment_id == 'c_stress_valid_3'


# ===========================================================================
# 3. Cron Security & Header Matrix Stress Tests
# ===========================================================================

class TestCronSecurityMatrix:
    @pytest.mark.parametrize("invalid_header", [
        None,                                      # Missing Authorization header
        {},                                        # Empty dict
        {'Authorization': ''},                     # Empty string
        {'Authorization': 'Bearer'},               # Missing token
        {'Authorization': 'Bearer '},              # Whitespace token
        {'Authorization': 'bearer test-sec'},      # Lowercase 'bearer'
        {'Authorization': 'Token test-sec'},       # Token auth scheme
        {'Authorization': 'Basic dXNlcjpwYXNz'},   # Basic auth
        {'Authorization': 'Bearer test-sec-wrong'},# Invalid secret
        {'Authorization': 'Bearer test-sec '},     # Trailing space
        {'Authorization': 'Bearer ' + 'A' * 1000}, # Overflow token
    ])
    def test_cron_poll_comments_strictly_rejects_invalid_headers(self, client, invalid_header):
        secret = 'test-sec'
        with patch.dict(os.environ, {'CRON_SECRET': secret}):
            from blueprints import cron
            cron._CRON_SECRET = secret
            try:
                headers = invalid_header if isinstance(invalid_header, dict) else {}
                if invalid_header is None:
                    resp_get = client.get('/api/cron/poll_comments')
                    resp_post = client.post('/api/cron/poll_comments')
                else:
                    resp_get = client.get('/api/cron/poll_comments', headers=headers)
                    resp_post = client.post('/api/cron/poll_comments', headers=headers)

                assert resp_get.status_code == 401
                assert resp_get.get_json()['error'] == 'Unauthorized'
                assert resp_post.status_code == 401
                assert resp_post.get_json()['error'] == 'Unauthorized'
            finally:
                cron._CRON_SECRET = os.getenv('CRON_SECRET', '')

    def test_cron_fails_closed_when_secret_unset(self, client):
        with patch.dict(os.environ, {'CRON_SECRET': ''}):
            from blueprints import cron
            cron._CRON_SECRET = ''
            resp = client.get('/api/cron/poll_comments', headers={'Authorization': 'Bearer'})
            assert resp.status_code == 401

            resp2 = client.get('/api/cron/poll_comments', headers={'Authorization': 'Bearer test'})
            assert resp2.status_code == 401


# ===========================================================================
# 4. Plan Gating Full Matrix Stress Tests
# ===========================================================================

class TestPlanGatingMatrixStress:
    def test_free_tier_blocked_from_all_inbox_routes(self, client, app):
        with auth_user_stress(client, app, USER_A_ID, tier='free'):
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_stress_free_1', 'Hello', sentiment='neutral')

            # Page redirects
            assert client.get('/inbox').status_code == 302

            # All APIs return 403 PLAN_REQUIRED
            assert client.get('/api/inbox/items').status_code == 403
            assert client.get('/api/inbox/stats').status_code == 403
            assert client.post('/api/inbox/poll_now').status_code == 403
            assert client.post(f'/api/inbox/{item.id}/skip').status_code == 403
            assert client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'a'}).status_code == 403
            assert client.post(f'/api/inbox/{item.id}/regenerate').status_code == 403
            assert client.post(f'/api/inbox/{item.id}/hide').status_code == 403

    def test_starter_tier_permissions(self, client, app):
        with auth_user_stress(client, app, USER_A_ID, tier='starter'):
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_stress_starter_1', 'Hello', sentiment='neutral')

            # Allowed (Starter+)
            assert client.get('/inbox').status_code == 200
            assert client.get('/api/inbox/items').status_code == 200
            assert client.get('/api/inbox/stats').status_code == 200
            with patch('blueprints.inbox.poll_user_comments', return_value={'success': True, 'new': 0}):
                assert client.post('/api/inbox/poll_now').status_code == 200
            assert client.post(f'/api/inbox/{item.id}/skip').status_code == 200

            # Forbidden (Requires Pro)
            assert client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'a'}).status_code == 403
            assert client.post(f'/api/inbox/{item.id}/regenerate').status_code == 403
            assert client.post(f'/api/inbox/{item.id}/hide').status_code == 403

    def test_pro_tier_permissions(self, client, app):
        with auth_user_stress(client, app, USER_A_ID, tier='pro'):
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_stress_pro_1', 'Hello', sentiment='neutral')

            # All Allowed (Pro+)
            assert client.get('/inbox').status_code == 200
            assert client.get('/api/inbox/items').status_code == 200
            assert client.get('/api/inbox/stats').status_code == 200
            with patch('blueprints.inbox.poll_user_comments', return_value={'success': True, 'new': 0}):
                assert client.post('/api/inbox/poll_now').status_code == 200
            assert client.post(f'/api/inbox/{item.id}/skip').status_code == 200

            # Pro actions
            assert client.post(f'/api/inbox/{item.id}/regenerate').status_code == 200
            with patch.object(MetaAPI, 'hide_facebook_comment', return_value={'success': True}):
                assert client.post(f'/api/inbox/{item.id}/hide').status_code == 200
            with patch.object(MetaAPI, 'reply_to_facebook_comment', return_value={'id': 'rep_1'}):
                assert client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'Thanks!'}).status_code == 200

    def test_agency_tier_permissions(self, client, app):
        with auth_user_stress(client, app, USER_A_ID, tier='agency'):
            with app.app_context():
                item = InboxItem.create(USER_A_ID, 'fb', 'c_stress_agency_1', 'Hello', sentiment='neutral')

            # Agency has all Pro privileges
            assert client.get('/inbox').status_code == 200
            assert client.get('/api/inbox/items').status_code == 200
            assert client.post(f'/api/inbox/{item.id}/regenerate').status_code == 200
            with patch.object(MetaAPI, 'reply_to_facebook_comment', return_value={'id': 'rep_1'}):
                assert client.post(f'/api/inbox/{item.id}/reply', json={'reply_text': 'Thanks!'}).status_code == 200
