"""tests/test_content_pipeline.py — canonical pipeline delegates to legacy.

Proves legacy outputs still flow through `core.content.pipeline` unchanged:
master/adapted captions equal the legacy `generate_with_adaptations`
output, template posts equal the legacy `SocialMediaPostGenerator` output.

Legacy OpenAI calls are stubbed (template fallback + master passthrough)
so these tests are deterministic and offline.
"""

import pathlib

import pytest

from core.business_brain.service import load_context_from_dict
from core.content.pipeline import (
    PIPELINE_STAGES,
    ContentPipeline,
    ContentRequest,
    ContentResult,
    generate_content,
)

BUSINESS_INFO = {
    "name": "Taco Thunder",
    "type": "food_truck",
    "location": "Raleigh",
    "hours": "11 AM - 8 PM",
    "special": "Birria Tacos",
}

PLATFORMS = ["fb", "ig", "tt"]


@pytest.fixture(autouse=True)
def _deterministic_legacy(monkeypatch):
    """Force legacy template fallback + adapter passthrough (no network)."""
    import modules.ai_generator as legacy_ai
    from modules.platform_adapter import PlatformAdapter

    monkeypatch.setattr(legacy_ai, "_generate_openai", lambda *a, **k: None)
    monkeypatch.setattr(PlatformAdapter, "_get_client", lambda self: None)


def _request(**overrides):
    base = {
        "business_info": dict(BUSINESS_INFO),
        "content_type": "daily_special",
        "tone": "friendly",
        "keywords": [],
        "platforms": list(PLATFORMS),
    }
    base.update(overrides)
    return ContentRequest(**base)


# ---------------------------------------------------------------------------
# Legacy parity: AI path
# ---------------------------------------------------------------------------


def test_pipeline_master_matches_legacy():
    """Pipeline master caption equals the legacy generator output."""
    from modules.ai_generator import generate_with_adaptations

    legacy = generate_with_adaptations(
        business_info=dict(BUSINESS_INFO),
        content_type="daily_special",
        tone="friendly",
        keywords=[],
        platforms=list(PLATFORMS),
    )
    result = ContentPipeline().run(_request())

    assert isinstance(result, ContentResult)
    assert result.master == legacy["master"]
    assert result.adapted == legacy["adapted"]
    assert result.legacy["ai_generator"] == legacy
    assert "Taco Thunder" in result.master or "Birria Tacos" in result.master


def test_pipeline_runs_all_canonical_stages():
    result = ContentPipeline().run(_request())
    assert result.stages_run == PIPELINE_STAGES
    assert PIPELINE_STAGES == [
        "context",
        "generate",
        "adapt",
        "score",
        "validate",
        "assemble",
    ]


def test_pipeline_scores_every_platform_with_legacy_scorer():
    from modules.ai_generator import calculate_engagement_score

    result = ContentPipeline().run(_request())

    assert set(result.scores) == set(PLATFORMS)
    for key in PLATFORMS:
        expected = calculate_engagement_score(
            result.adapted[key], platform=key, content_type="daily_special"
        )
        assert result.scores[key] == expected
        assert 10 <= result.scores[key]["score"] <= 100


def test_pipeline_validation_delegates_to_legacy_validator():
    from modules.validator import validate_post_input

    result = ContentPipeline().run(_request(platforms=["fb"]))

    ok, errors = result.validation
    expected_ok, expected_errors = validate_post_input(
        caption=result.master, content_type="promo", platforms=["fb"]
    )
    assert ok == expected_ok
    assert errors == expected_errors
    assert ok is True  # fb-only master caption passes cleanly


def test_generate_content_convenience_wrapper():
    result = generate_content(
        business_info=dict(BUSINESS_INFO),
        content_type="daily_special",
        tone="friendly",
        platforms=["fb", "ig"],
    )
    assert isinstance(result, ContentResult)
    assert result.master
    assert set(result.adapted) == {"fb", "ig"}
    assert result.stages_run == PIPELINE_STAGES


# ---------------------------------------------------------------------------
# Legacy parity: template path
# ---------------------------------------------------------------------------


def test_template_path_matches_legacy_generator():
    from modules.post_generator import SocialMediaPostGenerator

    legacy_gen = SocialMediaPostGenerator()
    legacy_gen.setup_business(
        {
            "business_type": "food_truck",
            "business_name": "Taco Thunder",
            "location": "Raleigh",
            "hours": "11 AM - 8 PM",
            "city": "Raleigh",
            "special_item": "Birria Tacos",
            "hashtags": [],
        }
    )
    expected = legacy_gen.generate_post("instagram_location", day="Monday", date="June 02")

    got = ContentPipeline().run_template(
        "instagram_location", dict(BUSINESS_INFO), day="Monday", date="June 02"
    )
    assert got == expected
    assert "Taco Thunder" not in got["caption"]  # location template has no name...
    assert "Raleigh" in got["caption"]  # ...but carries location + hours
    assert "11 AM - 8 PM" in got["caption"]


def test_template_output_exposed_via_request():
    result = ContentPipeline().run(_request(template="instagram_menu"))
    assert "template_post" in result.legacy
    assert "Birria Tacos" in result.legacy["template_post"]["caption"]


# ---------------------------------------------------------------------------
# Business brain wiring
# ---------------------------------------------------------------------------


def test_pipeline_builds_context_from_business_info():
    ctx = load_context_from_dict(dict(BUSINESS_INFO))
    result = ContentPipeline().run(
        ContentRequest(
            business_info={},
            content_type="daily_special",
            tone="",
            keywords=[],
            platforms=["fb"],
            context=ctx,
        )
    )
    # Empty business_info + empty tone fall back to the brain context.
    assert result.context is ctx
    assert "Birria Tacos" in result.master or "Taco Thunder" in result.master


# ---------------------------------------------------------------------------
# No duplicated prompt logic in core
# ---------------------------------------------------------------------------


def test_core_defines_no_prompt_or_template_logic():
    """Guard: core must delegate, never copy legacy prompts/templates."""
    core_dir = pathlib.Path(__file__).resolve().parent.parent / "core"
    sources = [p.read_text(encoding="utf-8") for p in core_dir.rglob("*.py")]
    blob = "\n".join(sources)
    for banned in (
        "TONE_PROMPTS",
        "PLATFORM_STYLES",
        "PLATFORM_RULES",
        "MASTER_STYLE",
        "TEMPLATES =",
        "You write energetic",
        "Write a clear, engaging, platform-neutral",
    ):
        assert banned not in blob, f"core/ must not contain {banned!r}"
