"""Post-Pilot AI gateway package.

Provider-agnostic facade over LLM providers. Core modules in this package
(ai/__init__.py, gateway.py, router.py, context.py, providers/base.py)
must never import a specific LLM SDK. SDK usage lives only inside the
concrete adapters under ai/providers/.
"""

from ai.context import (
    AIRequest,
    AIResponse,
    DEFAULT_TASK_ROUTES,
    GatewayConfig,
    TaskRequirements,
)
from ai.gateway import AIGateway, build_gateway
from ai.router import AIRouter, NoAvailableProvider
from ai.providers.base import LLMProvider, BaseAIProvider

__all__ = [
    "AIGateway",
    "AIRouter",
    "AIRequest",
    "AIResponse",
    "BaseAIProvider",
    "DEFAULT_TASK_ROUTES",
    "GatewayConfig",
    "LLMProvider",
    "NoAvailableProvider",
    "TaskRequirements",
    "build_gateway",
]
