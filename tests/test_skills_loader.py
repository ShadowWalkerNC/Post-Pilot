"""
tests/test_skills_loader.py — tests for the provider-agnostic skills loader.
No LLM SDKs, no network, no Flask app required.
"""

import os

import pytest

from skills.loader import (
    SKILLS_ROOT,
    frontmatter_body,
    get_prompt,
    list_skills,
    load_all_skills,
    load_skill,
    parse_frontmatter,
    render_prompt,
    render_skill_prompt,
    skill_manifest,
    validate_skill,
)

EXPECTED_SKILLS = {'special_post', 'event_campaign', 'weekly_plan', 'review_reply', 'brand_guard'}


def test_list_skills_discovers_all_five():
    assert EXPECTED_SKILLS.issubset(set(list_skills()))


def test_each_skill_has_skill_md_prompts_and_rules():
    for name in EXPECTED_SKILLS:
        skill_dir = os.path.join(SKILLS_ROOT, name)
        assert os.path.isfile(os.path.join(skill_dir, 'SKILL.md'))
        assert os.path.isdir(os.path.join(skill_dir, 'prompts'))
        assert os.path.isdir(os.path.join(skill_dir, 'rules'))
        skill = load_skill(name)
        assert skill.prompts, f'{name} has no prompts'
        assert skill.rules, f'{name} has no rules'


def test_frontmatter_parses_name_version_description_inputs():
    skill = load_skill('special_post')
    assert skill.name == 'special_post'
    assert skill.version == '1.0.0'
    assert skill.description
    assert 'business_name' in skill.inputs
    assert 'item_name' in skill.inputs


def test_parse_frontmatter_without_block_returns_empty():
    assert parse_frontmatter('# no frontmatter here') == {}
    assert frontmatter_body('# hi') == '# hi'


def test_load_skill_name_mismatch_raises(tmp_path):
    bad = tmp_path / 'bad'
    (bad / 'x').mkdir(parents=True)
    (bad / 'SKILL.md').write_text('---\nname: other\n---\nbody\n', encoding='utf-8')
    with pytest.raises(ValueError):
        load_skill('bad', skills_root=str(tmp_path))


def test_load_skill_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_skill('does_not_exist')


def test_get_prompt_accepts_name_with_or_without_suffix():
    skill = load_skill('special_post')
    assert get_prompt(skill, 'caption') == get_prompt(skill, 'caption.md')
    with pytest.raises(KeyError):
        get_prompt(skill, 'nope')


def test_render_prompt_substitutes_and_leaves_unknown():
    out = render_prompt('Hello {{name}}, {{missing}}!', {'name': 'Jo'})
    assert out == 'Hello Jo, {{missing}}!'


def test_render_skill_prompt_includes_rules_and_variables():
    skill = load_skill('special_post')
    rendered = render_skill_prompt(skill, 'caption', {
        'business_name': 'Taco Libre', 'business_type': 'food truck',
        'location': 'Raleigh', 'item_name': 'Baja Tacos',
        'description': 'fresh', 'price': '$9', 'available_until': '8pm',
        'tone': 'hype', 'platform': 'instagram',
    })
    assert '{{' not in rendered
    assert 'Taco Libre' in rendered and 'Baja Tacos' in rendered
    assert 'Price honesty' in rendered  # rules appended


def test_render_skill_prompt_without_rules():
    skill = load_skill('special_post')
    rendered = render_skill_prompt(skill, 'caption', {'business_name': 'X'}, include_rules=False)
    assert 'Price honesty' not in rendered


def test_validate_skill_all_valid():
    for name, skill in load_all_skills().items():
        if name in EXPECTED_SKILLS:
            assert validate_skill(skill) == [], f'{name}: {validate_skill(skill)}'


def test_validate_skill_flags_undeclared_placeholder():
    skill = load_skill('brand_guard')
    skill.prompts['extra.md'] = 'Uses {{undeclared_var}} here.'
    problems = validate_skill(skill)
    assert any('undeclared_var' in p for p in problems)


def test_skill_manifest_shape():
    manifest = skill_manifest()
    by_name = {m['name']: m for m in manifest}
    for name in EXPECTED_SKILLS:
        assert name in by_name
        entry = by_name[name]
        assert entry['version'] and entry['description'] and entry['inputs']
        assert entry['prompts'] and entry['rules']


def test_no_llm_sdk_imports_in_skills_package():
    """Skills must stay provider-agnostic: no openai/anthropic imports."""
    banned = ('import openai', 'import anthropic', 'from openai', 'from anthropic')
    for root, _, files in os.walk(SKILLS_ROOT):
        for fname in files:
            if not fname.endswith('.py'):
                continue
            text = open(os.path.join(root, fname), encoding='utf-8').read()
            for pattern in banned:
                assert pattern not in text, f'{fname} contains {pattern}'
