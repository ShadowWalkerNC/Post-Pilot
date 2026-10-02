"""Provider interface for the AI gateway.

Defines the contract every adapter must implement. No LLM SDK imports here.

The canonical contract name is :class:`LLMProvider`. ``BaseAIProvider`` is a
backwards-compatible alias kept for existing importers.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse

#: Methods every provider adapter must expose.
INTERFACE_METHODS = (
    "generate",
    "stream",
    "structured_output",
    "tool_call",
    "capabilities",
    "is_available",
)


class LLMProvider(abc.ABC):
    """Abstract base class for all AI provider adapters.

    Adapters are pure transports: prompts are forwarded verbatim and no
    business logic lives here. Concrete SDK imports must be lazy (inside
    methods) so importing an adapter never requires the SDK to be installed.
    """

    name: str = "base"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = dict(config or {})

    @abc.abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        """Generate a single completion for the prompt. Returns an AIResponse."""
        raise NotImplementedError

    @abc.abstractmethod
    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        """Yield response text chunks for the prompt."""
        raise NotImplementedError

    @abc.abstractmethod
    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate output conforming to the given JSON-schema-like dict."""
        raise NotImplementedError

    @abc.abstractmethod
    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        """Generate a tool call given the prompt and a list of tool definitions."""
        raise NotImplementedError

    @abc.abstractmethod
    def capabilities(self) -> List[str]:
        """Capability tokens this provider supports (e.g. streaming, structured, tools)."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Whether this provider is currently configured and usable."""
        return True

    def supports(self, capability: str) -> bool:
        """Whether this provider advertises the given capability token."""
        return capability in (self.capabilities() or [])

    def health(self) -> Dict[str, Any]:
        """Lightweight status snapshot (no network calls by default).

        Adapters may override this to add a live ping, but the default must
        stay cheap so ``provider.health`` can poll every provider safely.
        """
        return {
            "name": self.name,
            "available": bool(self.is_available()),
            "model": getattr(self, "model", None),
            "capabilities": list(self.capabilities() or []),
        }


#: Backwards-compatible alias for the provider contract.
BaseAIProvider = LLMProvider
