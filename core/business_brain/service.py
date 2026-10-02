"""core.business_brain.service — build the unified BusinessContext.

`load_context(user_id)` is the single reader all content code and agents use.
It pulls from the existing tables via the existing managers (`UserManager`,
`modules.database.get_db`) and never changes stored data.

Every section degrades to a safe default when its table/row is missing, so
callers always get a usable context object — never an exception for a
missing optional table.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.business_brain.models import (
    BrandVoice,
    BusinessContext,
    Constraints,
    EventItem,
    HoursInfo,
    Identity,
    Location,
    MediaAsset,
    MenuItem,
    PerformanceSummary,
    PriorPost,
    SpecialItem,
)

logger = logging.getLogger(__name__)

_PLAN_CAPTION_LIMITS = {"free": 5, "starter": 30, "pro": 999999, "agency": 999999}


def load_context(user_id: str) -> BusinessContext:
    """Load the full unified context for a user.

    Args:
        user_id: users.id / business_profiles.user_id.

    Returns:
        BusinessContext with every section populated (or safely defaulted).
        Unknown users get defaults; this function does not raise for
        missing rows or missing optional tables.
    """
    uid = str(user_id or "")
    ctx = BusinessContext()
    ctx.identity.user_id = uid

    _load_identity_and_brand(ctx, uid)
    _load_specials(ctx, uid)
    _load_events(ctx, uid)
    _load_hours(ctx, uid)
    _load_prior_posts_and_media(ctx, uid)
    _load_performance(ctx, uid)
    _load_constraints(ctx)
    return ctx


def load_context_from_dict(data: Dict[str, Any]) -> BusinessContext:
    """Build a BusinessContext from a plain dict (no DB).

    Accepts legacy-shaped keys (`business_name`/`name`, `business_type`/
    `type`, `location`, `hours`, `special`/`special_item`, `tone`/
    `ai_tone`, `keywords`/`ai_keywords`, `hashtags`, `menu`, `email`,
    `phone`, `website_url`, `plan`). Useful for callers without a user row
    (Flask-less scripts, previews) and for tests.
    """
    data = dict(data or {})
    name = str(data.get("business_name") or data.get("name") or "Our Business")
    btype = str(data.get("business_type") or data.get("type") or "restaurant")
    location = str(data.get("location") or "")
    hours = str(data.get("hours") or "")
    tone = str(data.get("tone") or data.get("ai_tone") or "friendly")
    keywords = _split_keywords(data.get("keywords") or data.get("ai_keywords") or "")
    hashtags = list(data.get("hashtags") or [])
    email = str(data.get("email") or "")
    phone = str(data.get("phone") or "")
    website_url = str(data.get("website_url") or "")
    plan = str(data.get("plan") or "free")

    menu: List[MenuItem] = []
    for item in data.get("menu") or []:
        if isinstance(item, dict):
            menu.append(
                MenuItem(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    price=item.get("price"),
                )
            )
        else:
            menu.append(MenuItem(name=str(item)))

    specials: List[SpecialItem] = []
    special_name = str(data.get("special") or data.get("special_item") or "")
    if special_name:
        specials.append(SpecialItem(item_name=special_name))

    locations = [Location(label=location)] if location else []

    ctx = BusinessContext(
        identity=Identity(
            user_id=str(data.get("user_id") or ""),
            business_name=name,
            business_type=btype,
            email=email,
            phone=phone,
            website_url=website_url,
            plan=plan,
        ),
        brand_voice=BrandVoice(tone=tone, keywords=keywords, hashtags=hashtags),
        menu=menu,
        locations=locations,
        hours=HoursInfo(regular=hours),
        specials=specials,
    )
    _load_constraints(ctx)
    return ctx


# ---------------------------------------------------------------------------
# Section loaders (each is best-effort; failures leave defaults in place)
# ---------------------------------------------------------------------------


def _load_identity_and_brand(ctx: BusinessContext, uid: str) -> None:
    try:
        from modules.user_manager import UserManager

        user = UserManager.get_user(uid)
        profile = UserManager.get_business_profile(uid)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("business_brain: identity load failed for %s: %s", uid, exc)
        return

    if user is not None:
        ctx.identity.email = getattr(user, "email", "") or ""
        ctx.identity.plan = getattr(user, "plan", "free") or "free"
        if getattr(user, "business_name", ""):
            ctx.identity.business_name = user.business_name
    if profile:
        ctx.identity.business_name = (
            profile.get("name") or ctx.identity.business_name
        )
        ctx.identity.business_type = (
            profile.get("business_type") or ctx.identity.business_type
        )
        ctx.identity.phone = profile.get("phone") or ""
        ctx.identity.website_url = profile.get("website_url") or ""
        ctx.brand_voice.tone = profile.get("ai_tone") or ctx.brand_voice.tone
        ctx.brand_voice.keywords = _split_keywords(profile.get("ai_keywords") or "")
        ctx.hours.regular = profile.get("hours") or ""
        label = profile.get("location") or profile.get("address") or ""
        if label:
            ctx.locations.append(
                Location(
                    label=label,
                    address=profile.get("address") or "",
                    lat=profile.get("lat"),
                    lng=profile.get("lng"),
                )
            )


def _load_specials(ctx: BusinessContext, uid: str) -> None:
    rows = _select(
        "SELECT id, item_name, description, post_date, post_time, content_type,"
        " tone, image_url, status FROM specials WHERE user_id = ?"
        " ORDER BY post_date DESC, post_time DESC LIMIT 20",
        (uid,),
    )
    for row in rows:
        ctx.specials.append(
            SpecialItem(
                id=row.get("id"),
                item_name=row.get("item_name") or "",
                description=row.get("description") or "",
                post_date=str(row.get("post_date") or ""),
                post_time=str(row.get("post_time") or ""),
                content_type=row.get("content_type") or "daily_special",
                tone=row.get("tone") or "",
                image_url=row.get("image_url"),
                status=row.get("status") or "pending",
            )
        )
        if row.get("image_url"):
            ctx.media.append(
                MediaAsset(url=row["image_url"], kind="image", source="specials")
            )


def _load_events(ctx: BusinessContext, uid: str) -> None:
    rows = _select(
        "SELECT id, title, description, event_date, post_date, post_time,"
        " event_type, tone, image_url, ticket_url, status FROM events"
        " WHERE user_id = ? ORDER BY event_date DESC LIMIT 20",
        (uid,),
    )
    for row in rows:
        ctx.events.append(
            EventItem(
                id=row.get("id"),
                title=row.get("title") or "",
                description=row.get("description") or "",
                event_date=str(row.get("event_date") or ""),
                post_date=str(row.get("post_date") or ""),
                post_time=str(row.get("post_time") or ""),
                event_type=row.get("event_type") or "event",
                tone=row.get("tone") or "",
                image_url=row.get("image_url"),
                ticket_url=row.get("ticket_url"),
                status=row.get("status") or "pending",
            )
        )
        if row.get("image_url"):
            ctx.media.append(
                MediaAsset(url=row["image_url"], kind="image", source="events")
            )


def _load_hours(ctx: BusinessContext, uid: str) -> None:
    rows = _select(
        "SELECT id, title, message, override_type, post_date, post_time, status"
        " FROM hours_overrides WHERE user_id = ?"
        " ORDER BY post_date DESC LIMIT 20",
        (uid,),
    )
    for row in rows:
        ctx.hours.overrides.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or "",
                "message": row.get("message") or "",
                "override_type": row.get("override_type") or "",
                "post_date": str(row.get("post_date") or ""),
                "post_time": str(row.get("post_time") or ""),
                "status": row.get("status") or "pending",
            }
        )


def _load_prior_posts_and_media(ctx: BusinessContext, uid: str) -> None:
    try:
        from modules.user_manager import UserManager

        posts = UserManager.get_post_history(uid, limit=20)
    except Exception as exc:
        logger.warning("business_brain: post history load failed: %s", exc)
        return
    for post in posts or []:
        ctx.prior_posts.append(
            PriorPost(
                id=post.get("id"),
                caption=post.get("caption") or "",
                content_type=post.get("content_type") or "text",
                status=post.get("status") or "",
                created_at=post.get("created_at"),
            )
        )
        if post.get("image_url"):
            ctx.media.append(
                MediaAsset(url=post["image_url"], kind="image", source="post_history")
            )
        if post.get("video_url"):
            ctx.media.append(
                MediaAsset(url=post["video_url"], kind="video", source="post_history")
            )


def _load_performance(ctx: BusinessContext, uid: str) -> None:
    try:
        from modules.user_manager import UserManager

        posts_this_month = UserManager.count_posts_this_month(uid)
    except Exception as exc:
        logger.warning("business_brain: performance load failed: %s", exc)
        posts_this_month = 0
    total = len(ctx.prior_posts)
    last_at: Optional[int] = None
    for post in ctx.prior_posts:
        if post.created_at and (last_at is None or post.created_at > last_at):
            try:
                last_at = int(post.created_at)
            except (TypeError, ValueError):
                continue
    ctx.performance = PerformanceSummary(
        total_posts=total,
        posts_this_month=posts_this_month,
        last_post_at=last_at,
    )


def _load_constraints(ctx: BusinessContext) -> None:
    plan = (ctx.identity.plan or "free").strip().lower()
    if plan == "free":
        allowed = ["fb", "web"]
    else:
        allowed = ["fb", "ig", "tt", "yt", "yts", "li", "tw", "pi", "gb", "web"]
    ctx.constraints = Constraints(
        plan=plan,
        ai_captions_limit=_PLAN_CAPTION_LIMITS.get(plan, 5),
        allowed_platforms=allowed,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _select(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Best-effort SELECT returning a list of dicts (empty on any failure)."""
    try:
        from modules.database import get_db

        cur = get_db().execute(sql, params)
        rows = cur.fetchall()
    except Exception as exc:
        logger.warning("business_brain: query failed (%s...): %s", sql[:60], exc)
        return []
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        try:
            out.append(dict(row))
        except Exception:
            continue
    return out


def _split_keywords(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(k).strip() for k in raw if str(k).strip()]
    if isinstance(raw, str):
        return [k.strip() for k in raw.split(",") if k.strip()]
    return []
