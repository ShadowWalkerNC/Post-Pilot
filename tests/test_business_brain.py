"""tests/test_business_brain.py — unified business context.

Proves `load_context()` unifies identity, brand voice, menu/prices,
locations, hours, specials, events, media, prior posts, performance, and
constraints into one object, and that the context feeds the legacy
generators (and the canonical pipeline) unchanged.
"""

import time

import pytest

from core.business_brain.models import BusinessContext
from core.business_brain.service import load_context, load_context_from_dict
from core.content.pipeline import ContentPipeline, ContentRequest

TEST_UID = "00000000-0000-4000-8000-0000000000b1"


@pytest.fixture(autouse=True)
def _deterministic_legacy(monkeypatch):
    """Force legacy template fallback + adapter passthrough (no network)."""
    import modules.ai_generator as legacy_ai
    from modules.platform_adapter import PlatformAdapter

    monkeypatch.setattr(legacy_ai, "_generate_openai", lambda *a, **k: None)
    monkeypatch.setattr(PlatformAdapter, "_get_client", lambda self: None)


@pytest.fixture()
def seeded_user(app):
    """Seed user + profile + special + event + hours + post history."""
    now = int(time.time())
    with app.app_context():
        from modules.database import get_db

        db = get_db()
        db.execute(
            "INSERT OR REPLACE INTO users"
            " (id, email, full_name, business_name, subscription_tier, plan, is_active)"
            " VALUES (?, ?, ?, ?, ?, ?, 1)",
            (TEST_UID, "brain@test.dev", "Brain Owner", "Taco Thunder",
             "starter", "starter"),
        )
        db.execute(
            "INSERT OR REPLACE INTO business_profiles"
            " (user_id, name, business_type, location, hours, phone,"
            "  website_url, ai_tone, ai_keywords)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (TEST_UID, "Taco Thunder", "food_truck", "Raleigh",
             "11 AM - 8 PM", "555-0100", "https://tacothunder.test",
             "hype", "birria, tacos"),
        )
        db.execute("DELETE FROM specials WHERE user_id = ?", (TEST_UID,))
        db.execute("DELETE FROM events WHERE user_id = ?", (TEST_UID,))
        db.execute("DELETE FROM hours_overrides WHERE user_id = ?", (TEST_UID,))
        db.execute("DELETE FROM post_history WHERE user_id = ?", (TEST_UID,))
        db.execute(
            "INSERT INTO specials (user_id, item_name, description, post_date,"
            " post_time, content_type, tone, image_url, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (TEST_UID, "Birria Tacos", "slow-cooked, cheesy",
             "2026-10-02", "11:00", "daily_special", "hype",
             "https://cdn.test/birria.jpg", "pending"),
        )
        db.execute(
            "INSERT INTO events (user_id, title, description, event_date,"
            " post_date, post_time, event_type, tone, image_url, ticket_url, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (TEST_UID, "Taco Fest", "all-you-can-eat", "2026-10-10",
             "2026-10-02", "09:00", "festival", "hype",
             "https://cdn.test/fest.jpg", "https://tickets.test/fest", "pending"),
        )
        db.execute(
            "INSERT INTO hours_overrides (user_id, title, message,"
            " override_type, post_date, post_time, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (TEST_UID, "Closed Monday", "Private event",
             "closure", "2026-10-02", "08:00", "pending"),
        )
        db.execute(
            "INSERT INTO post_history (user_id, caption, content_type,"
            " image_url, video_url, platforms, results, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (TEST_UID, "Yesterday's post", "text",
             "https://cdn.test/old.jpg", None, '["fb"]', "{}", "published", now),
        )
        db.commit()
    return TEST_UID


# ---------------------------------------------------------------------------
# load_context()
# ---------------------------------------------------------------------------


def test_load_context_unifies_all_sections(seeded_user):
    ctx = load_context(seeded_user)
    assert isinstance(ctx, BusinessContext)

    # identity
    assert ctx.identity.business_name == "Taco Thunder"
    assert ctx.identity.business_type == "food_truck"
    assert ctx.identity.email == "brain@test.dev"
    assert ctx.identity.phone == "555-0100"
    assert ctx.identity.plan == "starter"

    # brand voice
    assert ctx.brand_voice.tone == "hype"
    assert ctx.brand_voice.keywords == ["birria", "tacos"]

    # locations + hours
    assert ctx.locations and ctx.locations[0].label == "Raleigh"
    assert ctx.hours.regular == "11 AM - 8 PM"
    assert len(ctx.hours.overrides) == 1
    assert ctx.hours.overrides[0]["title"] == "Closed Monday"

    # specials + events
    assert len(ctx.specials) == 1
    assert ctx.specials[0].item_name == "Birria Tacos"
    assert len(ctx.events) == 1
    assert ctx.events[0].title == "Taco Fest"
    assert ctx.events[0].ticket_url == "https://tickets.test/fest"

    # media unified from specials + events + post_history
    urls = {m.url for m in ctx.media}
    assert urls == {
        "https://cdn.test/birria.jpg",
        "https://cdn.test/fest.jpg",
        "https://cdn.test/old.jpg",
    }

    # prior posts + performance
    assert len(ctx.prior_posts) == 1
    assert ctx.prior_posts[0].caption == "Yesterday's post"
    assert ctx.performance.total_posts == 1
    assert ctx.performance.posts_this_month >= 1

    # constraints follow the starter plan
    assert ctx.constraints.plan == "starter"
    assert ctx.constraints.ai_captions_limit == 30
    assert "ig" in ctx.constraints.allowed_platforms


