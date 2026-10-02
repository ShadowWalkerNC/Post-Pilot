"""
integrations.culinaryos — Adapter-only integration for CulinaryOS.

Post-Pilot owns ALL marketing logic (generation, scheduling, publishing,
analytics). This package only translates between CulinaryOS data/events and
Post-Pilot services. It must never contain caption templates, prompts, or
publishing logic of its own.

Supported (current + future) channels, all optional and independent:
- REST pull: CulinaryOSClient fetches menu/specials/events/hours snapshots.
- Webhooks: verify + normalize inbound CulinaryOS event payloads.
- MCP: CulinaryOS data can be re-exposed through mcp/tools (see contract.md).
- Plugin SDK: a future CulinaryOS plugin host can call the adapter functions.
"""

from integrations.culinaryos.client import (
    CulinaryOSClient,
    CulinaryOSConfig,
    normalize_menu,
    normalize_specials,
    normalize_events,
    normalize_hours,
    verify_webhook_signature,
    parse_webhook_event,
)

__all__ = [
    'CulinaryOSClient',
    'CulinaryOSConfig',
    'normalize_menu',
    'normalize_specials',
    'normalize_events',
    'normalize_hours',
    'verify_webhook_signature',
    'parse_webhook_event',
]
