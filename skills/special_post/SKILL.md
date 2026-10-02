---
name: special_post
version: 1.0.0
description: Generate a high-engagement daily-special post from a menu item, price, and availability window.
inputs: [business_name, business_type, location, item_name, description, price, available_until, tone, platform]
---

# special_post

Turns one daily special into a ready-to-publish caption for any platform.
Provider-agnostic: render a prompt with `skills/loader.py`, then send the
text to any LLM (OpenAI, Anthropic, local model) or use the template fallback.

## Inputs

| Variable | Required | Example |
|---|---|---|
| business_name | yes | Taco Libre Truck |
| business_type | no | food truck |
| location | no | 5th & Main, Raleigh |
| item_name | yes | Baja Shrimp Tacos |
| description | no | cilantro-lime slaw, chipotle crema |
| price | no | $9.99 |
| available_until | no | 8pm today |
| tone | no | hype |
| platform | no | instagram |

## Prompts

- `prompts/caption.md` — full caption generation prompt.
- `prompts/hook_only.md` — first-line hook only (for A/B testing hooks).

## Rules

- `rules/special_rules.md` — guardrails (price honesty, urgency limits, CTA).
