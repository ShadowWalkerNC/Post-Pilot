"""
mcp/tools/provider.py — provider.list + provider.route + provider.health (read-only).

Delegates to: the ai/ LLM gateway (registry + router explain + health).
No network calls: health() is a cheap local snapshot (configuration +
declared capabilities), never a live ping.
"""

from typing import List, Optional

SPEC_PROVIDER_LIST = {
    'name': 'provider.list',
    'description': 'List registered LLM providers with availability, model, and capabilities.',
    'permission': 'read',
    'auth': 'Operator tool: reveals provider configuration status, never API keys.',
    'inputs': {},
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_PROVIDER_ROUTE = {
    'name': 'provider.route',
    'description': 'Preview which provider would serve a request (no generation).',
    'permission': 'read',
    'auth': 'Operator tool: routing preview only, never API keys.',
    'inputs': {
        'task_type': 'Optional task type (content, structured, coding, ...)',
        'preferred_provider': 'Optional explicit provider name or alias',
        'capabilities': 'Optional list of required capability tokens',
    },
    'secrets': 'Never returns tokens or API keys.',
}

SPEC_PROVIDER_HEALTH = {
    'name': 'provider.health',
    'description': 'Health snapshot for one provider (or all when name omitted).',
    'permission': 'read',
    'auth': 'Operator tool: configuration status only, never API keys.',
    'inputs': {'name': 'Optional provider name or alias (Claude, codex, ...)'},
    'secrets': 'Never returns tokens or API keys.',
}


def provider_list() -> dict:
    """Return {providers, aliases, default_provider, fallback_order}."""
    from ai.gateway import build_gateway
    from ai.providers import KNOWN_PROVIDERS, PROVIDER_ALIASES
    health = build_gateway().health()
    providers = []
    for name in KNOWN_PROVIDERS:
        snapshot = health['providers'].get(name, {})
        providers.append({
            'name': name,
            'available': snapshot.get('available', False),
            'model': snapshot.get('model'),
            'capabilities': snapshot.get('capabilities', []),
        })
    return {
        'providers': providers,
        'aliases': dict(PROVIDER_ALIASES),
        'default_provider': health['default_provider'],
        'fallback_order': health['fallback_order'],
    }


def provider_route(
    task_type: Optional[str] = None,
    preferred_provider: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
) -> dict:
    """Return the router explanation for the given requirements (no generation)."""
    from ai.context import TaskRequirements
    from ai.gateway import build_gateway
    if capabilities is not None and not isinstance(capabilities, list):
        raise ValueError('capabilities must be a list')
    requirements = TaskRequirements(
        capabilities=list(capabilities or []),
        preferred_provider=preferred_provider,
        task_type=task_type,
    )
    return dict(build_gateway().explain(requirements))


def provider_health(name: Optional[str] = None) -> dict:
    """Return one provider snapshot, or the full health dict when name omitted."""
    from ai.gateway import build_gateway
    from ai.providers import canonical_name
    health = build_gateway().health()
    if name is None:
        return health
    canonical = canonical_name(name)
    if canonical not in health['providers']:
        raise ValueError(f'unknown provider: {name}')
    return health['providers'][canonical]
