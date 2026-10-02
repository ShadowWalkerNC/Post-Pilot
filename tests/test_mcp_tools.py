"""
tests/test_mcp_tools.py — tests for mcp/tools/* product tools.

Tools delegate to existing services; external HTTP (Meta/OpenAI) is mocked.
DB-backed reads use the session `app` fixture (SQLite test DB).
"""

import json

import pytest

import modules.mcp_bootstrap
modules.mcp_bootstrap.ensure_local_mcp_tools()

from mcp.tools import TOOL_NAMES, TOOL_SPECS, get_tool_spec
from mcp.tools.business import (
    business_get, business_update, menu_get, menu_list, menu_item_get,
)
from mcp.tools.specials import specials_list, specials_get
from mcp.tools.events import events_list, events_get
from mcp.tools.hours import hours_get
from mcp.tools.content import (
    _first_platform, content_generate, content_schedule,
    content_adapt, content_preview,
)
from mcp.tools.publish import post_publish, post_cancel, post_status
from mcp.tools.analytics import (
    analytics_get, analytics_top_posts, analytics_performance_summary,
)
from mcp.tools.inbox import (
    inbox_reply, inbox_list, inbox_approve_reply, inbox_skip,
)
from mcp.tools.media import media_list, media_get
from mcp.tools.brand import brand_get, brand_validate
from mcp.tools.automation import automation_run, automation_status
from mcp.tools.provider import provider_list, provider_route, provider_health

TEST_UID = '00000000-0000-4000-8000-000000000001'

EXPECTED_TOOLS = {
    'business.get', 'business.update',
    'menu.get', 'menu.list', 'menu.item_get',
    'specials.list', 'specials.get',
    'events.list', 'events.get',
    'hours.get',
    'content.generate', 'content.adapt', 'content.schedule', 'content.preview',
    'post.publish', 'post.cancel', 'post.status',
    'analytics.get', 'analytics.top_posts', 'analytics.performance_summary',
    'inbox.list', 'inbox.reply', 'inbox.approve_reply', 'inbox.skip',
    'media.list', 'media.get',
    'brand.get', 'brand.validate',
    'automation.run', 'automation.status',
    'provider.list', 'provider.route', 'provider.health',
}


# ---------------------------------------------------------------------------
# Registry / specs
# ---------------------------------------------------------------------------

def test_registry_contains_all_tools():
    assert EXPECTED_TOOLS == set(TOOL_NAMES)
    assert len(TOOL_SPECS) == 33


def test_every_spec_has_permission_and_auth_notes():
    for spec in TOOL_SPECS:
        assert spec['permission'] in {'read', 'write', 'publish'}, spec['name']
        assert spec['auth'], spec['name']
        assert 'secrets' in spec, spec['name']
        assert spec['description'], spec['name']


def test_get_tool_spec_unknown_raises():
    with pytest.raises(KeyError):
        get_tool_spec('nope.nope')


def test_publish_and_schedule_specs_call_out_permissions():
    assert get_tool_spec('post.publish')['permission'] == 'publish'
    assert 'publish' in get_tool_spec('post.publish')['auth'].lower()
    assert get_tool_spec('inbox.reply')['permission'] == 'write'
    assert 'draft' in get_tool_spec('inbox.reply')['description'].lower()


# ---------------------------------------------------------------------------
# business.get / menu.get
# ---------------------------------------------------------------------------

def test_business_get_returns_profile(app):
    with app.app_context():
        from modules.user_manager import UserManager
        UserManager.save_business_profile(TEST_UID, {'name': 'MCP Diner', 'location': 'Raleigh'})
        profile = business_get(TEST_UID)
    assert profile['name'] == 'MCP Diner'


def test_business_get_requires_user_id():
    with pytest.raises(ValueError):
        business_get('')


def test_menu_get_empty_when_no_website_row(app):
    with app.app_context():
        assert menu_get('uid-with-no-website-row') == {'items': []}


