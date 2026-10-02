"""OpenAI provider adapter.

Thin transport adapter: prompts are forwarded verbatim to the OpenAI chat
completions API. The OpenAI SDK is imported lazily inside methods so importing
this module never requires the SDK to be installed. No business logic here.

Env config:
  OPENAI_API_KEY  required for availability
  OPENAI_MODEL    default "gpt-4o-mini"
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse
from ai.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI / Codex adapter (lazy SDK import; also serves the "codex" alias)."""

    name: str = "openai"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        cfg = self.config
        self.api_key: str = cfg.get("api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.model: str = cfg.get("model") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> List[str]:
        return ["streaming", "structured", "tools"]

    def _client(self) -> Any:
        if not self.api_key:
            raise RuntimeError("OpenAIProvider: OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAIProvider: the 'openai' package is not installed") from exc
        return OpenAI(api_key=self.api_key)

    @staticmethod
    def _messages(prompt: str, system: Optional[str]) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        client = self._client()
        model = kwargs.pop("model", self.model)
        response = client.chat.completions.create(
            model=model, messages=self._messages(prompt, system), **kwargs
        )
        message = response.choices[0].message
        usage = {}
        if getattr(response, "usage", None):
            usage = response.usage.model_dump() if hasattr(response.usage, "model_dump") else dict(response.usage)
        return AIResponse(
            text=(message.content or "").strip(),
            provider=self.name,
            model=model,
            usage=usage,
            raw=response,
        )

    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        kwargs.setdefault("stream", True)
        for chunk in client.chat.completions.create(
            model=model, messages=self._messages(prompt, system), **kwargs
        ):
            delta = chunk.choices[0].delta if chunk.choices else None
            content = getattr(delta, "content", None) if delta else None
            if content:
                yield content

    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        kwargs.setdefault("response_format", {"type": "json_object"})
        response = self.generate(prompt, system=system, **kwargs)
        try:
            parsed = json.loads(response.text)
        except ValueError as exc:
            raise ValueError(
                f"OpenAIProvider: response is not valid JSON: {response.text!r:.200}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"OpenAIProvider: expected JSON object, got: {response.text!r:.200}")
        return parsed

    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        response = client.chat.completions.create(
            model=model, messages=self._messages(prompt, system), tools=tools, **kwargs
        )
        message = response.choices[0].message
        tool_calls = []
        for call in getattr(message, "tool_calls", None) or []:
            tool_calls.append(
                {
                    "id": getattr(call, "id", None),
                    "type": getattr(call, "type", "function"),
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
            )
        return {"content": message.content, "tool_calls": tool_calls}
