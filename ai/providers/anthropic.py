"""Claude provider adapter (Anthropic API).

Thin transport adapter: prompts are forwarded verbatim to the Anthropic
messages API. The ``anthropic`` SDK is imported lazily inside methods so
importing this module never requires the SDK to be installed. No business
logic here.

Env config:
  ANTHROPIC_API_KEY   required for availability
  ANTHROPIC_MODEL     default "claude-3-5-sonnet-20241022"
  ANTHROPIC_MAX_TOKENS default 1024
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse
from ai.providers.base import LLMProvider

DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_MAX_TOKENS = 1024
JSON_INSTRUCTION = "Respond with a single JSON object and nothing else."


class ClaudeProvider(LLMProvider):
    """Anthropic messages API adapter (also serves the "Claude" alias)."""

    name: str = "anthropic"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        cfg = self.config
        self.api_key: str = cfg.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model: str = cfg.get("model") or os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
        try:
            self.max_tokens: int = int(
                cfg.get("max_tokens") or os.environ.get("ANTHROPIC_MAX_TOKENS", DEFAULT_MAX_TOKENS)
            )
        except (TypeError, ValueError):
            self.max_tokens = DEFAULT_MAX_TOKENS

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> List[str]:
        return ["streaming", "structured", "tools"]

    def _client(self) -> Any:
        if not self.api_key:
            raise RuntimeError("ClaudeProvider: ANTHROPIC_API_KEY is not configured")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError(
                "ClaudeProvider: the 'anthropic' package is not installed"
            ) from exc
        return Anthropic(api_key=self.api_key)

    @staticmethod
    def _messages(prompt: str) -> List[Dict[str, str]]:
        return [{"role": "user", "content": prompt}]

    @staticmethod
    def _text_of(response: Any) -> str:
        parts = []
        for block in getattr(response, "content", None) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts).strip()

    @staticmethod
    def _usage_of(response: Any) -> Dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        try:
            return dict(usage)
        except (TypeError, ValueError):
            return {}

    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        client = self._client()
        model = kwargs.pop("model", self.model)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._messages(prompt),
        }
        if system is not None:
            create_kwargs["system"] = system
        create_kwargs.update(kwargs)
        response = client.messages.create(**create_kwargs)
        return AIResponse(
            text=self._text_of(response),
            provider=self.name,
            model=model,
            usage=self._usage_of(response),
            raw=response,
        )

    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        stream_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._messages(prompt),
        }
        if system is not None:
            stream_kwargs["system"] = system
        stream_kwargs.update(kwargs)
        with client.messages.stream(**stream_kwargs) as streamer:
            for text in streamer.text_stream:
                if text:
                    yield text

    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        response = self.generate(f"{prompt}\n\n{JSON_INSTRUCTION}", system=system, **kwargs)
        try:
            parsed = json.loads(response.text)
        except ValueError as exc:
            raise ValueError(
                f"ClaudeProvider: response is not valid JSON: {response.text!r:.200}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"ClaudeProvider: expected JSON object, got: {response.text!r:.200}")
        return parsed

    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._messages(prompt),
            "tools": tools,
        }
        if system is not None:
            create_kwargs["system"] = system
        create_kwargs.update(kwargs)
        response = client.messages.create(**create_kwargs)
        tool_calls = []
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    {
                        "id": getattr(block, "id", None),
                        "name": getattr(block, "name", None),
                        "input": getattr(block, "input", None),
                    }
                )
        return {"content": self._text_of(response), "tool_calls": tool_calls}
