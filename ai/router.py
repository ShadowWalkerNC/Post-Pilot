"""Provider router for the AI gateway.

Selects a provider from explicit preference, task-type routes, static config,
provider availability, and the configured fallback order. No LLM SDK imports
here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ai.context import GatewayConfig, TaskRequirements
from ai.providers.base import LLMProvider


class NoAvailableProvider(RuntimeError):
    """Raised when no provider can serve a request."""


class AIRouter:
    """Orders registered providers for a request and picks the best candidate."""

    def __init__(
        self,
        providers: Dict[str, LLMProvider],
        fallback_order: Optional[List[str]] = None,
        default_provider: Optional[str] = None,
        task_routes: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self.providers = dict(providers)
        config = GatewayConfig()
        if fallback_order is None:
            fallback_order = config.fallback_order
        self.fallback_order = list(fallback_order)
        self.default_provider = default_provider if default_provider is not None else config.default_provider
        self.task_routes = dict(task_routes) if task_routes is not None else dict(config.task_routes)

    def _ordered_names(self, requirements: Optional[TaskRequirements]) -> List[str]:
        order: List[str] = []
        preferred = requirements.preferred_provider if requirements else None
        if preferred:
            order.append(preferred)
        task_type = requirements.task_type if requirements else None
        if task_type and task_type in self.task_routes:
            for name in self.task_routes[task_type]:
                if name not in order:
                    order.append(name)
        if self.default_provider and self.default_provider not in order:
            order.append(self.default_provider)
        for name in self.fallback_order:
            if name not in order:
                order.append(name)
        for name in self.providers:
            if name not in order:
                order.append(name)
        return order

    def candidates(self, requirements: Optional[TaskRequirements] = None) -> List[LLMProvider]:
        """Available providers in selection order, filtered by required capabilities."""
        ordered = [
            self.providers[name]
            for name in self._ordered_names(requirements)
            if name in self.providers and self.providers[name].is_available()
        ]
        if requirements and requirements.capabilities:
            required = set(requirements.capabilities)
            ordered = [p for p in ordered if required.issubset(set(p.capabilities()))]
        return ordered

    def select(self, requirements: Optional[TaskRequirements] = None) -> LLMProvider:
        """Return the best provider for the requirements, or raise NoAvailableProvider."""
        matches = self.candidates(requirements)
        if not matches:
            raise NoAvailableProvider("No available provider matches the task requirements")
        return matches[0]

    def explain(self, requirements: Optional[TaskRequirements] = None) -> Dict[str, object]:
        """Describe how a request would route (names only; backs provider.route)."""
        return {
            "task_type": requirements.task_type if requirements else None,
            "preferred_provider": requirements.preferred_provider if requirements else None,
            "capabilities": list(requirements.capabilities) if requirements else [],
            "ordered_candidates": [p.name for p in self.candidates(requirements)],
            "selected": self.select(requirements).name if self.candidates(requirements) else None,
        }