def test_menu_get_parses_section_data(app):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO websites (user_id, config, published, updated_at) "
            "VALUES (?, ?, 0, '')",
            ('menu-user', json.dumps({'x': 1})),
        )
        # section_data column may not exist in older schemas; add if missing
        cols = [r[1] for r in db.execute('PRAGMA table_info(websites)').fetchall()]
        if 'section_data' not in cols:
            db.execute('ALTER TABLE websites ADD COLUMN section_data TEXT')
        db.execute(
            'UPDATE websites SET section_data = ? WHERE user_id = ?',
            (json.dumps({'menu': {'items': [{'name': 'Burger', 'price': '$9'}]}}), 'menu-user'),
        )
        db.commit()
        assert menu_get('menu-user') == {'items': [{'name': 'Burger', 'price': '$9'}]}


# ---------------------------------------------------------------------------
# specials.list / events.list
# ---------------------------------------------------------------------------

def _seed_special(app):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            'INSERT INTO specials (user_id, item_name, post_date, post_time, status) '
            'VALUES (?, ?, ?, ?, ?)',
            (TEST_UID, 'MCP Taco', '2026-10-03', '12:00', 'pending'),
        )
        db.commit()


def _seed_event(app):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            'INSERT INTO events (user_id, title, event_date, post_date, post_time, status) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (TEST_UID, 'MCP Night', '2026-10-10', '2026-10-03', '12:00', 'pending'),
        )
        db.commit()


def test_specials_list_returns_seeded_row(app):
    _seed_special(app)
    rows = specials_list(TEST_UID)
    assert any(r['item_name'] == 'MCP Taco' for r in rows)


def test_specials_list_status_filter_and_validation(app):
    _seed_special(app)
    assert all(r['status'] == 'pending' for r in specials_list(TEST_UID, status='pending'))
    assert specials_list(TEST_UID, status='posted') == []
    with pytest.raises(ValueError):
        specials_list(TEST_UID, status='bogus')
    with pytest.raises(ValueError):
        specials_list('')


def test_events_list_returns_seeded_row(app):
    _seed_event(app)
    rows = events_list(TEST_UID)
    assert any(r['title'] == 'MCP Night' for r in rows)


def test_events_list_status_validation():
    with pytest.raises(ValueError):
        events_list(TEST_UID, status='bogus')


# ---------------------------------------------------------------------------
# content.generate / content.schedule
# ---------------------------------------------------------------------------

def test_content_generate_uses_template_fallback(app, monkeypatch):
    monkeypatch.setattr('modules.ai_generator._generate_openai', lambda *a, **k: None)
    monkeypatch.setattr(
        'modules.platform_adapter.PlatformAdapter.adapt_all',
        lambda self, master, platforms, tone='', business=None: {p: f'{master} [{p}]' for p in platforms},
    )
    with app.app_context():
        out = content_generate(TEST_UID, content_type='daily_special', tone='hype',
                               platforms=['fb', 'ig'])
    assert 'master' in out and 'adapted' in out
    assert set(out['adapted']) == {'fb', 'ig'}
    assert all(out['adapted'].values())


def test_content_generate_requires_user_id():
    with pytest.raises(ValueError):
        content_generate('')


def test_first_platform_mapping():
    assert _first_platform(None) == 'instagram'
    assert _first_platform(['fb']) == 'facebook'
    assert _first_platform({'ig': True, 'fb': False}) == 'instagram'
    assert _first_platform(['tt']) == 'instagram'


def test_content_schedule_no_token_returns_error(app):
    with app.app_context():
        out = content_schedule('uid-no-tokens', 'Hi', '2026-10-04T12:00:00')
    assert out['success'] is False
    assert 'not connected' in out['error']


def test_content_schedule_validates_inputs():
    with pytest.raises(ValueError):
        content_schedule('', 'Hi', '2026-10-04T12:00:00')
    with pytest.raises(ValueError):
        content_schedule(TEST_UID, '', '2026-10-04T12:00:00')


def test_content_schedule_delegates_to_scheduler(app, monkeypatch):
    import mcp.tools.publish as publish_mod
    monkeypatch.setattr(
        publish_mod, '_load_decrypted_tokens',
        lambda uid: {'facebook_token': 'tok', 'facebook_page_id': 'pg', 'instagram_id': 'ig'},
    )
    captured = {}
    monkeypatch.setattr(
        'modules.scheduler_worker.PostScheduler.schedule',
        lambda self, data: captured.update(data) or {'success': True, 'scheduled_for': data['publish_time']},
    )
    with app.app_context():
        out = content_schedule(TEST_UID, 'Hello FB', '2026-10-04T12:00:00', platforms=['fb'])
    assert out['success'] is True
    assert captured['platform'] == 'facebook'
    assert captured['caption'] == 'Hello FB'
    assert captured['access_token'] == 'tok'


