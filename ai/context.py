"""Shared context types for the AI gateway.

Pure data types only: no LLM SDK imports, no network access, no business logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Default task-type routes: task_type -> ordered provider names.
#: - content/marketing -> Muse or Claude-family (Anthropic API)
#: - structured analysis -> Gemini
#: - coding/dev/admin -> Codex (OpenAI)
DEFAULT_TASK_ROUTES: Dict[str, List[str]] = {
    "content": ["Muse", "anthropic"],
    "marketing": ["Muse", "anthropic"],
    "structured": ["gemini"],
    "analysis": ["gemini"],
    "coding": ["openai"],
    "dev": ["openai"],
    "admin": ["openai"],
}


@dataclass
class TaskRequirements:
    """Per-request routing requirements consumed by AIRouter."""

    capabilities: List[str] = field(default_factory=list)
    preferred_provider: Optional[str] = None
    task_type: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


@dataclass
class AIRequest:
    """A provider-agnostic generation request."""

    prompt: str
    system: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """A provider-agnostic generation response."""

    text: str
    provider: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None


@dataclass
class GatewayConfig:
    """Static gateway configuration.

    No provider is ever required: the gateway serves any request from
    whichever providers are available, in router order. Env overrides are
    applied by :meth:`from_env` (AI_DEFAULT_PROVIDER, AI_FALLBACK_ORDER as a
    comma-separated list, AI_TASK_ROUTES as a JSON object).
    """

    default_provider: str = "Muse"
    fallback_order: List[str] = field(
        default_factory=lambda: ["Muse", "openai", "anthropic", "gemini"]
    )
    task_routes: Dict[str, List[str]] = field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_TASK_ROUTES.items()}
    )
    provider_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        """Build a config from environment variables, falling back to defaults."""
        default_provider = os.environ.get("AI_DEFAULT_PROVIDER", "Muse").strip() or "Muse"
        raw_fallback = os.environ.get("AI_FALLBACK_ORDER", "").strip()
        if raw_fallback:
            fallback_order = [p.strip() for p in raw_fallback.split(",") if p.strip()]
        else:
            fallback_order = ["Muse", "openai", "anthropic", "gemini"]
        task_routes = {k: list(v) for k, v in DEFAULT_TASK_ROUTES.items()}
        raw_routes = os.environ.get("AI_TASK_ROUTES", "").strip()
        if raw_routes:
            try:
                overrides = json.loads(raw_routes)
            except ValueError as exc:
                raise ValueError(f"AI_TASK_ROUTES is not valid JSON: {exc}") from exc
            if not isinstance(overrides, dict):
                raise ValueError("AI_TASK_ROUTES must be a JSON object of task_type to provider list")
            for task_type, providers in overrides.items():
                if not isinstance(providers, list) or not all(
                    isinstance(p, str) for p in providers
                ):
                    raise ValueError(
                        f"AI_TASK_ROUTES[{task_type!r}] must be a list of provider names"
                    )
                task_routes[str(task_type)] = list(providers)
        return cls(
            default_provider=default_provider,
            fallback_order=fallback_order,
            task_routes=task_routes,
        )
