"""core — canonical Post-Pilot domain layer.

`core/content/pipeline.py` is the ONE canonical content pipeline.
`core/business_brain/` is the unified business context all content/agents read.

Legacy `modules/*` generators remain the execution layer: core delegates to
them (import + call) and never duplicates their prompt/template logic.
Nothing in `modules/` or `blueprints/` imports from `core/` yet; adoption is
opt-in per caller so existing behavior is preserved.
"""

__all__ = []
