"""core.business_brain.models — unified business context data model.

One typed place for everything content generation and agents need to know
about a business: identity, brand voice, menu/prices, locations, hours,
specials, events, media, prior posts, performance, and constraints.

Plain dataclasses with no I/O. Loading lives in
`core.business_brain.service.load_context()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Identity:
    """Who the business is."""

    user_id: str = ""
    business_name: str = "Our Business"
    business_type: str = "restaurant"
    email: str = ""
    phone: str = ""
    website_url: str = ""
    plan: str = "free"


@dataclass
class BrandVoice:
    """How the business sounds."""

    tone: str = "friendly"
    keywords: List[str] = field(default_factory=list)
    hashtags: List[str] = field(default_factory=list)


@dataclass
class MenuItem:
    """A menu item with optional price."""

    name: str = ""
    description: str = ""
    price: Optional[str] = None


@dataclass
class Location:
    """A place the business operates from."""

    label: str = ""
    address: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None


@dataclass
class HoursInfo:
    """Regular hours plus dated overrides/closures."""

    regular: str = ""
    overrides: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SpecialItem:
    """A scheduled special (row from `specials`)."""

    id: Optional[int] = None
    item_name: str = ""
    description: str = ""
    post_date: str = ""
    post_time: str = ""
    content_type: str = "daily_special"
    tone: str = ""
    image_url: Optional[str] = None
    status: str = "pending"


@dataclass
class EventItem:
    """A scheduled event promo (row from `events`)."""

    id: Optional[int] = None
    title: str = ""
    description: str = ""
    event_date: str = ""
    post_date: str = ""
    post_time: str = ""
    event_type: str = "event"
    tone: str = ""
    image_url: Optional[str] = None
    ticket_url: Optional[str] = None
    status: str = "pending"


@dataclass
class MediaAsset:
    """A reusable image/video URL with its source."""

    url: str = ""
    kind: str = "image"  # 'image' | 'video'
    source: str = ""  # e.g. 'specials', 'events', 'post_history'


@dataclass
class PriorPost:
    """A previously generated/published post (row from `post_history`)."""

    id: Optional[int] = None
    caption: str = ""
    content_type: str = "text"
    status: str = ""
    created_at: Optional[int] = None


@dataclass
class PerformanceSummary:
    """Cheap engagement/posting stats for prompt context."""

    total_posts: int = 0
    posts_this_month: int = 0
    last_post_at: Optional[int] = None


@dataclass
class Constraints:
    """Plan/entitlement limits content generation must respect."""

    plan: str = "free"
    ai_captions_limit: int = 5
    allowed_platforms: List[str] = field(default_factory=list)


@dataclass
class BusinessContext:
    """The single context object all content code and agents read."""

    identity: Identity = field(default_factory=Identity)
    brand_voice: BrandVoice = field(default_factory=BrandVoice)
    menu: List[MenuItem] = field(default_factory=list)
    locations: List[Location] = field(default_factory=list)
    hours: HoursInfo = field(default_factory=HoursInfo)
    specials: List[SpecialItem] = field(default_factory=list)
    events: List[EventItem] = field(default_factory=list)
    media: List[MediaAsset] = field(default_factory=list)
    prior_posts: List[PriorPost] = field(default_factory=list)
    performance: PerformanceSummary = field(default_factory=PerformanceSummary)
    constraints: Constraints = field(default_factory=Constraints)

    # -- Legacy adapters --------------------------------------------------
    # These map the unified context onto the exact dict shapes the legacy
    # `modules/*` generators already accept, so core can delegate to them
    # without changing their signatures.

    def to_business_info(self) -> Dict[str, Any]:
        """Legacy `business_info` dict for `modules.ai_generator` functions.

        Keys: name, type, location, hours, special (+ city when known).
        """
        location = self.locations[0].label if self.locations else ""
        special = self.specials[0].item_name if self.specials else ""
        info: Dict[str, Any] = {
            "name": self.identity.business_name,
            "type": self.identity.business_type,
            "location": location,
            "hours": self.hours.regular,
            "special": special,
        }
        if location and "," not in location:
            info["city"] = location
        return info

    def to_template_info(self) -> Dict[str, Any]:
        """Legacy `info` dict for `SocialMediaPostGenerator.setup_business()`.

        Keys: business_type, business_name, location, hours, city,
        special_item, hashtags.
        """
        location = self.locations[0].label if self.locations else ""
        return {
            "business_type": self.identity.business_type,
            "business_name": self.identity.business_name,
            "location": location or "Downtown",
            "hours": self.hours.regular or "11 AM - 8 PM",
            "city": location or "My City",
            "special_item": (
                self.specials[0].item_name if self.specials else "Today's Special"
            ),
            "hashtags": list(self.brand_voice.hashtags),
        }
