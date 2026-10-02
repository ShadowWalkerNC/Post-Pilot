"""
tests/test_retention_and_location.py
Unit and endpoint tests for Phase 6 Retention (Morning Daily Prompt & One-Tap Location Post).
"""

import json
from unittest.mock import patch, MagicMock


def test_cron_daily_prompt_unauthorized(client):
    """Calling /api/cron/daily_prompt without secret returns 401."""
    resp = client.get('/api/cron/daily_prompt')
    assert resp.status_code == 401


def test_cron_daily_prompt_authorized(client, monkeypatch):
    """Calling /api/cron/daily_prompt with correct Bearer token triggers send_morning_prompts_to_due_users."""
    monkeypatch.setenv('CRON_SECRET', 'test-cron-secret-xyz')
    # Re-read _CRON_SECRET in blueprints.cron
    import blueprints.cron as cron_module
    cron_module._CRON_SECRET = 'test-cron-secret-xyz'

    with patch('modules.notification_service.send_morning_prompts_to_due_users') as mock_send:
        mock_send.return_value = {'success': True, 'sent': 2, 'skipped': 1, 'errors': []}
        resp = client.get(
            '/api/cron/daily_prompt',
            headers={'Authorization': 'Bearer test-cron-secret-xyz'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['summary']['sent'] == 2


def test_cron_health_includes_daily_prompt(client):
    """Health check route advertises daily_prompt."""
    resp = client.get('/api/cron/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'daily_prompt' in data['endpoints']


def test_one_tap_location_unauthorized(client):
    """Unauthenticated call to /api/location/one_tap redirects or returns 401/302."""
    resp = client.post('/api/location/one_tap', json={'lat': 35.7796, 'lng': -78.6382})
    assert resp.status_code in (302, 401)


def test_one_tap_location_happy_path(logged_in_client):
    """Logged in user can generate one-tap location post with GPS coordinates."""
    with patch('modules.location_service.reverse_geocode') as mock_geo, \
         patch('modules.location_service.update_website_location') as mock_web:
        mock_geo.return_value = {
            'display_name': 'Downtown Plaza, Main St',
            'city': 'Raleigh',
            'lat': 35.7796,
            'lng': -78.6382,
        }
        mock_web.return_value = True

        resp = logged_in_client.post('/api/location/one_tap', json={
            'lat': 35.7796,
            'lng': -78.6382,
            'special': 'Tacos Al Pastor $3',
            'publish_now': False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        payload = data['payload']
        assert payload['ready'] is True
        assert 'Downtown Plaza' in payload['captions']['facebook']
        assert 'Tacos Al Pastor' in payload['captions']['facebook']


def test_one_tap_location_with_address(logged_in_client):
    """Logged in user can generate one-tap location post with manual address string."""
    with patch('modules.location_service.update_website_location') as mock_web:
        mock_web.return_value = True

        resp = logged_in_client.post('/api/location/one_tap', json={
            'address': 'Brewery Bhavana Lot',
            'special': 'Smoked Brisket Sandwich',
            'publish_now': False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        payload = data['payload']
        assert payload['ready'] is True
        assert 'Brewery Bhavana Lot' in payload['captions']['instagram']
