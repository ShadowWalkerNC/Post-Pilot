"""core.content.pipeline — the ONE canonical content pipeline.

Stages (see PIPELINE_STAGES):
  1. context  — resolve a BusinessContext (business brain) for the request.
  2. generate — master caption via legacy `modules.ai_generator`.
  3. adapt    — per-platform versions via legacy `PlatformAdapter`.
  4. score    — engagement scores via legacy `calculate_engagement_score`.
  5. validate — input checks via legacy `modules.validator`.
  6. assemble — pack the ContentResult.

This module contains NO prompt text, NO templates, and NO per-platform
prompt rules: every stage imports and calls the existing legacy functions.
Legacy modules stay untouched and keep working exactly as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PIPELINE_STAGES: List[str] = [
    "context",
    "generate",
    "adapt",
    "score",
    "validate",
    "assemble",
]

_DEFAULT_PLATFORMS: List[str] = ["fb", "ig", "tt", "yt", "yts", "tw", "gb", "web"]

# Legacy ai_generator content types -> validator content types.
_VALIDATOR_CONTENT_TYPES = {"text", "image", "video", "promo", "update"}


@dataclass
class ContentRequest:
    """Input to the canonical pipeline."""

    business_info: Dict[str, Any] = field(default_factory=dict)
    content_type: str = "general"
    tone: str = "friendly"
    keywords: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    user_id: str = ""
    # Optional pre-loaded context; when omitted the pipeline loads one via
    # the business brain (from user_id, else from business_info).
    context: Any = None
    # Optional legacy template path (e.g. 'instagram_location'). When set,
    # the pipeline ALSO runs the legacy SocialMediaPostGenerator and exposes
    # its output as result.legacy['template_post'].
    template: str = ""


@dataclass
class ContentResult:
    """Output of the canonical pipeline."""

    master: str = ""
    adapted: Dict[str, str] = field(default_factory=dict)
    scores: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    validation: Tuple[bool, List[str]] = (True, [])
    stages_run: List[str] = field(default_factory=list)
    # Raw legacy outputs for provenance/debugging:
    # {'ai_generator': {...}, 'template_post': {...}} (keys present only
    # for the paths that ran).
    legacy: Dict[str, Any] = field(default_factory=dict)
    context: Any = None


class ContentPipeline:
    """Canonical stages pipeline delegating to legacy generator logic."""

    def __init__(self, platforms: Optional[List[str]] = None):
        self.default_platforms = list(platforms) if platforms else list(
            _DEFAULT_PLATFORMS
        )

    # -- Main entry point -------------------------------------------------

    def run(self, request: ContentRequest) -> ContentResult:
        """Run all pipeline stages and return the assembled result."""
        result = ContentResult()
        stages: List[str] = []

        # Stage 1: context -------------------------------------------
        context = self._resolve_context(request)
        result.context = context
        stages.append("context")

        business_info = dict(request.business_info or {})
        if not business_info and context is not None:
            business_info = context.to_business_info()
        tone = request.tone or getattr(
            getattr(context, "brand_voice", None), "tone", "friendly"
        )
        keywords = list(request.keywords or [])
        if not keywords and context is not None:
            keywords = list(getattr(context.brand_voice, "keywords", []) or [])
        platforms = list(request.platforms) if request.platforms else list(
            self.default_platforms
        )

        # Stages 2+3: generate + adapt (single legacy call) -----------
        # generate_with_adaptations() IS the legacy master+adapt flow
        # (master caption, then PlatformAdapter.adapt_all in parallel).
        from modules.ai_generator import generate_with_adaptations

        legacy_out = generate_with_adaptations(
            business_info=business_info,
            content_type=request.content_type or "general",
            tone=tone or "friendly",
            keywords=keywords,
            platforms=platforms,
        )
        result.master = legacy_out.get("master", "")
        result.adapted = dict(legacy_out.get("adapted", {}))
        result.legacy["ai_generator"] = legacy_out
        stages.append("generate")
        stages.append("adapt")

        # Optional legacy template path (provenance, not a replacement) --
        if request.template:
            result.legacy["template_post"] = self.run_template(
                request.template, business_info
            )

        # Stage 4: score ----------------------------------------------
        from modules.ai_generator import calculate_engagement_score

        scores: Dict[str, Dict[str, Any]] = {}
        for key, caption in result.adapted.items():
            try:
                scores[key] = calculate_engagement_score(
                    caption,
                    platform=key,
                    content_type=request.content_type or "general",
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("pipeline: scoring failed for %s: %s", key, exc)
        result.scores = scores
        stages.append("score")

        # Stage 5: validate --------------------------------------------
        from modules.validator import validate_post_input

        validator_content_type = self._validator_content_type(
            request.content_type or "general"
        )
        ok, errors = validate_post_input(
            caption=result.master,
            content_type=validator_content_type,
            platforms=platforms,
        )
        result.validation = (ok, list(errors))
        stages.append("validate")

        # Stage 6: assemble ---------------------------------------------
        stages.append("assemble")
        result.stages_run = stages
        return result

    # -- Legacy template path ---------------------------------------------

    def run_template(
        self,
        template: str,
        business_info: Dict[str, Any],
        day: Optional[str] = None,
        date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the legacy SocialMediaPostGenerator for one template.

        Delegates to `modules.post_generator` (the canonical legacy home
        per app.py's module architecture note).
        """
        from modules.post_generator import SocialMediaPostGenerator

        gen = SocialMediaPostGenerator()
        gen.setup_business(
            {
                "business_type": business_info.get("type")
                or business_info.get("business_type", "restaurant"),
                "business_name": business_info.get("name")
                or business_info.get("business_name", "My Business"),
                "location": business_info.get("location", "Downtown"),
                "hours": business_info.get("hours", "11 AM - 8 PM"),
                "city": business_info.get(
                    "city", business_info.get("location", "My City")
                ),
                "special_item": business_info.get("special")
                or business_info.get("special_item", "Today's Special"),
                "hashtags": business_info.get("hashtags", []),
            }
        )
        return gen.generate_post(template, day=day, date=date)

    # -- Internals ----------------------------------------------------------

    @staticmethod
    def _resolve_context(request: ContentRequest) -> Any:
        if request.context is not None:
            return request.context
        try:
            if request.user_id:
                from core.business_brain.service import load_context

                return load_context(request.user_id)
            if request.business_info:
                from core.business_brain.service import load_context_from_dict

                return load_context_from_dict(request.business_info)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("pipeline: context load failed: %s", exc)
        return None

    @staticmethod
    def _validator_content_type(content_type: str) -> str:
        """Map AI content types onto the validator's allowed set."""
        ct = (content_type or "").strip().lower()
        if ct in _VALIDATOR_CONTENT_TYPES:
            return ct
        if ct in {"daily_special", "promo", "promotion", "giveaway", "event"}:
            return "promo"
        return "text"


def generate_content(
    business_info: Optional[Dict[str, Any]] = None,
    content_type: str = "general",
    tone: str = "friendly",
    keywords: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    user_id: str = "",
    template: str = "",
) -> ContentResult:
    """Convenience wrapper: build a ContentRequest and run the pipeline."""
    request = ContentRequest(
        business_info=dict(business_info or {}),
        content_type=content_type,
        tone=tone,
        keywords=list(keywords or []),
        platforms=list(platforms) if platforms else [],
        user_id=user_id,
        template=template,
    )
    return ContentPipeline().run(request)
