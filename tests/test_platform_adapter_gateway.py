"""Gateway migration tests for modules/platform_adapter.py.

Locks the migration contract:
  1. Adapt prompts are byte-identical to the legacy direct-OpenAI prompts
     (golden system/user messages).
  2. Adaptation routes through the gateway client with task_type="content",
     the adapter model, and the same sampling params.
  3. Fallbacks are unchanged: unknown platform -> master, gateway failure ->
     master, no provider -> master, Twitter hard-truncated at 280 chars.
  4. The module holds no direct LLM SDK imports anymore.
"""

import ast
from pathlib import Path

from ai.context import AIResponse

from modules.platform_adapter import PlatformAdapter

BIZ = {'name': 'Taco Truck', 'type': 'food_truck', 'location': 'Main St'}

FB_RULES = (
    'Write in a warm, conversational tone. '
    '1-3 short paragraphs. Emojis welcome but not excessive (3-6 max). '
    'End with a soft call-to-action (visit us, tag a friend, comment below). '
    'Do NOT add more than 5 hashtags -- Facebook deprioritises hashtag-heavy posts.'
)

GOLDEN_SYSTEM = (
    'You are a social media copywriter specialising in Facebook content. '
    'You adapt provided captions to suit the platform perfectly. '
    'Always return ONLY the adapted caption text -- no explanations, '
    'no labels, no quotes around the output.'
)
GOLDEN_USER = (
    'Adapt the following caption for Facebook. Tone: friendly. '
    'Max characters: 500.\n'
    'Business context: Business name: Taco Truck, Business type: Food Truck, '
    'Location: Main St.\n'
    f'\nPlatform rules:\n{FB_RULES}\n'
    '\nMaster caption to adapt:\nTacos today!\n'
    '\nReturn ONLY the adapted Facebook caption:'
)


class FakeGateway:
    """Captures generate() args; returns canned text or raises."""

    def __init__(self, text='Adapted caption', fail=False):
        self._text = text
        self._fail = fail
        self.captured = {}
        self.calls = 0

    def generate(self, prompt, system=None, requirements=None, **kwargs):
        self.calls += 1
        if self._fail:
            raise RuntimeError('All AI providers failed')
        self.captured['prompt'] = prompt
        self.captured['system'] = system
        self.captured['requirements'] = requirements
        self.captured['kwargs'] = kwargs
        return AIResponse(text=self._text, provider='fake', model='fake-model')


def _adapted_adapter(text='Adapted caption', fail=False, **adapter_kwargs):
    adapter = PlatformAdapter(**adapter_kwargs)
    fake = FakeGateway(text=text, fail=fail)
    adapter._client = fake
    return adapter, fake


# ---------------------------------------------------------------------------
# 1. Prompt construction unchanged
# ---------------------------------------------------------------------------

def test_adapt_prompts_match_legacy_golden_format():
    adapter, fake = _adapted_adapter()
    out = adapter.adapt_one('Tacos today!', 'fb', 'friendly', BIZ)
    assert out == 'Adapted caption'
    assert fake.captured['prompt'] == GOLDEN_USER
    assert fake.captured['system'] == GOLDEN_SYSTEM


# ---------------------------------------------------------------------------
# 2. Gateway routing
# ---------------------------------------------------------------------------

def test_adapt_routes_through_gateway_with_content_task_and_model():
    adapter, fake = _adapted_adapter()
    adapter.adapt_one('Hi', 'fb', 'friendly', BIZ)
    assert fake.captured['requirements'].task_type == 'content'
    assert fake.captured['kwargs'] == {
        'model': 'gpt-4o-mini',  # adapter default passed through
        'max_tokens': 256,  # max(256, 500 // 2)
        'temperature': 0.7,
    }


def test_adapter_model_override_reaches_gateway():
    adapter, fake = _adapted_adapter(model='custom-model')
    adapter.adapt_one('Hi', 'ig', 'hype', BIZ)
    assert fake.captured['kwargs']['model'] == 'custom-model'
    assert fake.captured['kwargs']['max_tokens'] == 1100  # max(256, 2200 // 2)


# ---------------------------------------------------------------------------
# 3. Fallbacks unchanged
# ---------------------------------------------------------------------------

def test_unknown_platform_falls_back_to_master_without_calling_gateway():
    adapter, fake = _adapted_adapter()
    assert adapter.adapt_all('Master text', ['xx-unknown'], business=BIZ) == {
        'xx-unknown': 'Master text'
    }
    assert fake.calls == 0
    assert adapter.adapt_one('Master text', 'xx-unknown', business=BIZ) == 'Master text'


def test_gateway_failure_falls_back_to_master():
    adapter, _ = _adapted_adapter(fail=True)
    assert adapter.adapt_all('Master text', ['fb', 'ig'], business=BIZ) == {
        'fb': 'Master text', 'ig': 'Master text'
    }
    assert adapter.adapt_one('Master text', 'fb', business=BIZ) == 'Master text'


def test_twitter_hard_truncation_preserved():
    adapter, _ = _adapted_adapter(text='x' * 300)
    out = adapter.adapt_one('Master text', 'tw', business=BIZ)
    assert out == 'x' * 277 + '...'
    assert len(out) == 280


def test_no_client_falls_back_to_master(monkeypatch):
    monkeypatch.setattr(PlatformAdapter, '_get_client', lambda self: None)
    adapter = PlatformAdapter()
    assert adapter.adapt_all('Master text', ['fb', 'ig'], business=BIZ) == {
        'fb': 'Master text', 'ig': 'Master text'
    }
    assert adapter.adapt_one('Master text', 'fb', business=BIZ) == 'Master text'


def test_get_client_none_when_no_provider_available(monkeypatch):
    for var in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('CLAUDE_API_URL', '')
    assert PlatformAdapter()._get_client() is None


# ---------------------------------------------------------------------------
# 4. No direct LLM SDK imports
# ---------------------------------------------------------------------------

def test_no_direct_llm_sdk_imports():
    source = Path('modules/platform_adapter.py').read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.')[0])
    assert roots.isdisjoint({'openai', 'anthropic', 'google', 'genai'}), roots
