"""Tests for the ai/ gateway package.

Proves:
  1. Interface conformance: every adapter implements BaseAIProvider's interface
     (generate/stream/structured_output/tool_call/capabilities/is_available)
     with matching signatures.
  2. Router fallback order: selection follows preferred -> default -> fallback
     order, skipping unavailable providers and filtering by capabilities.
  3. No-SDK-import in core: gateway/router/context/base core modules never
     import a specific LLM SDK (static AST check + runtime sys.modules check).
"""

import ast
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

from ai.context import AIResponse, GatewayConfig, TaskRequirements
from ai.gateway import AIGateway
from ai.providers import PROVIDER_ALIASES, load_provider
from ai.providers.anthropic import ClaudeProvider
from ai.providers.base import INTERFACE_METHODS, LLMProvider, BaseAIProvider
from ai.providers.gemini import GeminiProvider
from ai.providers.muse import MuseProvider
from ai.providers.openai import OpenAIProvider
from ai.router import AIRouter, NoAvailableProvider

ALL_PROVIDERS = [MuseProvider, OpenAIProvider, GeminiProvider, ClaudeProvider]

CORE_FILES = [
    "ai/__init__.py",
    "ai/gateway.py",
    "ai/router.py",
    "ai/context.py",
    "ai/providers/__init__.py",
    "ai/providers/base.py",
]

