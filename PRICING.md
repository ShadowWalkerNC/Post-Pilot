# PostPilot Pro — Pricing Logic

---

## Cost Floor (What You Pay Monthly)

| Service | Cost | Notes |
|---------|------|-------|
| Render hosting | $7/mo | Scales to all users |
| PostgreSQL (Render) | $7/mo | User data, tokens, post history |
| OpenAI GPT-4o-mini | $5–20/mo | ~$0.002/caption, scales with usage |
| Cloudflare | Free | CDN, CORS, domain proxy |
| Stripe | 2.9% + $0.30/txn | Only pay when you earn |
| Domain (postpilotpro.com) | $1/mo | ~$12/yr |
| **Total fixed floor** | **~$25/mo** | Before any users |

---

## Tier Definitions

### Free — $0
**Purpose:** Hook. Lead generation. Conversion pipeline.
- Platforms: Facebook + Website only
- AI captions: 5/mo
- Scheduled posts: 3 max
- Users: 1
- Analytics: None
- API: None
- Locked (visible but greyed): TikTok, Instagram, Google Business, YouTube, Calendar, Weekly Planner, Analytics, API

### Starter — $15/mo | $150/yr
**Purpose:** Solo operator. Core tool.
- Platforms: All 6 (FB, IG, TikTok, YouTube, Google Business, Website)
- AI captions: 30/mo
- Scheduled posts: Unlimited
- Users: 1
- Analytics: Basic (last 30 days)
- API: None
- Locked: Weekly Planner, Review Alerts, API, White-label, Multi-seat

### Growth — $35/mo | $350/yr
**Purpose:** Restaurant / cafe with one social media helper.
- Platforms: All 6
- AI captions: 150/mo
- Scheduled posts: Unlimited
- Users: 1
- Analytics: Full (90 days + insights)
- API: Yes (1,000 calls/day)
- Weekly Planner: Yes
- Review Alerts: Yes
- Locked: White-label website, Multi-seat, Agency dashboard

### Pro — $69/mo | $690/yr
**Purpose:** Multi-location operator or busy single location.
- Platforms: All 6
- AI captions: Unlimited
- Scheduled posts: Unlimited
- Users: 3 seats
- Analytics: Full + cross-account
- API: Yes (10,000 calls/day)
- White-label hosted website: Yes
- Custom domain: Yes
- Review Alerts: Yes
- Weekly Planner: Yes

### Agency — $249/mo | $2,490/yr
**Purpose:** Marketing agencies reselling to local food clients.
- All Pro features
- 25 client accounts
- Reseller dashboard (add/remove clients)
- White-label branding (no PostPilot Pro visible to clients)
- Bulk posting across all clients
- Priority support (24hr response)
- API: Unlimited

---

## Conversion Strategy

### The Upgrade Moments
1. **Day 5–7:** Free user hits 5 AI caption limit
   → Banner: "You've used all 5 AI captions this month. Upgrade to Starter for 30/mo."

2. **Day 10:** Free user tries to post to Instagram
   → Lock screen: "Instagram posting is a Starter feature. Upgrade for $15/mo."

3. **Day 14:** Free user opens Calendar tab
   → Lock screen: "Schedule unlimited posts with Starter."

4. **Day 30:** Free user sees Monthly Recap teaser
   → "Your Growth tier unlocks full analytics. See exactly what's working."

### Annual Conversion
- Show annual option prominently on upgrade screen
- "Save $30 — pay $150/yr instead of $180/yr"
- Highlight: "Most food truck owners choose annual"
- Annual customers churn at roughly half the rate of monthly

---

## Stripe Implementation Notes

```python
# Price IDs to create in Stripe Dashboard
STRIPE_PRICES = {
    'starter_monthly':  'price_XXXXXX',  # $15/mo
    'starter_annual':   'price_XXXXXX',  # $150/yr
    'growth_monthly':   'price_XXXXXX',  # $35/mo
    'growth_annual':    'price_XXXXXX',  # $350/yr
    'pro_monthly':      'price_XXXXXX',  # $69/mo
    'pro_annual':       'price_XXXXXX',  # $690/yr
    'agency_monthly':   'price_XXXXXX',  # $249/mo
    'agency_annual':    'price_XXXXXX',  # $2,490/yr
}

# Webhook events to handle
WEBHOOK_EVENTS = [
    'customer.subscription.created',
    'customer.subscription.updated',
    'customer.subscription.deleted',
    'invoice.payment_failed',
    'invoice.payment_succeeded',
]

# On payment failure: downgrade to Free, lock features, email user
# On cancellation: keep data for 30 days, then archive
# Never delete user data on cancellation — they may come back
```
