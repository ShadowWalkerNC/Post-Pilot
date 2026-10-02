"""
skills/loader.py — Provider-agnostic skill loader for Post-Pilot.

A "skill" is a directory under skills/ containing:
    SKILL.md          frontmatter (name, version, description, inputs) + markdown docs
    prompts/*.md      provider-agnostic prompt templates ({{variable}} placeholders)
    rules/*.md        guardrail / style rules as plain markdown

Design constraints:
- stdlib only; NEVER import an LLM SDK (openai, anthropic, etc.).
- Prompts are rendered to plain strings via render_prompt(); the caller
  decides which provider sends them (OpenAI, Anthropic, template fallback).
- Frontmatter is parsed with a minimal hand parser (no PyYAML dependency).
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SKILLS_ROOT = os.path.dirname(os.path.abspath(__file__))

# Names every skill directory must avoid colliding with (loader internals)
RESERVED_NAMES = {'__pycache__'}

FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_]+)\s*\}\}')


@dataclass
class Skill:
    """In-memory representation of one skill directory."""
    name: str
    version: str = '0.1.0'
    description: str = ''
    inputs: List[str] = field(default_factory=list)
    path: str = ''
    body: str = ''                      # SKILL.md markdown below frontmatter
    prompts: Dict[str, str] = field(default_factory=dict)  # filename -> template text
    rules: Dict[str, str] = field(default_factory=dict)    # filename -> rule text


def parse_frontmatter(text: str) -> Dict[str, str]:
    """Parse minimal `key: value` frontmatter. Lists via `[a, b]` or `a, b`."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    out: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        out[key.strip()] = value.strip().strip('"\'')
    return out


def frontmatter_body(text: str) -> str:
    """Return the markdown below the frontmatter block (or full text)."""
    match = FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


def _read_text_files(directory: str) -> Dict[str, str]:
    """Read all *.md files in a directory into {filename: content}."""
    out: Dict[str, str] = {}
    if not os.path.isdir(directory):
        return out
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(directory, fname)
        if not os.path.isfile(fpath):
            continue
        with open(fpath, encoding='utf-8') as fh:
            out[fname] = fh.read()
    return out


def list_skills(skills_root: str = SKILLS_ROOT) -> List[str]:
    """Return sorted names of skill directories (those containing SKILL.md)."""
    names: List[str] = []
    if not os.path.isdir(skills_root):
        return names
    for entry in sorted(os.listdir(skills_root)):
        if entry in RESERVED_NAMES or entry.startswith('.'):
            continue
        skill_dir = os.path.join(skills_root, entry)
        if os.path.isdir(skill_dir) and os.path.isfile(
            os.path.join(skill_dir, 'SKILL.md')
        ):
            names.append(entry)
    return names


def load_skill(name: str, skills_root: str = SKILLS_ROOT) -> Skill:
    """Load a skill by directory name. Raises FileNotFoundError / ValueError."""
    skill_dir = os.path.join(skills_root, name)
    skill_md = os.path.join(skill_dir, 'SKILL.md')
    if not os.path.isfile(skill_md):
        raise FileNotFoundError(f"Skill '{name}' not found (no SKILL.md in {skill_dir})")
    with open(skill_md, encoding='utf-8') as fh:
        raw = fh.read()
    meta = parse_frontmatter(raw)
    if 'name' in meta and meta['name'] != name:
        raise ValueError(
            f"Skill directory '{name}' declares name '{meta['name']}' — mismatch"
        )
    raw_inputs = meta.get('inputs', '')
    inputs = [i.strip().strip('"\'') for i in raw_inputs.strip('[]').split(',') if i.strip()]
    return Skill(
        name=name,
        version=meta.get('version', '0.1.0'),
        description=meta.get('description', ''),
        inputs=inputs,
        path=skill_dir,
        body=frontmatter_body(raw),
        prompts=_read_text_files(os.path.join(skill_dir, 'prompts')),
        rules=_read_text_files(os.path.join(skill_dir, 'rules')),
    )


def load_all_skills(skills_root: str = SKILLS_ROOT) -> Dict[str, Skill]:
    """Load every discoverable skill into {name: Skill}."""
    return {name: load_skill(name, skills_root) for name in list_skills(skills_root)}


def get_prompt(skill: Skill, prompt_name: str) -> str:
    """Return a prompt template by name (with or without .md suffix)."""
    key = prompt_name if prompt_name.endswith('.md') else prompt_name + '.md'
    if key not in skill.prompts:
        raise KeyError(f"Skill '{skill.name}' has no prompt '{prompt_name}'")
    return skill.prompts[key]


def render_prompt(template: str, variables: Dict[str, str]) -> str:
    """Substitute {{variable}} placeholders. Unknown placeholders are left intact."""

    def _sub(match: 're.Match') -> str:
        key = match.group(1)
        return str(variables[key]) if key in variables else match.group(0)

    return PLACEHOLDER_RE.sub(_sub, template)


def render_skill_prompt(
    skill: Skill,
    prompt_name: str,
    variables: Dict[str, str],
    include_rules: bool = True,
) -> str:
    """Render a skill prompt with variables, optionally appending rule blocks."""
    rendered = render_prompt(get_prompt(skill, prompt_name), variables)
    if include_rules and skill.rules:
        rules_block = '\n\n'.join(
            f'## Rule: {fname}\n{text.strip()}'
            for fname, text in sorted(skill.rules.items())
        )
        rendered = f'{rendered.strip()}\n\n---\n\n{rules_block}'
    return rendered


def validate_skill(skill: Skill) -> List[str]:
    """Return a list of problems (empty = valid)."""
    problems: List[str] = []
    if not skill.description:
        problems.append('missing description in frontmatter')
    if not skill.prompts:
        problems.append('no prompts/*.md files')
    if not skill.rules:
        problems.append('no rules/*.md files')
    declared = set(skill.inputs)
    used: set = set()
    for template in skill.prompts.values():
        used.update(PLACEHOLDER_RE.findall(template))
    for var in sorted(used - declared):
        problems.append(f"placeholder '{{{{{var}}}}}' used but not declared in inputs")
    return problems


def skill_manifest(skills_root: str = SKILLS_ROOT) -> List[Dict]:
    """Lightweight manifest for APIs/registries: name, version, description, inputs."""
    manifest = []
    for name in list_skills(skills_root):
        skill = load_skill(name, skills_root)
        manifest.append({
            'name': skill.name,
            'version': skill.version,
            'description': skill.description,
            'inputs': skill.inputs,
            'prompts': sorted(skill.prompts),
            'rules': sorted(skill.rules),
        })
    return manifest
