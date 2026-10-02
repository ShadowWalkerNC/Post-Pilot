---
name: weekly_plan
version: 1.0.0
description: Draft a 7-day posting plan mixing specials, events, engagement, and promo posts.
inputs: [business_name, business_type, location, week_of, specials, events, tone, platforms, posts_per_week]
---

# weekly_plan

Produces a 7-day content calendar as structured text the caller can parse
into scheduled posts. Render with `skills/loader.py`; usable by any provider.

## Inputs

| Variable | Required | Example |
|---|---|---|
| business_name | yes | Taco Libre Truck |
| business_type | no | food truck |
| location | no | Raleigh, NC |
| week_of | yes | 2026-10-05 |
| specials | no | Mon: Baja tacos; Fri: Birria |
| events | no | Sat: Food Truck Rodeo |
| tone | no | friendly |
| platforms | no | fb, ig, tt |
| posts_per_week | no | 5 |

## Prompts

- `prompts/plan.md` — full week plan generation prompt.

## Rules

- `rules/plan_rules.md` — mix ratios, cadence, and format guardrails.
