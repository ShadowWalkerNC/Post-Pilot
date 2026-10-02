"""Gemini provider adapter (Google GenAI API).

Thin transport adapter: prompts are forwarded verbatim to the Gemini API.
The ``google-genai`` SDK (``from google import genai``) is imported lazily
inside methods so importing this module never requires the SDK to be
installed. No business logic here.

Env config:
  GEMINI_API_KEY  required for availability (also accepts GOOGLE_API_KEY)
  GEMINI_MODEL    default "gemini-2.0-flash"
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse
from ai.providers.base import LLMProvider

DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(LLMProvider):
    """Google Gemini adapter via the google-genai SDK (lazy import)."""

    name: str = "gemini"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        cfg = self.config
        self.api_key: str = (
            cfg.get("api_key")
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
        )
        self.model: str = cfg.get("model") or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> List[str]:
        return ["streaming", "structured", "tools"]

    def _client(self) -> Any:
        if not self.api_key:
            raise RuntimeError("GeminiProvider: GEMINI_API_KEY is not configured")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError(
                "GeminiProvider: the 'google-genai' package is not installed"
            ) from exc
        return genai.Client(api_key=self.api_key)

    def _config(self, system: Optional[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config: Dict[str, Any] = dict(extra or {})
        if system is not None:
            config.setdefault("system_instruction", system)
        return config

    @staticmethod
    def _text_of(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text.strip()
        parts = []
        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                chunk = getattr(part, "text", None)
                if isinstance(chunk, str):
                    parts.append(chunk)
        return "".join(parts).strip()

    @staticmethod
    def _declarations(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize OpenAI/Anthropic-style tool defs to Gemini function declarations."""
        declarations = []
        for tool in tools:
            fn = tool.get("function", tool) if isinstance(tool, dict) else {}
            name = fn.get("name", tool.get("name") if isinstance(tool, dict) else None)
            if not name:
                continue
            declarations.append(
                {
                    "name": name,
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", fn.get("input_schema", {})),
                }
            )
        return declarations

    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        client = self._client()
        model = kwargs.pop("model", self.model)
        config = self._config(system, kwargs.pop("config", None))
        response = client.models.generate_content(
            model=model, contents=prompt, config=config or None, **kwargs
        )
        return AIResponse(
            text=self._text_of(response),
            provider=self.name,
            model=model,
            usage={},
            raw=response,
        )

    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        config = self._config(system, kwargs.pop("config", None))
        for chunk in client.models.generate_content_stream(
            model=model, contents=prompt, config=config or None, **kwargs
        ):
            text = self._text_of(chunk)
            if text:
                yield text

    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        config = self._config(system, kwargs.pop("config", None))
        config.setdefault("response_mime_type", "application/json")
        response = client.models.generate_content(
            model=model, contents=prompt, config=config, **kwargs
        )
        text = self._text_of(response)
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise ValueError(
                f"GeminiProvider: response is not valid JSON: {text!r:.200}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"GeminiProvider: expected JSON object, got: {text!r:.200}")
        return parsed

    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        client = self._client()
        model = kwargs.pop("model", self.model)
        config = self._config(system, kwargs.pop("config", None))
        config.setdefault("tools", [{"function_declarations": self._declarations(tools)}])
        response = client.models.generate_content(
            model=model, contents=prompt, config=config, **kwargs
        )
        calls = []
        for call in getattr(response, "function_calls", None) or []:
            calls.append(
                {
                    "name": getattr(call, "name", None),
                    "args": getattr(call, "args", None),
                    "id": getattr(call, "id", None),
                }
            )
        return {"content": self._text_of(response), "tool_calls": calls}