# ---------------------------------------------------------------------------
# post.publish / analytics.get
# ---------------------------------------------------------------------------

def test_post_publish_requires_caption_or_captions():
    with pytest.raises(ValueError):
        post_publish(TEST_UID)


def test_post_publish_delegates_to_publisher(app, monkeypatch):
    import mcp.tools.publish as publish_mod
    monkeypatch.setattr(publish_mod, '_load_decrypted_tokens', lambda uid: {'facebook_token': 't'})
    captured = {}
    monkeypatch.setattr(
        'modules.publisher.UniversalPublisher.push_all',
        lambda self, **kw: captured.update(kw) or {'fb': {'success': True}},
    )
    with app.app_context():
        out = post_publish(TEST_UID, caption='Launch!', platforms=['fb'])
    assert out == {'fb': {'success': True}}
    assert captured['caption'] == 'Launch!'


def test_analytics_get_unconnected_returns_error(app):
    with app.app_context():
        out = analytics_get('uid-no-tokens', days=7)
    assert out['success'] is False


def test_analytics_get_delegates_to_analytics_client(app, monkeypatch):
    import mcp.tools.publish as publish_mod
    monkeypatch.setattr(
        publish_mod, '_load_decrypted_tokens',
        lambda uid: {'facebook_token': 'tok', 'facebook_page_id': 'pg'},
    )
    monkeypatch.setattr(
        'modules.analytics_client.Analytics.get_combined_summary',
        lambda self, days=30: {'success': True, 'kpis': {'posts': 3}, 'days': days},
    )
    with app.app_context():
        out = analytics_get(TEST_UID, days=7)
    assert out['success'] is True and out['days'] == 7


# ---------------------------------------------------------------------------
# inbox.reply
# ---------------------------------------------------------------------------

def test_inbox_reply_drafts_and_marks_not_posted():
    out = inbox_reply('I love this place!', tone='friendly')
    assert out['sentiment'] == 'positive'
    assert out['ai_draft_reply']
    assert out['posted'] is False


def test_inbox_reply_spam_yields_empty_draft():
    out = inbox_reply('Buy followers now at bit.ly/xyz crypto earn $500')
    assert out['sentiment'] == 'spam'
    assert out['ai_draft_reply'] == ''


def test_inbox_reply_requires_comment():
    with pytest.raises(ValueError):
        inbox_reply('   ')


def test_inbox_reply_uses_business_context(app):
    with app.app_context():
        from modules.user_manager import UserManager
        UserManager.save_business_profile(TEST_UID, {'name': 'MCP Diner'})
        out = inbox_reply('Great food!', user_id=TEST_UID)
    assert 'MCP Diner' in out['ai_draft_reply']


# ---------------------------------------------------------------------------
# business.update / menu.list / menu.item_get
# ---------------------------------------------------------------------------

def test_business_update_merges_and_returns_profile(app):
    with app.app_context():
        from modules.user_manager import UserManager
        UserManager.save_business_profile(TEST_UID, {'name': 'Old Name', 'location': 'Raleigh'})
        out = business_update(TEST_UID, {'name': 'New Name'})
    assert out['success'] is True
    assert out['profile']['name'] == 'New Name'
    assert out['profile']['location'] == 'Raleigh'  # unspecified fields preserved


def test_business_update_validates_inputs(app):
    with pytest.raises(ValueError):
        business_update('', {'name': 'x'})
    with pytest.raises(ValueError):
        business_update(TEST_UID, {})
    with pytest.raises(ValueError, match='unknown profile fields'):
        business_update(TEST_UID, {'nope': 'x'})