FORBIDDEN_SDK_ROOTS = {
    "openai",
    "anthropic",
    "google",
    "genai",
    "generativeai",
    "gemini",
    "cohere",
    "mistral",
    "mistralai",
    "langchain",
    "llama_index",
    "boto3",
    "bedrock",
    "vertexai",
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeProvider(BaseAIProvider):
    def __init__(
        self,
        name: str = "fake",
        available: bool = True,
        caps: Optional[List[str]] = None,
        text: str = "fake-text",
        fail: bool = False,
    ) -> None:
        super().__init__({})
        self.name = name
        self._available = available
        self._caps = list(caps) if caps is not None else ["streaming", "structured", "tools"]
        self._text = text
        self._fail = fail
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def capabilities(self) -> List[str]:
        return list(self._caps)

    def _maybe_fail(self) -> None:
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"{self.name} boom")

    def generate(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> AIResponse:
        self._maybe_fail()
        return AIResponse(text=self._text, provider=self.name, model="fake-model")

    def stream(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Iterator[str]:
        self._maybe_fail()
        yield self._text

    def structured_output(
        self, prompt: str, schema: Dict[str, Any], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        self._maybe_fail()
        return {"echo": self._text}

    def tool_call(
        self, prompt: str, tools: List[Dict[str, Any]], system: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        self._maybe_fail()
        return {"content": self._text, "tool_calls": []}


# ---------------------------------------------------------------------------
# 1. Interface conformance
# ---------------------------------------------------------------------------
def test_base_interface_declares_expected_methods():
    assert LLMProvider is BaseAIProvider  # canonical contract name + alias
    assert set(INTERFACE_METHODS) == {
        "generate",
        "stream",
        "structured_output",
        "tool_call",
        "capabilities",
        "is_available",
    }
    for method in INTERFACE_METHODS:
        assert callable(getattr(LLMProvider, method)), method
    # health()/supports() are concrete helpers inherited by every adapter.
    assert callable(LLMProvider.health) and callable(LLMProvider.supports)


def test_base_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BaseAIProvider()  # type: ignore[abstract]


@pytest.mark.parametrize("cls", ALL_PROVIDERS, ids=lambda c: c.__name__)
def test_provider_implements_interface_with_matching_signatures(cls):
    assert issubclass(cls, BaseAIProvider)
    assert isinstance(cls.name, str) and cls.name
    for method in INTERFACE_METHODS:
        assert callable(getattr(cls, method)), f"{cls.__name__}.{method}"
        base_params = list(inspect.signature(getattr(BaseAIProvider, method)).parameters)
        sub_params = list(inspect.signature(getattr(cls, method)).parameters)
        assert sub_params == base_params, f"{cls.__name__}.{method} signature drift"


def test_gemini_unavailable_without_key_and_fails_cleanly(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = GeminiProvider(config={"api_key": ""})
    assert provider.is_available() is False
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        provider.generate("hi")


def test_claude_unavailable_without_key_and_fails_cleanly(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = ClaudeProvider(config={"api_key": ""})
    assert provider.is_available() is False
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        provider.generate("hi")


def test_gemini_missing_sdk_fails_cleanly(monkeypatch):
    monkeypatch.setitem(sys.modules, "google", None)
    provider = GeminiProvider(config={"api_key": "k"})
    assert provider.is_available() is True
    with pytest.raises(RuntimeError, match="google-genai.*not installed"):
        provider.generate("hi")


def test_claude_missing_sdk_fails_cleanly(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    provider = ClaudeProvider(config={"api_key": "k"})
    assert provider.is_available() is True
    with pytest.raises(RuntimeError, match="'anthropic' package is not installed"):
        provider.generate("hi")


def _fake_anthropic_client(captured, text="claude-text", tool_blocks=None):
    import types

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            blocks = [types.SimpleNamespace(type="text", text=text)]
            for block in tool_blocks or []:
                blocks.append(block)
            return types.SimpleNamespace(content=blocks, usage=None)

        def stream(self, **kwargs):
            captured.update(kwargs)

            class FakeStreamer:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                text_stream = [text]

            return FakeStreamer()

    return types.SimpleNamespace(messages=FakeMessages())


def _fake_gemini_client(captured, text="gemini-text", function_calls=None):
    import types

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(text=text, function_calls=function_calls)

        def generate_content_stream(self, **kwargs):
            captured.update(kwargs)
            return [types.SimpleNamespace(text=text)]

    return types.SimpleNamespace(models=FakeModels())


def test_claude_forwards_prompt_verbatim_with_fake_client(monkeypatch):
    captured: Dict[str, Any] = {}
    provider = ClaudeProvider(config={"api_key": "k", "model": "m"})
    monkeypatch.setattr(provider, "_client", lambda: _fake_anthropic_client(captured))
    response = provider.generate("Hello world", system="sys")
    assert captured["messages"] == [{"role": "user", "content": "Hello world"}]
    assert captured["system"] == "sys"
    assert response.text == "claude-text"
    assert response.provider == "anthropic"
    assert list(provider.stream("hi")) == ["claude-text"]


def test_claude_tool_call_normalizes_blocks(monkeypatch):
    import types

    captured: Dict[str, Any] = {}
    tool_block = types.SimpleNamespace(
        type="tool_use", id="t1", name="menu_get", input={"a": 1}
    )
    provider = ClaudeProvider(config={"api_key": "k"})
    monkeypatch.setattr(
        provider, "_client", lambda: _fake_anthropic_client(captured, tool_blocks=[tool_block])
    )
    result = provider.tool_call("hi", [{"name": "menu_get"}])
    assert result["tool_calls"] == [{"id": "t1", "name": "menu_get", "input": {"a": 1}}]


def test_gemini_forwards_prompt_verbatim_with_fake_client(monkeypatch):
    captured: Dict[str, Any] = {}
    provider = GeminiProvider(config={"api_key": "k", "model": "m"})
    monkeypatch.setattr(provider, "_client", lambda: _fake_gemini_client(captured))
    response = provider.generate("Hello world", system="sys")
    assert captured["contents"] == "Hello world"  # verbatim, no business logic
    assert captured["config"]["system_instruction"] == "sys"
    assert response.text == "gemini-text"
    assert response.provider == "gemini"
    assert list(provider.stream("hi")) == ["gemini-text"]


def test_gemini_structured_uses_json_mime_type(monkeypatch):
    captured: Dict[str, Any] = {}
    provider = GeminiProvider(config={"api_key": "k"})
    monkeypatch.setattr(
        provider, "_client", lambda: _fake_gemini_client(captured, text='{"ok": true}')
    )
    assert provider.structured_output("hi", {"type": "object"}) == {"ok": True}
    assert captured["config"]["response_mime_type"] == "application/json"


def test_openai_model_override_with_fake_client(monkeypatch):
    import types

    captured: Dict[str, Any] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content="o-text", tool_calls=None)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message)], usage=None
            )

    fake_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )
    provider = OpenAIProvider(config={"api_key": "k", "model": "default-model"})
    monkeypatch.setattr(provider, "_client", lambda: fake_client)
    response = provider.generate("hi", model="override-model")
    assert captured["model"] == "override-model"
    assert response.model == "override-model"


def test_openai_unavailable_without_key_and_fails_cleanly(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider(config={"api_key": ""})
    assert provider.is_available() is False
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider.generate("hi")


def test_muse_env_configuration(monkeypatch):
    monkeypatch.setenv("CLAUDE_API_URL", "http://claude.test/v1")
    monkeypatch.setenv("CLAUDE_API_KEY", "secret")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-test")
    provider = MuseProvider()
    assert provider.api_url == "http://claude.test/v1"
    assert provider.api_key == "secret"
    assert provider.model == "claude-test"
    assert provider.is_available() is True


def test_muse_forwards_prompt_verbatim_without_network(monkeypatch):
    import urllib.request

    captured: Dict[str, Any] = {}

    class FakeHTTPResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"text": "reply-text"}).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = MuseProvider(config={"api_url": "http://claude.test/v1", "model": "m"})
    response = provider.generate("Hello world", system="sys", model="override")

    assert captured["url"] == "http://claude.test/v1"
    assert captured["body"]["prompt"] == "Hello world"  # verbatim, no business logic
    assert captured["body"]["system"] == "sys"
    assert captured["body"]["model"] == "override"  # per-request model selection
    assert response.text == "reply-text"
    assert response.provider == "Muse"
    assert response.model == "override"


# ---------------------------------------------------------------------------
# 2. Router fallback order
# ---------------------------------------------------------------------------
def test_router_fallback_order_skips_unavailable():
    providers = {
        "a": FakeProvider("a", available=False),
        "b": FakeProvider("b", available=True),
        "c": FakeProvider("c", available=True),
    }
    router = AIRouter(providers, fallback_order=["a", "b", "c"], default_provider="a")
    assert [p.name for p in router.candidates()] == ["b", "c"]
    assert router.select().name == "b"


def test_router_prefers_task_preferred_provider():
    providers = {"b": FakeProvider("b"), "c": FakeProvider("c")}
    router = AIRouter(providers, fallback_order=["b", "c"], default_provider="b")
    selected = router.select(TaskRequirements(preferred_provider="c"))
    assert selected.name == "c"


def test_router_filters_by_capabilities():
    providers = {
        "plain": FakeProvider("plain", caps=[]),
        "tooled": FakeProvider("tooled", caps=["tools"]),
    }
    router = AIRouter(providers, fallback_order=["plain", "tooled"], default_provider="plain")
    assert router.select(TaskRequirements(capabilities=["tools"])).name == "tooled"


def test_router_raises_when_nothing_available():
    router = AIRouter({"a": FakeProvider("a", available=False)}, fallback_order=["a"])
    with pytest.raises(NoAvailableProvider):
        router.select()


def test_gateway_falls_back_on_failure_in_order():
    bad = FakeProvider("bad", text="bad-text", fail=True)
    good = FakeProvider("good", text="good-text")
    gateway = AIGateway(
        providers={"bad": bad, "good": good},
        fallback_order=["bad", "good"],
        default_provider="bad",
    )
    response = gateway.generate("hi")
    assert response.text == "good-text"
    assert response.provider == "good"
    assert (bad.calls, good.calls) == (1, 1)


def test_gateway_raises_when_all_providers_fail():
    gateway = AIGateway(
        providers={"x": FakeProvider("x", fail=True)},
        fallback_order=["x"],
        default_provider="x",
    )
    with pytest.raises(RuntimeError, match="All AI providers failed"):
        gateway.generate("hi")


def test_gateway_stream_and_structured_use_router_order():
    first = FakeProvider("first", available=False)
    second = FakeProvider("second", text="s-text")
    gateway = AIGateway(
        providers={"first": first, "second": second},
        fallback_order=["first", "second"],
        default_provider="first",
    )
    assert "".join(gateway.stream("hi")) == "s-text"
    assert gateway.structured_output("hi", {"type": "object"}) == {"echo": "s-text"}
    assert gateway.tool_call("hi", []) == {"content": "s-text", "tool_calls": []}


# ---------------------------------------------------------------------------
# 3. No-SDK-import in core
# ---------------------------------------------------------------------------
def _imported_root_modules(tree: ast.AST) -> List[str]:
    roots: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.append(node.module.split(".")[0])
    return roots


def test_core_files_have_no_sdk_imports():
    repo_root = Path(__file__).resolve().parent.parent
    violations = []
    for rel in CORE_FILES:
        path = repo_root / rel
        assert path.exists(), f"core file missing: {rel}"
        roots = _imported_root_modules(ast.parse(path.read_text(encoding="utf-8")))
        bad = sorted(set(roots) & FORBIDDEN_SDK_ROOTS)
        if bad:
            violations.append(f"{rel}: {bad}")
    assert not violations, f"SDK imports found in core: {violations}"


def test_importing_core_pulls_in_no_sdk_modules():
    before = set(sys.modules) & FORBIDDEN_SDK_ROOTS
    for module in [m for m in sys.modules if m == "ai" or m.startswith("ai.")]:
        del sys.modules[module]
    import ai.gateway  # noqa: F401
    import ai.router  # noqa: F401

    after = set(sys.modules) & FORBIDDEN_SDK_ROOTS
    assert after - before == set()

    # Adapters must also be importable without any SDK installed/imported.
    import ai.providers.anthropic  # noqa: F401
    import ai.providers.gemini  # noqa: F401
    import ai.providers.muse  # noqa: F401
    import ai.providers.openai  # noqa: F401

    after_adapters = set(sys.modules) & FORBIDDEN_SDK_ROOTS
    assert after_adapters - before == set()


# ---------------------------------------------------------------------------
# 4. Task-type routing, env config, registry aliases, health
# ---------------------------------------------------------------------------
def _named_fakes(*names):
    return {name: FakeProvider(name) for name in names}


def test_task_routing_content_prefers_claude_then_codex():
    providers = _named_fakes("Muse", "openai", "anthropic", "gemini")
    router = AIRouter(
        providers,
        fallback_order=["gemini", "openai", "anthropic", "Muse"],
        default_provider="gemini",
    )
    assert router.select(TaskRequirements(task_type="content")).name == "Muse"
    assert router.select(TaskRequirements(task_type="marketing")).name == "Muse"


def test_task_routing_structured_prefers_gemini_and_coding_prefers_openai():
    providers = _named_fakes("Muse", "openai", "anthropic", "gemini")
    router = AIRouter(
        providers,
        fallback_order=["Muse", "anthropic", "openai", "gemini"],
        default_provider="Muse",
    )
    assert router.select(TaskRequirements(task_type="structured")).name == "gemini"
    assert router.select(TaskRequirements(task_type="analysis")).name == "gemini"
    assert router.select(TaskRequirements(task_type="coding")).name == "openai"
    assert router.select(TaskRequirements(task_type="admin")).name == "openai"


def test_task_routing_falls_back_when_routed_provider_unavailable():
    providers = {
        "Muse": FakeProvider("Muse", available=False),
        "anthropic": FakeProvider("anthropic", available=False),
        "openai": FakeProvider("openai"),
    }
    router = AIRouter(
        providers,
        fallback_order=["openai", "Muse", "anthropic"],
        default_provider="Muse",
    )
    assert router.select(TaskRequirements(task_type="content")).name == "openai"


def test_explicit_preferred_provider_beats_task_route():
    providers = _named_fakes("Muse", "openai")
    router = AIRouter(providers, fallback_order=["Muse", "openai"], default_provider="Muse")
    selected = router.select(TaskRequirements(task_type="coding", preferred_provider="Muse"))
    assert selected.name == "Muse"


def test_gateway_config_from_env(monkeypatch):
    monkeypatch.setenv("AI_DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("AI_FALLBACK_ORDER", "openai,gemini")
    monkeypatch.setenv("AI_TASK_ROUTES", '{"content": ["gemini"]}')
    config = GatewayConfig.from_env()
    assert config.default_provider == "openai"
    assert config.fallback_order == ["openai", "gemini"]
    assert config.task_routes["content"] == ["gemini"]
    # Non-overridden task routes keep their defaults.
    assert config.task_routes["coding"] == ["openai"]


def test_gateway_config_from_env_rejects_bad_json(monkeypatch):
    monkeypatch.setenv("AI_TASK_ROUTES", "not-json")
    with pytest.raises(ValueError, match="AI_TASK_ROUTES"):
        GatewayConfig.from_env()


def test_registry_aliases_resolve_to_canonical_adapters():
    assert PROVIDER_ALIASES["Claude"] == "anthropic"
    assert PROVIDER_ALIASES["codex"] == "openai"
    # Compare by class name: the no-SDK-import test above purges ai.* from
    # sys.modules and reimports it, so class identity is not stable here.
    assert type(load_provider("Claude", config={"api_key": ""})).__name__ == "ClaudeProvider"
    assert type(load_provider("codex", config={"api_key": ""})).__name__ == "OpenAIProvider"
    with pytest.raises(KeyError):
        load_provider("no-such-provider")


def test_gateway_health_reports_every_provider_without_network():
    gateway = AIGateway(
        providers=_named_fakes("Muse", "openai"),
        fallback_order=["Muse", "openai"],
        default_provider="Muse",
    )
    health = gateway.health()
    assert health["default_provider"] == "Muse"
    assert health["fallback_order"] == ["Muse", "openai"]
    assert set(health["providers"]) == {"Muse", "openai"}
    assert health["providers"]["Muse"]["available"] is True
    assert "tools" in health["providers"]["openai"]["capabilities"]


def test_gateway_explain_describes_routing():
    gateway = AIGateway(
        providers=_named_fakes("Muse", "openai", "gemini"),
        fallback_order=["Muse", "openai", "gemini"],
        default_provider="Muse",
    )
    explained = gateway.explain(TaskRequirements(task_type="coding"))
    assert explained["task_type"] == "coding"
    assert explained["selected"] == "openai"
    assert explained["ordered_candidates"][0] == "openai"
