"""
integrations/culinaryos/client.py — Adapter-only CulinaryOS client.

Reads CulinaryOS data (menu, specials, events, hours) and normalizes it into
Post-Pilot shapes. Post-Pilot services then decide what to generate, schedule,
or publish. No marketing logic lives here.

Transports:
- REST pull (implemented): GET {base_url}/v1/{menu,specials,events,hours}
  with `Authorization: Bearer <api_key>`. Timeouts + explicit errors; the
  caller decides retries/fallbacks.
- Webhooks (implemented): HMAC-SHA256 verification + payload normalization.
- MCP / plugin-SDK (future): thin wrappers call these same normalize_*
  functions; see contract.md.
"""

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10


@dataclass
class CulinaryOSConfig:
    """Connection config. Secrets come from env vars, never hardcode."""
    base_url: str
    api_key: str = ''
    webhook_secret: str = ''
    timeout: int = DEFAULT_TIMEOUT
    headers: Dict[str, str] = field(default_factory=dict)


class CulinaryOSError(RuntimeError):
    """Raised for transport/auth failures talking to CulinaryOS."""


# ---------------------------------------------------------------------------
# Normalizers: CulinaryOS payloads -> Post-Pilot shapes
# ---------------------------------------------------------------------------

def normalize_menu(payload: Any) -> Dict[str, list]:
    """Return {'items': [{name, description, price}]} from any reasonable menu payload."""
    items: List[Dict[str, str]] = []
    raw_items: list = []
    if isinstance(payload, dict):
        raw_items = payload.get('items') or payload.get('menu') or payload.get('data') or []
    elif isinstance(payload, list):
        raw_items = payload
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        items.append({
            'name': str(entry.get('name', entry.get('title', ''))),
            'description': str(entry.get('description', '')),
            'price': str(entry.get('price', '')),
        })
    return {'items': items}


def normalize_specials(payload: Any) -> List[Dict[str, str]]:
    """Return Post-Pilot specials-shaped rows from a CulinaryOS payload."""
    rows: List[Dict[str, str]] = []
    raw: list = payload if isinstance(payload, list) else (payload or {}).get('specials', []) \
        if isinstance(payload, dict) else []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rows.append({
            'item_name': str(entry.get('item_name', entry.get('name', ''))),
            'description': str(entry.get('description', '')),
            'price': str(entry.get('price', '')),
            'post_date': str(entry.get('date', entry.get('post_date', ''))),
            'post_time': str(entry.get('time', entry.get('post_time', '09:00'))),
        })
    return rows


def normalize_events(payload: Any) -> List[Dict[str, str]]:
    """Return Post-Pilot events-shaped rows from a CulinaryOS payload."""
    rows: List[Dict[str, str]] = []
    raw: list = payload if isinstance(payload, list) else (payload or {}).get('events', []) \
        if isinstance(payload, dict) else []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rows.append({
            'title': str(entry.get('title', entry.get('name', ''))),
            'description': str(entry.get('description', '')),
            'event_date': str(entry.get('event_date', entry.get('date', ''))),
            'ticket_url': str(entry.get('ticket_url', entry.get('url', ''))),
        })
    return rows


def normalize_hours(payload: Any) -> Dict[str, str]:
    """Return {'summary': ..., 'days': {...}} hours snapshot."""
    if isinstance(payload, dict):
        days = payload.get('days') or payload.get('hours') or {}
        summary = payload.get('summary', '')
        if isinstance(days, dict):
            return {'summary': str(summary), 'days': {str(k): str(v) for k, v in days.items()}}
        return {'summary': str(summary or payload), 'days': {}}
    return {'summary': str(payload or ''), 'days': {}}


# ---------------------------------------------------------------------------
# Webhooks: verify + parse (transport-agnostic, no Flask import)
# ---------------------------------------------------------------------------

def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Verify an HMAC-SHA256 hex signature over the raw request body."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def parse_webhook_event(payload: Dict) -> Dict[str, Any]:
    """Normalize an inbound CulinaryOS webhook into {type, data}.

    Supported event types: menu.updated, special.created, event.created,
    hours.updated. Unknown types pass through with type='unknown'.
    """
    event_type = str(payload.get('type', payload.get('event', 'unknown')))
    data = payload.get('data', payload)
    normalizers = {
        'menu.updated': normalize_menu,
        'special.created': lambda d: {'specials': normalize_specials(d)},
        'event.created': lambda d: {'events': normalize_events(d)},
        'hours.updated': normalize_hours,
    }
    normalizer = normalizers.get(event_type)
    try:
        normalized = normalizer(data) if normalizer else data
    except Exception as exc:  # never crash the webhook receiver on bad data
        logger.warning('CulinaryOS webhook normalize failed for %s: %s', event_type, exc)
        return {'type': event_type, 'data': data, 'normalized': None, 'error': str(exc)}
    return {'type': event_type, 'data': data, 'normalized': normalized}


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------

class CulinaryOSClient:
    """Minimal REST pull client. Adapter only — returns normalized data."""

    def __init__(self, config: CulinaryOSConfig):
        if not config.base_url:
            raise ValueError('base_url is required')
        self.config = config

    @classmethod
    def from_env(cls) -> 'CulinaryOSClient':
        """Build from CULINARYOS_BASE_URL / CULINARYOS_API_KEY / CULINARYOS_WEBHOOK_SECRET."""
        import os
        return cls(CulinaryOSConfig(
            base_url=os.environ.get('CULINARYOS_BASE_URL', ''),
            api_key=os.environ.get('CULINARYOS_API_KEY', ''),
            webhook_secret=os.environ.get('CULINARYOS_WEBHOOK_SECRET', ''),
        ))

    def _get(self, path: str) -> Any:
        import requests
        url = self.config.base_url.rstrip('/') + path
        headers = {'Accept': 'application/json', **self.config.headers}
        if self.config.api_key:
            headers['Authorization'] = f'Bearer {self.config.api_key}'
        try:
            resp = requests.get(url, headers=headers, timeout=self.config.timeout)
        except Exception as exc:
            raise CulinaryOSError(f'GET {path} failed: {exc}') from exc
        if resp.status_code == 401:
            raise CulinaryOSError('CulinaryOS auth rejected (401) — check CULINARYOS_API_KEY')
        if resp.status_code >= 400:
            raise CulinaryOSError(f'GET {path} returned HTTP {resp.status_code}')
        try:
            return resp.json()
        except ValueError as exc:
            raise CulinaryOSError(f'GET {path} returned non-JSON body') from exc

    def get_menu(self) -> Dict[str, list]:
        """Fetch + normalize the current menu."""
        return normalize_menu(self._get('/v1/menu'))

    def get_specials(self) -> List[Dict[str, str]]:
        """Fetch + normalize current specials."""
        return normalize_specials(self._get('/v1/specials'))

    def get_events(self) -> List[Dict[str, str]]:
        """Fetch + normalize upcoming events."""
        return normalize_events(self._get('/v1/events'))

    def get_hours(self) -> Dict[str, str]:
        """Fetch + normalize hours."""
        return normalize_hours(self._get('/v1/hours'))

    def health(self) -> Dict[str, str]:
        """Lightweight connectivity check (no auth required by contract)."""
        try:
            self._get('/v1/health')
            return {'ok': True, 'base_url': self.config.base_url}
        except CulinaryOSError as exc:
            return {'ok': False, 'base_url': self.config.base_url, 'error': str(exc)}