def _seed_menu(app, uid, items):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO websites (user_id, config, published, updated_at) "
            "VALUES (?, ?, 0, '')",
            (uid, json.dumps({})),
        )
        cols = [r[1] for r in db.execute('PRAGMA table_info(websites)').fetchall()]
        if 'section_data' not in cols:
            db.execute('ALTER TABLE websites ADD COLUMN section_data TEXT')
        db.execute(
            'UPDATE websites SET section_data = ? WHERE user_id = ?',
            (json.dumps({'menu': {'items': items}}), uid),
        )
        db.commit()


MENU_ITEMS = [
    {'id': 'b1', 'name': 'Burger', 'price': '$9', 'category': 'mains'},
    {'id': 't1', 'name': 'Taco', 'price': '$4', 'category': 'mains'},
    {'id': 'c1', 'name': 'Cola', 'price': '$2', 'category': 'drinks'},
]


def test_menu_list_and_search(app):
    _seed_menu(app, 'menu-user-2', MENU_ITEMS)
    assert len(menu_list('menu-user-2')) == 3
    assert [i['name'] for i in menu_list('menu-user-2', search='taco')] == ['Taco']
    assert len(menu_list('menu-user-2', search='mains')) == 2
    assert menu_list('menu-user-2', limit=1) != []
    with pytest.raises(ValueError):
        menu_list('')


def test_menu_item_get_by_id_and_name(app):
    _seed_menu(app, 'menu-user-3', MENU_ITEMS)
    assert menu_item_get('menu-user-3', 'b1')['name'] == 'Burger'
    assert menu_item_get('menu-user-3', 'taco')['id'] == 't1'
    assert menu_item_get('menu-user-3', 'missing') == {}
    with pytest.raises(ValueError):
        menu_item_get('menu-user-3', '')


# ---------------------------------------------------------------------------
# specials.get / events.get / hours.get
# ---------------------------------------------------------------------------

def test_specials_get_roundtrip(app):
    _seed_special(app)
    row = next(r for r in specials_list(TEST_UID) if r['item_name'] == 'MCP Taco')
    fetched = specials_get(TEST_UID, row['id'])
    assert fetched['item_name'] == 'MCP Taco'
    assert specials_get(TEST_UID, 999999) == {}
    assert specials_get('other-user', row['id']) == {}
    with pytest.raises(ValueError):
        specials_get('', row['id'])


def test_events_get_roundtrip(app):
    _seed_event(app)
    row = next(r for r in events_list(TEST_UID) if r['title'] == 'MCP Night')
    assert events_get(TEST_UID, row['id'])['title'] == 'MCP Night'
    assert events_get(TEST_UID, 999999) == {}
    with pytest.raises(ValueError):
        events_get(TEST_UID, None)


def _seed_hours(app):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        db.execute(
            'INSERT INTO hours_overrides (user_id, title, message, override_type, post_date, post_time, status) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (TEST_UID, 'Closed July 4', 'See you Friday', 'closure', '2026-07-04', '09:00', 'pending'),
        )
        db.commit()


def test_hours_get_lists_and_filters(app):
    _seed_hours(app)
    rows = hours_get(TEST_UID)
    assert any(r['title'] == 'Closed July 4' for r in rows)
    assert hours_get(TEST_UID, status='posted') == []
    with pytest.raises(ValueError):
        hours_get(TEST_UID, status='bogus')
    with pytest.raises(ValueError):
        hours_get('')


# ---------------------------------------------------------------------------
# content.adapt / content.preview
# ---------------------------------------------------------------------------

def test_content_adapt_delegates_to_adapter(app, monkeypatch):
    monkeypatch.setattr(
        'modules.platform_adapter.PlatformAdapter.adapt_all',
        lambda self, master, platforms, tone='', business=None: {p: f'{master} [{p}]' for p in platforms},
    )
    with app.app_context():
        out = content_adapt(TEST_UID, 'Hello', ['fb', 'ig'], tone='hype')
    assert out['master'] == 'Hello'
    assert out['adapted'] == {'fb': 'Hello [fb]', 'ig': 'Hello [ig]'}


def test_content_adapt_validates_inputs():
    with pytest.raises(ValueError):
        content_adapt('', 'Hi', ['fb'])
    with pytest.raises(ValueError):
        content_adapt(TEST_UID, '  ', ['fb'])
    with pytest.raises(ValueError):
        content_adapt(TEST_UID, 'Hi', [])


