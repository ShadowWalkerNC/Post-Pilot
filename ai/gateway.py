"""AI gateway facade.

Single entry point for AI generation. Routes each request through AIRouter and
falls back to the next candidate when a provider fails. No LLM SDK imports
here; concrete adapters are loaded lazily.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse, GatewayConfig, TaskRequirements
from ai.providers.base import LLMProvider
from ai.router import AIRouter, NoAvailableProvider


class AIGateway:
    """Provider-agnostic generation facade with fallback."""

    def __init__(
        self,
        providers: Optional[Dict[str, LLMProvider]] = None,
        fallback_order: Optional[List[str]] = None,
        default_provider: Optional[str] = None,
        provider_configs: Optional[Dict[str, Dict[str, Any]]] = None,
        task_routes: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        if providers is None:
            providers = _build_default_providers(provider_configs or {}, fallback_order)
        if fallback_order is None:
            fallback_order = GatewayConfig().fallback_order
        self.providers: Dict[str, LLMProvider] = dict(providers)
        self.router = AIRouter(
            self.providers,
            fallback_order=fallback_order,
            default_provider=default_provider,
            task_routes=task_routes,
        )

    def health(self) -> Dict[str, Any]:
        """Status snapshot for every registered provider (no network calls)."""
        return {
            "default_provider": self.router.default_provider,
            "fallback_order": list(self.router.fallback_order),
            "providers": {
                name: provider.health() for name, provider in self.providers.items()
            },
        }

    def explain(self, requirements: Optional[TaskRequirements] = None) -> Dict[str, object]:
        """Describe how a request would route (backs the provider.route tool)."""
        return self.router.explain(requirements)

    def _candidates(self, requirements: Optional[TaskRequirements]) -> List[LLMProvider]:
        matches = self.router.candidates(requirements)
        if not matches:
            raise NoAvailableProvider("No available provider matches the task requirements")
        return matches

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        requirements: Optional[TaskRequirements] = None,
        **kwargs: Any,
    ) -> AIResponse:
        """Generate via the first provider that succeeds, in router order."""
        errors: List[str] = []
        for provider in self._candidates(requirements):
            try:
                return provider.generate(prompt, system=system, **kwargs)
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")

    def stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        requirements: Optional[TaskRequirements] = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream via the first provider that succeeds, in router order."""
        errors: List[str] = []
        for provider in self._candidates(requirements):
            try:
                yield from provider.stream(prompt, system=system, **kwargs)
                return
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")

    def structured_output(
        self,
        prompt: str,
        schema: Dict[str, Any],
        system: Optional[str] = None,
        requirements: Optional[TaskRequirements] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Structured output via the first provider that succeeds, in router order."""
        errors: List[str] = []
        for provider in self._candidates(requirements):
            try:
                return provider.structured_output(prompt, schema, system=system, **kwargs)
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")

    def tool_call(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        requirements: Optional[TaskRequirements] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Tool call via the first provider that succeeds, in router order."""
        errors: List[str] = []
        for provider in self._candidates(requirements):
            try:
                return provider.tool_call(prompt, tools, system=system, **kwargs)
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                errors.append(f"{provider.name}: {exc}")
        raise RuntimeError(f"All AI providers failed: {'; '.join(errors)}")


def _build_default_providers(
    provider_configs: Dict[str, Dict[str, Any]], fallback_order: Optional[List[str]]
) -> Dict[str, LLMProvider]:
    from ai.providers import KNOWN_PROVIDERS, load_provider

    names = list(fallback_order) if fallback_order else list(KNOWN_PROVIDERS)
    for name in KNOWN_PROVIDERS:
        if name not in names:
            names.append(name)
    return {name: load_provider(name, config=provider_configs.get(name)) for name in names}


def build_gateway(config: Optional[GatewayConfig] = None) -> AIGateway:
    """Build a gateway from a GatewayConfig (env-derived when omitted)."""
    config = config or GatewayConfig.from_env()
    return AIGateway(
        fallback_order=config.fallback_order,
        default_provider=config.default_provider,
        provider_configs=config.provider_configs,
        task_routes=config.task_routes,
    )
