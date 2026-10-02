---
name: brand_guard
version: 1.0.0
description: Audit a draft caption against brand voice, banned claims, and platform rules before publish.
inputs: [business_name, tone, platform, draft, banned_words, required_cta]
---

# brand_guard

Pre-publish audit pass. Takes a draft caption and returns PASS/FAIL with
reasons. Deterministic checks run wherever possible; the prompt covers
judgment calls. Provider-agnostic.

## Inputs

| Variable | Required | Example |
|---|---|---|
| business_name | yes | Taco Libre Truck |
| tone | no | friendly |
| platform | yes | instagram |
| draft | yes | Today's special... |
| banned_words | no | free, guaranteed, #1 |
| required_cta | no | true |

## Prompts

- `prompts/audit.md` — the audit prompt; expects a PASS/FAIL verdict.

## Rules

- `rules/guard_rules.md` — hard-fail conditions and platform limits.
