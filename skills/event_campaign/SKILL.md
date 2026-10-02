---
name: event_campaign
version: 1.0.0
description: Build a multi-post campaign (announce, reminder, last-call) for an event.
inputs: [business_name, business_type, location, event_title, event_date, event_end_date, ticket_url, tone, platform]
---

# event_campaign

Generates a 3-post event campaign: announcement, reminder, and last-call.
Each post is platform-adapted. Render with `skills/loader.py`; usable by any
LLM provider or the template fallback.

## Inputs

| Variable | Required | Example |
|---|---|---|
| business_name | yes | The Copper Kettle |
| business_type | no | cafe |
| location | no | 12 Main St, Durham |
| event_title | yes | Live Jazz Night |
| event_date | yes | 2026-10-10 19:00 |
| event_end_date | no | 2026-10-10 22:00 |
| ticket_url | no | https://tickets.example.com/jazz |
| tone | no | hype |
| platform | no | facebook |

## Prompts

- `prompts/announce.md` — first announcement post.
- `prompts/reminder.md` — mid-campaign reminder post.
- `prompts/last_call.md` — final last-call post.

## Rules

- `rules/campaign_rules.md` — date accuracy, ticket-link, cadence guardrails.