def test_content_preview_adds_counts_and_media_warnings(app, monkeypatch):
    monkeypatch.setattr(
        'modules.platform_adapter.PlatformAdapter.adapt_all',
        lambda self, master, platforms, tone='', business=None: {p: master for p in platforms},
    )
    with app.app_context():
        out = content_preview(TEST_UID, 'Hello', ['fb', 'ig'])
    assert out['previews']['fb']['chars'] == 5
    assert out['previews']['fb']['warnings'] == []
    assert out['previews']['ig']['warnings'] == ['instagram publishing requires image_url']
    with app.app_context():
        out2 = content_preview(TEST_UID, 'Hello', ['ig'], image_url='https://x/y.jpg')
    assert out2['previews']['ig']['warnings'] == []


# ---------------------------------------------------------------------------
# post.cancel / post.status
# ---------------------------------------------------------------------------

def test_post_cancel_delegates_to_scheduler(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        'modules.scheduler_worker.PostScheduler.cancel_job',
        lambda self, job_id: captured.update(job_id=job_id) or {'success': True},
    )
    assert post_cancel(TEST_UID, 'job-1') == {'success': True}
    assert captured == {'job_id': 'job-1'}
    with pytest.raises(ValueError):
        post_cancel('', 'job-1')
    with pytest.raises(ValueError):
        post_cancel(TEST_UID, '')


def test_post_status_found_and_unknown(monkeypatch):
    monkeypatch.setattr(
        'modules.scheduler_worker.PostScheduler.get_jobs',
        lambda self: [{'id': 'job-1', 'next_run': 'soon'}],
    )
    assert post_status(TEST_UID, 'job-1') == {
        'found': True, 'status': 'scheduled', 'next_run': 'soon',
    }
    assert post_status(TEST_UID, 'nope') == {
        'found': False, 'status': 'unknown', 'next_run': None,
    }


# ---------------------------------------------------------------------------
# analytics.top_posts / analytics.performance_summary
# ---------------------------------------------------------------------------

_SUMMARY = {
    'success': True,
    'kpis': {'posts': 2, 'reach': 30, 'likes': 5, 'engaged': 12, 'eng_rate': 40.0},
    'posts': [
        {'post_id': 'a', 'reach': 10, 'likes': 1, 'engaged': 2},
        {'post_id': 'b', 'reach': 20, 'likes': 4, 'engaged': 10},
    ],
    'ig': {'followers': 7},
}


def _mock_analytics(monkeypatch):
    import mcp.tools.publish as publish_mod
    monkeypatch.setattr(
        publish_mod, '_load_decrypted_tokens',
        lambda uid: {'facebook_token': 'tok', 'facebook_page_id': 'pg'},
    )
    monkeypatch.setattr(
        'modules.analytics_client.Analytics.get_combined_summary',
        lambda self, days=30: dict(_SUMMARY),
    )


def test_analytics_top_posts_ranks_by_metric(app, monkeypatch):
    _mock_analytics(monkeypatch)
    with app.app_context():
        out = analytics_top_posts(TEST_UID, limit=1)
    assert out['success'] is True
    assert [p['post_id'] for p in out['posts']] == ['b']
    with app.app_context():
        out = analytics_top_posts(TEST_UID, metric='likes', limit=2)
    assert [p['post_id'] for p in out['posts']] == ['b', 'a']
    with pytest.raises(ValueError):
        analytics_top_posts(TEST_UID, metric='bogus')


def test_analytics_performance_summary_compacts_kpis(app, monkeypatch):
    _mock_analytics(monkeypatch)
    with app.app_context():
        out = analytics_performance_summary(TEST_UID, days=7)
    assert out == {
        'success': True, 'days': 7, 'kpis': _SUMMARY['kpis'],
        'posts_count': 2, 'has_instagram': True,
    }


def test_analytics_projections_passthrough_when_unconnected(app):
    with app.app_context():
        assert analytics_top_posts('uid-no-tokens')['success'] is False
        assert analytics_performance_summary('uid-no-tokens')['success'] is False


# ---------------------------------------------------------------------------
# inbox.list / inbox.approve_reply / inbox.skip
# ---------------------------------------------------------------------------