def test_load_context_unknown_user_returns_defaults():
    ctx = load_context("00000000-0000-4000-8000-ffffffffffff")
    assert isinstance(ctx, BusinessContext)
    assert ctx.identity.business_name == "Our Business"
    assert ctx.specials == []
    assert ctx.events == []
    assert ctx.prior_posts == []
    assert ctx.constraints.plan == "free"
    assert ctx.constraints.allowed_platforms == ["fb", "web"]


def test_load_context_from_dict_no_db():
    ctx = load_context_from_dict(
        {
            "business_name": "Noodle Nest",
            "business_type": "restaurant",
            "location": "Durham",
            "hours": "9 AM - 9 PM",
            "special": "Ramen Bowl",
            "tone": "funny",
            "keywords": "ramen, spicy",
            "hashtags": ["#durhameats"],
            "menu": [{"name": "Ramen Bowl", "price": "$12"}],
            "plan": "pro",
        }
    )
    assert ctx.identity.business_name == "Noodle Nest"
    assert ctx.brand_voice.tone == "funny"
    assert ctx.brand_voice.keywords == ["ramen", "spicy"]
    assert ctx.menu[0].price == "$12"
    assert ctx.specials[0].item_name == "Ramen Bowl"
    assert ctx.constraints.plan == "pro"
    assert ctx.constraints.ai_captions_limit == 999999


def test_constraints_free_vs_paid():
    free = load_context_from_dict({"name": "X"})
    assert free.constraints.allowed_platforms == ["fb", "web"]
    assert free.constraints.ai_captions_limit == 5

    agency = load_context_from_dict({"name": "X", "plan": "agency"})
    assert "ig" in agency.constraints.allowed_platforms
    assert agency.constraints.ai_captions_limit == 999999


# ---------------------------------------------------------------------------
# Context -> legacy generators (parity)
# ---------------------------------------------------------------------------


def test_context_business_info_feeds_legacy_generator(seeded_user):
    from modules.ai_generator import generate_caption, generate_with_adaptations

    ctx = load_context(seeded_user)
    info = ctx.to_business_info()
    assert info == {
        "name": "Taco Thunder",
        "type": "food_truck",
        "location": "Raleigh",
        "hours": "11 AM - 8 PM",
        "special": "Birria Tacos",
        "city": "Raleigh",
    }

    caption = generate_caption(
        business_info=info,
        content_type="daily_special",
        tone="hype",
        platform="facebook",
    )
    assert "Birria Tacos" in caption

    multi = generate_with_adaptations(
        business_info=info,
        content_type="daily_special",
        tone="hype",
        platforms=["fb", "ig"],
    )
    assert "Birria Tacos" in multi["master"]
    assert set(multi["adapted"]) == {"fb", "ig"}

    template_info = ctx.to_template_info()
    assert template_info["business_name"] == "Taco Thunder"
    assert template_info["special_item"] == "Birria Tacos"


def test_pipeline_consumes_loaded_context(seeded_user):
    ctx = load_context(seeded_user)
    result = ContentPipeline().run(
        ContentRequest(
            business_info={},
            content_type="daily_special",
            tone="",
            keywords=[],
            platforms=["fb", "ig"],
            context=ctx,
        )
    )
    # Tone/keywords fall back to the brain; business facts flow to legacy.
    assert "Birria Tacos" in result.master
    assert set(result.adapted) == {"fb", "ig"}
    assert result.stages_run == [
        "context",
        "generate",
        "adapt",
        "score",
        "validate",
        "assemble",
    ]


def test_pipeline_loads_context_from_user_id(seeded_user):
    result = ContentPipeline().run(
        ContentRequest(
            business_info={},
            content_type="daily_special",
            tone="friendly",
            keywords=[],
            platforms=["fb"],
            user_id=seeded_user,
        )
    )
    assert isinstance(result.context, BusinessContext)
    assert result.context.identity.business_name == "Taco Thunder"
    assert "Birria Tacos" in result.master
