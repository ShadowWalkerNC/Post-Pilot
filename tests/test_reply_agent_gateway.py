"""Gateway migration tests for modules/reply_agent.py.

Locks the migration contract:
  1. Draft prompts are byte-identical to the legacy per-provider prompts
     (golden system/user messages).
  2. Drafting routes through ai.gateway structured_output with
     task_type="content" and the same sampling params (max_tokens=150,
     temperature=0.7).
  3. Gateway failure (or empty reply) falls back to the unchanged
     deterministic sentiment + template matrix.
  4. The module holds no direct LLM SDK imports anymore.
"""

import ast
from pathlib import Path

import modules.reply_agent as reply_agent
from modules.reply_agent import (
    _build_draft_messages,
    _call_gateway_llm,
    analyze_and_draft,
)

GOLDEN_SYSTEM = (
    'You are the social media community manager for Taco Haven, a restaurant'
    ' in Raleigh.\n'
    'Tone style: friendly.\n'
    "Analyze the user comment, verify or refine its sentiment ('positive', "
    "'neutral', 'negative', 'question', 'spam'), "
    'and write a concise, authentic, on-brand social media response '
    '(1-2 sentences). If spam, reply should be empty string.\n'
    'Output valid JSON strictly formatted as: '
    '{"sentiment": "...", "reply": "..."}'
)
GOLDEN_USER = 'Original Post Context: "New menu!"\nComment: "Love the tacos!"'


class FakeGateway:
    """Captures structured_output() args; returns canned dict or raises."""

    def __init__(self, data=None, fail=False):
        self._data = {'sentiment': 'positive', 'reply': 'Gateway draft!'} \
            if data is None else data
        self._fail = fail
        self.captured = {}

    def structured_output(self, prompt, schema, system=None, requirements=None, **kwargs):
        if self._fail:
            raise RuntimeError('All AI providers failed')
        self.captured['prompt'] = prompt
        self.captured['schema'] = schema
        self.captured['system'] = system
        self.captured['requirements'] = requirements
        self.captured['kwargs'] = kwargs
        return self._data


def _patch_gateway(monkeypatch, **fake_kwargs):
    fake = FakeGateway(**fake_kwargs)
    monkeypatch.setattr('ai.gateway.build_gateway', lambda *a, **k: fake)
    return fake


# ---------------------------------------------------------------------------
# 1. Prompt construction unchanged
# ---------------------------------------------------------------------------

def test_build_draft_messages_matches_legacy_golden_format():
    system, user = _build_draft_messages(
        'Love the tacos!', 'friendly', 'Taco Haven', 'restaurant', 'Raleigh', 'New menu!'
    )
    assert system == GOLDEN_SYSTEM
    assert user == GOLDEN_USER


def test_build_draft_messages_without_location_or_context():
    system, user = _build_draft_messages(
        'Hi', 'hype', 'X', 'cafe', '', None
    )
    assert system.startswith(
        'You are the social media community manager for X, a cafe.\n'
    )
    assert user == 'Comment: "Hi"'


# ---------------------------------------------------------------------------
# 2. Gateway routing
# ---------------------------------------------------------------------------

def test_call_gateway_llm_delegates_with_content_task(monkeypatch):
    fake = _patch_gateway(monkeypatch)
    result = _call_gateway_llm(
        'Love the tacos!', 'positive', 'friendly',
        'Taco Haven', 'restaurant', 'Raleigh', 'New menu!',
    )
    assert result == {'sentiment': 'positive', 'reply': 'Gateway draft!'}
    assert fake.captured['prompt'] == GOLDEN_USER
    assert fake.captured['system'] == GOLDEN_SYSTEM
    assert fake.captured['requirements'].task_type == 'content'
    assert fake.captured['kwargs'] == {'max_tokens': 150, 'temperature': 0.7}
    assert set(fake.captured['schema']['properties']) == {'sentiment', 'reply'}


def test_call_gateway_llm_rejects_invalid_sentiment(monkeypatch):
    _patch_gateway(monkeypatch, data={'sentiment': 'ecstatic', 'reply': 'Hi!'})
    result = _call_gateway_llm('Hi', 'neutral', 'friendly', 'X', 'cafe', '', None)
    assert result['sentiment'] == 'neutral'  # initial kept
    assert result['reply'] == 'Hi!'


# ---------------------------------------------------------------------------
# 3. Failure -> fallback matrix (unchanged behavior)
# ---------------------------------------------------------------------------

def test_call_gateway_llm_failure_returns_none(monkeypatch):
    _patch_gateway(monkeypatch, fail=True)
    assert _call_gateway_llm('Hi', 'neutral', 'friendly', 'X', 'cafe', '', None) is None


def test_call_gateway_llm_non_dict_returns_none(monkeypatch):
    _patch_gateway(monkeypatch, data=['not', 'a', 'dict'])
    assert _call_gateway_llm('Hi', 'neutral', 'friendly', 'X', 'cafe', '', None) is None


def test_analyze_and_draft_uses_gateway_reply_on_success(monkeypatch):
    _patch_gateway(monkeypatch)
    out = analyze_and_draft('Love the tacos!', business_name='Taco Haven')
    assert out['ai_draft_reply'] == 'Gateway draft!'
    assert out['sentiment'] == 'positive'
    assert out['source'] == 'gateway'
    assert out['confidence'] == 0.95


def test_analyze_and_draft_falls_back_on_gateway_failure(monkeypatch):
    _patch_gateway(monkeypatch, fail=True)
    out = analyze_and_draft('Love the tacos!', business_name='Taco Haven')
    assert out['source'] == 'fallback'
    assert out['confidence'] == 0.85
    assert 'Taco Haven' in out['ai_draft_reply']


def test_analyze_and_draft_spam_stays_empty(monkeypatch):
    _patch_gateway(monkeypatch, fail=True)
    out = analyze_and_draft('Buy followers now at bit.ly/xyz crypto earn $500')
    assert out['sentiment'] == 'spam'
    assert out['ai_draft_reply'] == ''


def test_legacy_provider_functions_removed():
    assert not hasattr(reply_agent, '_call_openai_llm')
    assert not hasattr(reply_agent, '_call_claude_llm')


# ---------------------------------------------------------------------------
# 4. No direct LLM SDK imports
# ---------------------------------------------------------------------------

def test_no_direct_llm_sdk_imports():
    source = Path('modules/reply_agent.py').read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.')[0])
    assert roots.isdisjoint({'openai', 'anthropic', 'google', 'genai'}), roots