def _seed_inbox_item(app, uid, **overrides):
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        row = {
            'platform': 'fb', 'platform_comment_id': f'c-{uid[-4:]}-{overrides.get("tag", "x")}',
            'comment_text': 'Great tacos!', 'sentiment': 'positive',
            'ai_draft_reply': 'Thanks for coming!', 'status': 'pending',
        }
        row.update({k: v for k, v in overrides.items() if k != 'tag'})
        cur = db.execute(
            'INSERT INTO inbox_items (user_id, platform, platform_comment_id, comment_text, '
            'sentiment, ai_draft_reply, status) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (uid, row['platform'], row['platform_comment_id'], row['comment_text'],
             row['sentiment'], row['ai_draft_reply'], row['status']),
        )
        db.commit()
        return cur.lastrowid


def test_inbox_list_returns_items_and_total(app):
    uid = 'inbox-uid-1'
    _seed_inbox_item(app, uid, tag='l1')
    _seed_inbox_item(app, uid, tag='l2')
    with app.app_context():
        out = inbox_list(uid)
    assert out['total'] >= 2
    assert all('comment_text' in i for i in out['items'])
    with pytest.raises(ValueError):
        inbox_list('')


def test_inbox_approve_reply_posts_and_marks_replied(app, monkeypatch):
    uid = 'inbox-uid-2'
    item_id = _seed_inbox_item(app, uid, tag='a1')
    import mcp.tools.publish as publish_mod
    monkeypatch.setattr(publish_mod, '_load_decrypted_tokens', lambda u: {'facebook_token': 't'})
    captured = {}
    monkeypatch.setattr(
        'modules.meta_api.MetaAPI.reply_to_facebook_comment',
        lambda self, cid, text: captured.update(cid=cid, text=text),
    )
    with app.app_context():
        out = inbox_approve_reply(uid, item_id)
    assert out['success'] is True
    assert captured['text'] == 'Thanks for coming!'  # defaulted to AI draft
    assert out['item']['status'] == 'approved'
    assert out['item']['final_reply'] == 'Thanks for coming!'


def test_inbox_approve_reply_missing_item_and_validation(app):
    with app.app_context():
        assert inbox_approve_reply('inbox-uid-2', 999999)['success'] is False
    with pytest.raises(ValueError):
        inbox_approve_reply('', 1)


def test_inbox_skip_marks_skipped(app):
    uid = 'inbox-uid-3'
    item_id = _seed_inbox_item(app, uid, tag='s1')
    with app.app_context():
        out = inbox_skip(uid, item_id)
    assert out['success'] is True
    assert out['item']['status'] == 'skipped'
    with app.app_context():
        assert inbox_skip(uid, 999999)['success'] is False


# ---------------------------------------------------------------------------
# media.list / media.get
# ---------------------------------------------------------------------------

def test_media_list_and_get(app):
    from modules.user_manager import UserManager
    uid = 'media-uid-1'
    with app.app_context():
        post_id = UserManager.log_post(uid, caption='With pic', image_url='https://x/pic.jpg')
        UserManager.log_post(uid, caption='No media here')
        rows = media_list(uid)
    assert any(r['image_url'] == 'https://x/pic.jpg' for r in rows)
    assert all(r['image_url'] or r['video_url'] for r in rows)
    with app.app_context():
        assert media_get(uid, int(post_id))['image_url'] == 'https://x/pic.jpg'
        assert media_get(uid, 999999) == {}
    with pytest.raises(ValueError):
        media_list('')


# ---------------------------------------------------------------------------
# brand.get / brand.validate
# ---------------------------------------------------------------------------

def test_brand_get_and_validate(app):
    with app.app_context():
        from modules.user_manager import UserManager
        UserManager.save_business_profile(
            TEST_UID, {'name': 'MCP Diner', 'ai_tone': 'friendly', 'ai_keywords': 'tacos, late-night'},
        )
        brand = brand_get(TEST_UID)
    assert brand['name'] == 'MCP Diner'
    assert brand['ai_tone'] == 'friendly'
    out = brand_validate(TEST_UID, 'MCP Diner has the best tacos in town!')
    assert out['verdict'] == 'pass'
    assert out['checks']['name_mentioned'] is True
    assert out['checks']['keyword_hits'] == 1
    out2 = brand_validate(TEST_UID, 'Generic post with no name.')
    assert out2['checks']['name_mentioned'] is False
    with pytest.raises(ValueError):
        brand_validate(TEST_UID, '  ')


