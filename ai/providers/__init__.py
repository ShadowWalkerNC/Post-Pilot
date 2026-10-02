"""Provider adapter registry.

Only re-exports the SDK-free base interface at import time. Concrete adapters
are loaded lazily via load_provider() so importing this package never pulls in
any LLM SDK.
"""

from .base import INTERFACE_METHODS, LLMProvider, BaseAIProvider

_PROVIDER_MODULES = {
    "Muse": ".muse",
    "openai": ".openai",
    "gemini": ".gemini",
    "anthropic": ".anthropic",
}

_PROVIDER_CLASSES = {
    "Muse": "MuseProvider",
    "openai": "OpenAIProvider",
    "gemini": "GeminiProvider",
    "anthropic": "ClaudeProvider",
}

#: Friendly aliases resolved to canonical provider names by load_provider().
PROVIDER_ALIASES = {
    "Claude": "anthropic",  # Claude-family API (Anthropic)
    "codex": "openai",  # Codex runs on the OpenAI adapter
}

KNOWN_PROVIDERS = tuple(_PROVIDER_MODULES)


def canonical_name(name: str) -> str:
    """Resolve an alias to its canonical provider name (unknown names unchanged)."""
    return PROVIDER_ALIASES.get(name, name)


def register_provider(name: str, module: str, classname: str) -> None:
    """Register (or override) a provider adapter for load_provider()."""
    _PROVIDER_MODULES[name] = module
    _PROVIDER_CLASSES[name] = classname


def load_provider(name: str, config=None) -> LLMProvider:
    """Instantiate a provider adapter by name or alias.

    Raises KeyError for unknown names.
    """
    import importlib

    canonical = PROVIDER_ALIASES.get(name, name)
    module = importlib.import_module(_PROVIDER_MODULES[canonical], package=__name__)
    cls = getattr(module, _PROVIDER_CLASSES[canonical])
    return cls(config=config)


__all__ = [
    "BaseAIProvider",
    "LLMProvider",
    "INTERFACE_METHODS",
    "KNOWN_PROVIDERS",
    "PROVIDER_ALIASES",
    "canonical_name",
    "load_provider",
    "register_provider",
]
