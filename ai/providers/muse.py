"""Muse provider adapter.

Functional, env-configured transport adapter with no business logic: prompts
are forwarded verbatim to the configured HTTP endpoint using only the standard
library (no LLM SDK). Response text is extracted from common envelope keys.

Env config:
  CLAUDE_API_URL  chat endpoint (default http://127.0.0.1:7777/v1/generate)
  CLAUDE_API_KEY  optional bearer token
  CLAUDE_MODEL    model label echoed back in AIResponse (default "Muse")
  CLAUDE_TIMEOUT  request timeout in seconds (default 30)
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional

from ai.context import AIResponse
from ai.providers.base import LLMProvider

DEFAULT_API_URL = "http://127.0.0.1:7777/v1/generate"
TEXT_KEYS = ("text", "response", "content", "output")


class MuseProvider(LLMProvider):
    """Local Muse/JOSH endpoint adapter (HTTP, stdlib only)."""

    name: str = "Muse"

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        cfg = self.config
        self.api_url: str = cfg.get("api_url") or os.environ.get("CLAUDE_API_URL", DEFAULT_API_URL)
        self.api_key: str = cfg.get("api_key") or os.environ.get("CLAUDE_API_KEY", "")
        self.model: str = cfg.get("model") or os.environ.get("CLAUDE_MODEL", "Muse")
        try:
            self.timeout: float = float(cfg.get("timeout") or os.environ.get("CLAUDE_TIMEOUT", 30))
        except (TypeError, ValueError):
            self.timeout = 30.0

    def is_available(self) -> bool:
        return bool(self.api_url)

    def capabilities(self) -> List[str]:
        return ["streaming", "structured", "tools"]

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, payload: Dict[str, Any]) -> Any:
        import urllib.error
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.api_url, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MuseProvider request failed: {exc}") from exc
        try:
            return json.loads(body)
        except ValueError:
            return body

    @staticmethod
    def _extract_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in TEXT_KEYS:
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
            nested = payload.get("data")
            if isinstance(nested, dict):
                for key in TEXT_KEYS:
                    value = nested.get(key)
                    if isinstance(value, str) and value:
                        return value
        raise ValueError(f"MuseProvider: no text field in response: {payload!r:.200}")

    def _payload(
        self, prompt: str, system: Optional[str], extra: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": extra.pop("model", self.model), "prompt": prompt}
        if system is not None:
            payload["system"] = system
        payload.update(extra)
        return payload

    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        payload = self._payload(prompt, system, dict(kwargs))
        raw = self._post(payload)
        return AIResponse(
            text=self._extract_text(raw),
            provider=self.name,
            model=payload["model"],
            raw=raw,
        )

    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        # Transport-level chunking: single request, text yielded in chunks.
        text = self.generate(prompt, system=system, **kwargs).text
        chunk_size = 200
        for index in range(0, len(text), chunk_size):
            yield text[index : index + chunk_size]

    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        raw = self._post(self._payload(prompt, system, {"schema": schema, **kwargs}))
        text = self._extract_text(raw)
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"MuseProvider: response is not valid JSON: {text!r:.200}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"MuseProvider: expected JSON object, got: {text!r:.200}")
        return parsed

    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        raw = self._post(self._payload(prompt, system, {"tools": tools, **kwargs}))
        if isinstance(raw, dict):
            return raw
        text = self._extract_text(raw)
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"MuseProvider: tool response is not valid JSON: {text!r:.200}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"MuseProvider: expected JSON object, got: {text!r:.200}")
        return parsed
