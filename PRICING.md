# Post-Pilot — Pricing Logic

> **Canonical with:** `templates/billing.html`, `modules/plan_guard.py`, `PLANNING.md`  
> Hierarchy: `free < starter < pro < agency`  
> **No Growth tier** in product UI or plan enforcement.

---

## Cost floor (approximate monthly)

| Service | Cost | Notes |
|---------|------|-------|
| Vercel | Hobby/Pro plan | Serverless + Cron |
| Supabase Postgres | Free → Pro | User data, tokens, post history |
| Upstash Redis | Free → paid | Rate limiting across instances |
| OpenAI GPT-4o-mini | Usage-based | ~$0.002/caption, scales with usage |
| Stripe | 2.9% + $0.30/txn | Only when you earn |
| Sentry | Free → Team | Error monitoring |
| Domain | ~$1/mo | Optional custom domain |

---

## Tier definitions

### Free — $0
**Purpose:** Hook / lead gen.
- 1 location
- 5 posts / month
- 3 platforms max
- Manual publish only
- Locked: AutomationAgent, Inbox, Website embed

### Starter — $19/mo | $15/mo annual ($180/yr)
**Purpose:** Solo owner.
- 1 location
- 30 posts / month
- 5 platforms
- AutomationAgent
- Inbox (read-only)
- Website embed (specials)
- Basic analytics (30 days)
- Locked: AI reply drafts, multiple locations

### Pro — $49/mo | $39/mo annual ($468/yr)
**Purpose:** Full command center.
- 1 location
- Unlimited posts
- All 8 platforms
- Full AutomationAgent
- Inbox + AI reply drafts + owner approval
- Full website embed
- Advanced analytics (90 days)
- API access
- Locked: multiple locations

### Agency — $99/mo | $79/mo annual ($948/yr)
**Purpose:** Multi-location operators / small agencies.
- Up to 5 locations
- Everything in Pro per location
- Priority support
- White-label (roadmap — gate already in `plan_guard`)

---

## Conversion moments

1. **Free hits 5 posts/mo** → upgrade to Starter  
2. **Free tries AutomationAgent / embed** → Starter gate  
3. **Starter wants AI inbox replies / full embed / API** → Pro gate  
4. **Pro needs a second location** → Agency gate  

Annual: show “2 months free” toggle (already in `billing.html`).

---

## Stripe implementation

```python
# Env vars to set in Vercel (real Stripe Price IDs)
STRIPE_PRICES = {
    'starter_monthly':  os.environ['STRIPE_PRICE_STARTER_MONTHLY'],  # $19
    'starter_annual':   os.environ['STRIPE_PRICE_STARTER_ANNUAL'],   # $180/yr
    'pro_monthly':      os.environ['STRIPE_PRICE_PRO_MONTHLY'],      # $49
    'pro_annual':       os.environ['STRIPE_PRICE_PRO_ANNUAL'],       # $468/yr
    'agency_monthly':   os.environ['STRIPE_PRICE_AGENCY_MONTHLY'],   # $99
    'agency_annual':    os.environ['STRIPE_PRICE_AGENCY_ANNUAL'],    # $948/yr
}

WEBHOOK_EVENTS = [
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'invoice.payment_failed',
    'invoice.payment_succeeded',
]
```

Graceful downgrade: never delete data on cancel/payment failure; lock paid features; allow resubscribe.
