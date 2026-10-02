---
name: review_reply
version: 1.0.0
description: Draft an on-brand reply to a customer review or comment, matched to sentiment.
inputs: [business_name, business_type, location, review_text, rating, sentiment, tone, reviewer_name]
---

# review_reply

Drafts a reply to a review/comment. Sentiment should come from
`modules/reply_agent.py::classify_sentiment`; this skill only shapes the
words. Provider-agnostic prompt text.

## Inputs

| Variable | Required | Example |
|---|---|---|
| business_name | yes | The Copper Kettle |
| business_type | no | cafe |
| location | no | Durham |
| review_text | yes | Best latte in town! |
| rating | no | 5 |
| sentiment | no | positive |
| tone | no | friendly |
| reviewer_name | no | Maya |

## Prompts

- `prompts/reply.md` — the reply-drafting prompt.

## Rules

- `rules/reply_rules.md` — apology/escalation and spam guardrails.
