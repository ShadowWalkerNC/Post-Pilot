"""Gateway migration tests for modules/ai_generator.py.

Locks the migration contract:
  1. Prompt construction is byte-identical to the legacy direct-OpenAI call
     (golden system/user messages).
  2. Generation routes through ai.gateway with task_type="content" and the
     same sampling params (max_tokens=300, temperature=0.8).
  3. Any gateway failure (or empty text) yields None so callers fall back to
     the unchanged template path.
  4. The module holds no direct LLM SDK imports anymore.
"""

import ast
from pathlib import Path

from ai.context import AIResponse

import modules.ai_generator as ai_gen
from modules.ai_generator import (
    _build_messages,
    _generate_llm,
    generate_caption,
    generate_with_adaptations,
)

BIZ = {
    'name': 'Taco Truck',
    'type': 'food truck',
    'location': 'Raleigh',
    'special': 'Taco Tuesday',
}

# Golden messages, transcribed from the legacy direct-OpenAI implementation.
# If these change, the gateway is no longer receiving the legacy prompts.
GOLDEN_SYSTEM_MASTER = (
    'You write energetic, hype social media captions with lots of excitement '
    'and urgency. Use fire/rocket emojis sparingly.'
    '\n\nYou are writing for: Taco Truck, a food truck. Located at: Raleigh.'
    '\n\nPlatform rules: Write a clear, engaging, platform-neutral social media '
    'caption. No hashtags. No platform-specific formatting. '
    'Focus on the core message and CTA only. '
    'This caption will be adapted for specific platforms separately.'
)
GOLDEN_USER = (
    "Write a daily_special post. Today's special: Taco Tuesday. "
    'Keywords to include: fresh. Return only the caption text, nothing else.'
)


class FakeGateway:
    """Captures generate() args; returns canned text or raises."""

    def __init__(self, text='  Gateway caption  ', fail=False):
        self._text = text
        self._fail = fail
        self.captured = {}

    def generate(self, prompt, system=None, requirements=None, **kwargs):
        if self._fail:
            raise RuntimeError('All AI providers failed')
        self.captured['prompt'] = prompt
        self.captured['system'] = system
        self.captured['requirements'] = requirements
        self.captured['kwargs'] = kwargs
        return AIResponse(text=self._text, provider='fake', model='fake-model')


def _patch_gateway(monkeypatch, **fake_kwargs):
    fake = FakeGateway(**fake_kwargs)
    monkeypatch.setattr('ai.gateway.build_gateway', lambda *a, **k: fake)
    return fake


# ---------------------------------------------------------------------------
# 1. Prompt construction unchanged
# ---------------------------------------------------------------------------

def test_build_messages_matches_legacy_golden_format():
    system, user = _build_messages(BIZ, 'daily_special', 'hype', ['fresh'], 'master')
    assert system == GOLDEN_SYSTEM_MASTER
    assert user == GOLDEN_USER


def test_build_messages_platform_style_and_defaults():
    system, user = _build_messages(
        {'name': 'X'}, 'general', 'unknown-tone', [], 'facebook'
    )
    # Unknown tone falls back to friendly; per-platform style used otherwise.
    assert system.startswith(
        'You write warm, conversational social media captions.'
    )
    assert 'Facebook post: 1-3 sentences.' in system
    assert 'Located at' not in system
    assert user == 'Write a general post. Return only the caption text, nothing else.'


# ---------------------------------------------------------------------------
# 2. Gateway routing
# ---------------------------------------------------------------------------

def test_generate_llm_delegates_to_gateway_with_content_task(monkeypatch):
    fake = _patch_gateway(monkeypatch)
    caption = _generate_llm(BIZ, 'daily_special', 'hype', ['fresh'], 'master')
    assert caption == 'Gateway caption'  # stripped
    assert fake.captured['prompt'] == GOLDEN_USER
    assert fake.captured['system'] == GOLDEN_SYSTEM_MASTER
    assert fake.captured['requirements'].task_type == 'content'
    assert fake.captured['kwargs'] == {'max_tokens': 300, 'temperature': 0.8}


def test_generate_openai_alias_preserved():
    assert ai_gen._generate_openai is _generate_llm


# ---------------------------------------------------------------------------
# 3. Failure -> None -> template fallback (unchanged behavior)
# ---------------------------------------------------------------------------

def test_generate_llm_gateway_failure_returns_none(monkeypatch):
    _patch_gateway(monkeypatch, fail=True)
    assert _generate_llm(BIZ, 'general', 'friendly', [], 'facebook') is None


def test_generate_llm_empty_text_returns_none(monkeypatch):
    _patch_gateway(monkeypatch, text='   ')
    assert _generate_llm(BIZ, 'general', 'friendly', [], 'facebook') is None


def test_generate_caption_template_fallback_on_gateway_failure(monkeypatch):
    monkeypatch.setattr(ai_gen, '_generate_llm', lambda *a, **k: None)
    caption = generate_caption(BIZ, 'daily_special', 'hype', [], 'facebook')
    assert "Today's special at Taco Truck" in caption


def test_generate_with_adaptations_template_master_on_gateway_failure(monkeypatch):
    monkeypatch.setattr(ai_gen, '_generate_llm', lambda *a, **k: None)
    monkeypatch.setattr(
        'modules.platform_adapter.PlatformAdapter.adapt_all',
        lambda self, master, platforms, tone='', business=None: {p: master for p in platforms},
    )
    out = generate_with_adaptations(BIZ, 'daily_special', 'hype', [], ['fb'])
    assert "Today's special at Taco Truck" in out['master']
    assert out['adapted'] == {'fb': out['master']}


# ---------------------------------------------------------------------------
# 4. No direct LLM SDK usage in the migrated module
# ---------------------------------------------------------------------------

def test_no_direct_llm_sdk_imports():
    source = Path('modules/ai_generator.py').read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.')[0])
    assert roots.isdisjoint({'openai', 'anthropic', 'google', 'genai'}), roots