# ---------------------------------------------------------------------------
# automation.run / automation.status
# ---------------------------------------------------------------------------

def test_automation_run_delegates_per_user(app, monkeypatch):
    with app.app_context():
        from modules.user_manager import UserManager
        UserManager.save_business_profile(TEST_UID, {'name': 'Auto Diner'})
    captured = {}
    monkeypatch.setattr(
        'modules.automation_agent._process_user',
        lambda conn, profile, today: captured.update(profile=profile) or 3,
    )
    out = automation_run(TEST_UID)
    assert out == {'success': True, 'queued': 3}
    assert captured['profile']['user_id'] == TEST_UID
    assert automation_run('uid-no-profile-here')['success'] is False
    with pytest.raises(ValueError):
        automation_run('')


def test_automation_status_lists_rows_and_handles_missing_table(app):
    assert automation_status('uid-never-automated-xyz') == []
    with app.app_context():
        from modules.database import get_db
        db = get_db()
        exists = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='automation_log'"
        ).fetchone()
        if not exists:
            db.execute(
                'CREATE TABLE automation_log (user_id TEXT, post_id TEXT, '
                'content_type TEXT, tone TEXT, keywords TEXT, master_caption TEXT, '
                'scheduled_at INTEGER, created_at INTEGER)'
            )
        cols = {r[1] for r in db.execute('PRAGMA table_info(automation_log)').fetchall()}
        # Another suite (e2e) may have created automation_log with a different
        # schema first; insert only into columns that actually exist.
        wanted = {
            'user_id': 'auto-uid-1', 'post_id': 'p1', 'content_type': 'daily_special',
            'tone': 'hype', 'keywords': '[]', 'master_caption': 'Tacos!',
            'scheduled_at': 1, 'created_at': 2,
        }
        usable = {k: v for k, v in wanted.items() if k in cols}
        assert 'user_id' in usable
        placeholders = ', '.join('?' for _ in usable)
        db.execute(
            f'INSERT INTO automation_log ({", ".join(usable)}) VALUES ({placeholders})',
            tuple(usable.values()),
        )
        db.commit()
    rows = automation_status('auto-uid-1')
    assert any(r['user_id'] == 'auto-uid-1' for r in rows)
    mine = next(r for r in rows if r['user_id'] == 'auto-uid-1')
    if 'post_id' in mine:
        assert mine['post_id'] == 'p1'


# ---------------------------------------------------------------------------
# provider.list / provider.route / provider.health
# ---------------------------------------------------------------------------

def _isolate_provider_env(monkeypatch):
    for var in ('AI_DEFAULT_PROVIDER', 'AI_FALLBACK_ORDER', 'AI_TASK_ROUTES',
                'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY',
                'OPENAI_API_KEY', 'OPENAI_MODEL'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CLAUDE_API_URL', 'http://127.0.0.1:7777/v1/generate')


def test_provider_list_reports_all_adapters_without_keys(monkeypatch):
    _isolate_provider_env(monkeypatch)
    out = provider_list()
    assert [p['name'] for p in out['providers']] == ['Muse', 'openai', 'gemini', 'anthropic']
    by_name = {p['name']: p for p in out['providers']}
    assert by_name['Muse']['available'] is True
    assert by_name['openai']['available'] is False
    assert out['aliases'] == {'Claude': 'anthropic', 'codex': 'openai'}
    assert out['default_provider'] == 'Muse'
    assert 'api_key' not in json.dumps(out)


def test_provider_route_and_health(monkeypatch):
    _isolate_provider_env(monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'dummy')
    routed = provider_route(task_type='coding')
    assert routed['selected'] == 'openai'
    routed = provider_route(task_type='content')
    assert routed['selected'] == 'Muse'
    health = provider_health('Claude')
    assert health['name'] == 'anthropic'
    assert provider_health()['providers']['openai']['available'] is True
    with pytest.raises(ValueError, match='unknown provider'):
        provider_health('nope')
    with pytest.raises(ValueError, match='capabilities must be a list'):
        provider_route(capabilities='tools')
