# PostPilot Pro — Master Build Plan

> **Status:** Planning Complete → Ready to Build
> **Last Updated:** June 2026
> **Repo:** github.com/ShadowWalkerNC/social-media-post-generator
> **SaaS Target:** postpilotpro.com

---

## 🎯 What It Is

> **PostPilot Pro is the only tool that lets a local food or hospitality business update their social media, Google Business, and website — all at once, from one screen, in under 60 seconds.**

Write once. Smart routing sends videos to video platforms, text to text platforms, images to image platforms. Hit Push. Done.

---

## 👤 Who It's For

### Primary — Solo Food/Hospitality Operator
- Food truck, coffee shop, cafe, bar, brewery, farmers market vendor, pop-up, catering
- 1–5 employees. No marketing person. No marketing budget.
- Knows they need to post but never has time or content ideas
- Currently using: phone + Meta's free tools + nothing for website
- **Pain:** 5 different apps, zero consistency, website always outdated
- **Willingness to pay:** $15–30/mo if it genuinely saves 2+ hours/week

### Secondary — Independent Restaurant / Cafe
- 5–20 employees, maybe one part-time social media helper
- Has a website nobody updates
- Needs Google Business kept current (hours, specials, posts)
- **Willingness to pay:** $30–60/mo

### Tertiary — Local Marketing Agency (Phase 5+)
- Manages 10–50 local food/hospitality clients
- Wants white-label tool to resell under their brand
- **Willingness to pay:** $249/mo for agency tier

---

## 🏆 The Market Gap

| Tool | Price | Google Business | Website | Content Generation | TikTok Auto |
|------|-------|----------------|---------|-------------------|-------------|
| Hootsuite | $99–739/mo | ❌ | ❌ | ❌ | ✅ |
| Buffer | $20/mo | ❌ | ❌ | ❌ | ✅ |
| Later | $25/mo | ❌ | ❌ | ❌ | ✅ |
| Meta Suite | Free | ❌ | ❌ | ❌ | ❌ |
| **PostPilot Pro** | **$15/mo** | **✅** | **✅** | **✅** | **✅** |

Freelance social media management costs $500–1,500/mo. We do more for $15.

---

## 💰 Pricing

### Monthly
| Tier | Price | Platforms | AI Captions | Users | Key Feature |
|------|-------|-----------|-------------|-------|-------------|
| **Free** | $0 | FB + Website only | 5/mo | 1 | Hook + lead gen |
| **Starter** | $15/mo | All 6 platforms | 30/mo | 1 | Core tool |
| **Growth** | $35/mo | All 6 + API access | 150/mo | 1 | Weekly planner + analytics |
| **Pro** | $69/mo | All 6 + white-label website | Unlimited | 3 seats | Multi-location |
| **Agency** | $249/mo | All + reseller dashboard | Unlimited | 25 clients | White-label |

### Annual (2 months free)
| Tier | Annual Price | Monthly Equivalent | Savings |
|------|-------------|-------------------|--------|
| Starter | $150/yr | $12.50/mo | $30 |
| Growth | $350/yr | $29.17/mo | $70 |
| Pro | $690/yr | $57.50/mo | $138 |
| Agency | $2,490/yr | $207.50/mo | $498 |

### Free Tier Limits (Conversion Gates)
- FB + Website only (TikTok, IG, Google, YouTube locked)
- 5 AI captions/mo (hits limit in first week for active users)
- Schedule up to 3 posts (calendar locked)
- No API access
- No analytics

---

## 🔧 Feature Roadmap

### ✅ Phase 1–3 — Built
- Flask app + web GUI
- Facebook + Instagram publishing (Meta Graph API)
- Meta OAuth flow
- Post scheduler (APScheduler)
- Visual content calendar
- Analytics dashboard (Meta Insights)
- One-page command center hub
- Smart content routing (video → video, text → text, image → image)
- Google Business shell + OAuth
- TikTok script generator + OAuth shell
- YouTube shell + OAuth
- Website live hub (banner, specials, hours, location)
- embed.js — one-line website integration
- Live preview per platform

### 📋 Phase 4 — Make It Work (Build Next)

#### Priority 1 — Token Persistence (`auth_manager.py`)
- Currently tokens die on app restart — breaks everything for real users
- Store tokens encrypted in SQLite (dev) / PostgreSQL (prod)
- Background job checks token expiry weekly
- Dashboard red pill indicator when token within 7 days of expiry
- Facebook: 60-day token, store long-lived version
- Google: 1-hour token, store refresh_token, auto-refresh silently
- TikTok: 24-hour token, daily refresh job
- One-click reauth from dashboard when expired

#### Priority 2 — Morning Daily Prompt (Retention Engine)
- Daily push notification + email at user-set time (default 7am)
- Message: "Good morning! Where are you today? What's the special?"
- User replies / taps → auto-posts location + special to all platforms
- This is the #1 retention feature — creates daily habit loop
- **Must ship in Phase 4, not Phase 6**

#### Priority 3 — AI Caption Generator (`ai_generator.py`)
- Input: business_info + content_type + tone + keywords
- Output: platform-optimized captions (different per platform)
- Option A: OpenAI GPT-4o-mini (cheap, $0.002/caption)
- Option B: Local LLM fallback (Ollama + llama3) for self-hosted users
- Option C: Template fallback if no AI key configured
- Tone selector: 🔥 Hype / 😊 Friendly / 📣 Urgent / 😂 Funny / 🤝 Community

#### Priority 4 — Image Auto-Resize (`media_handler.py`)
- Instagram: 1080×1080 (square) or 1080×1350 (portrait)
- Facebook: 1200×630
- YouTube thumbnail: 1280×720
- TikTok: 9:16 vertical
- Tool: Pillow for images, ffmpeg for video thumbnails
- Store processed versions in /static/uploads/ temporarily

#### Priority 5 — Location One-Tap Post
- Single biggest daily action for food trucks
- GPS pull or manual pin drop
- Auto-writes: "🚚 We're at [Location] today! Open [hours]. Come find us!"
- Pushes to FB + IG + Google Business + Website map in one tap
- No other tool does this specifically for food trucks

#### Priority 6 — Onboarding Wizard (`onboarding.html`)
- 5-minute guided setup
- Step 1: Business name, type, location, hours
- Step 2: Connect Facebook (gets FB + IG)
- Step 3: Connect Google (gets Google Business + YouTube)
- Step 4: Connect TikTok
- Step 5: Add embed to website (copy/paste one line)
- Step 6: First post — guided, can't fail
- Progress bar. Celebrate each connection. Make it feel easy.

### 📋 Phase 5 — Make It a Real SaaS

#### Multi-User Accounts
- Flask-Login or Supabase Auth
- Users table: id, email, password_hash, subscription_tier, created_at
- Tokens table: user_id, platform, access_token (encrypted), refresh_token, expires_at
- Business profiles table: user_id, name, type, location, hours, logo_url

#### Stripe Billing
- Subscription tiers map to Stripe Price IDs
- Webhook handles: subscription created, updated, cancelled, payment failed
- Graceful downgrade on payment failure (don't delete data, lock features)
- Customer portal for self-serve plan changes

#### Hosted Website Per User
- Every user gets: yourbusiness.postpilot.app
- Full page: banner, specials, hours, location map, gallery, about, contact
- Custom domain support: point yourfoodtruck.com → our server via Cloudflare
- "Powered by PostPilot Pro" footer link = passive marketing
- Sections editable directly from dashboard — no login to website ever

#### Public API + API Keys
- Every Growth+ user gets an API key from their dashboard
- Endpoints: /v1/publish, /v1/schedule, /v1/analytics, /v1/website, /v1/generate
- Rate limits by tier
- Developer docs at docs.postpilotpro.com
- Partner portal for POS integrations

### 📋 Phase 6 — Make It Sticky
- **Weekly Planner** — set 7 posts Sunday, forget about it all week
- **Simple Wins Dashboard** — reach up 34%, best post this week, etc.
- **Review Alerts** — Google + Facebook reviews in one inbox, one-click response
- **Repost Best Performers** — surface top posts from 90 days ago
- **Photo Templates** — "TODAY'S SPECIAL" overlays, zero design skill
- **Competitor Peek** — "your 3 nearest competitors posted 4x this week"
- **Square / Toast POS Integration** — auto-post when new menu item added
- **Threads** — free add, reuses existing Meta OAuth token
- **X/Twitter** — simple REST API add
- **Nextdoor** — hyper-local, perfect for food trucks
- **Annual recap** — "Your best year on social" sharable graphic

---

## 🏗️ File Structure

```
postpilot-pro/
│
├── app.py                        # Flask entry point, all routes, OAuth flows
├── config.py                     # TODO: App config, env loading, feature flags per tier
├── requirements.txt
├── Procfile                      # For Render/Heroku deployment
├── .env.example                  # All API keys documented
├── README.md
├── PLANNING.md                   # This file
├── ROADMAP.md                    # Phase tracker
├── COMPETITORS.md                # Competitive analysis
├── API_NOTES.md                  # Per-platform API gotchas
├── DISTRIBUTION.md               # GTM, POS marketplace, agency strategy
├── PRICING.md                    # Pricing logic, Stripe Price IDs
│
├── modules/
│   ├── __init__.py
│   ├── publisher.py              # ✅ Smart router — core brain
│   ├── post_generator.py         # ✅ Template-based caption generator
│   ├── post_scheduler.py         # ✅ APScheduler
│   ├── analytics_client.py       # ✅ Meta Insights
│   ├── auth_manager.py           # TODO P4: Token storage, refresh, expiry
│   ├── ai_generator.py           # TODO P4: OpenAI / LLM caption generation
│   ├── media_handler.py          # TODO P4: Image resize per platform
│   ├── location_service.py       # TODO P4: GPS + location post generator
│   ├── notification_service.py   # TODO P4: Morning prompt push/email
│   ├── meta_client.py            # TODO P4: Extract FB+IG into own module
│   ├── google_client.py          # TODO P4: Google Business + YouTube
│   ├── tiktok_client.py          # TODO P4: TikTok Content Posting API
│   ├── youtube_client.py         # TODO P4: YouTube Data API v3
│   ├── website_client.py         # TODO P4: Hosted website + banner.json
│   ├── user_manager.py           # TODO P5: Multi-user DB operations
│   ├── billing_manager.py        # TODO P5: Stripe webhooks + tier gating
│   └── api_manager.py            # TODO P5: Public API keys + rate limiting
│
├── templates/
│   ├── dashboard.html            # ✅ ONE-PAGE HUB — primary interface
│   ├── setup.html                # ✅ Business setup + platform connect
│   ├── calendar.html             # ✅ Visual content calendar
│   ├── analytics.html            # ✅ Analytics dashboard
│   ├── onboarding.html           # TODO P4: First-run 5-min wizard
│   ├── website_hub.html          # TODO P5: Hosted website template per user
│   ├── login.html                # TODO P5: User authentication
│   ├── register.html             # TODO P5: New user signup
│   ├── billing.html              # TODO P5: Stripe subscription management
│   ├── api_docs.html             # TODO P5: Developer API documentation
│   └── index.html                # TODO P5: Marketing landing page
│
├── static/
│   ├── style.css                 # ✅ Global styles
│   ├── dashboard.css             # ✅ Hub-specific styles
│   ├── dashboard.js              # ✅ Hub logic, smart routing, live preview
│   ├── embed.js                  # ✅ Website banner embed (served to client sites)
│   ├── banner.json               # ✅ Live website data bridge
│   ├── app.js                    # TODO: Shared JS utilities
│   ├── uploads/                  # TODO P4: Processed media files (temp)
│   ├── favicon.ico               # TODO: Brand icon
│   └── logo.png                  # TODO: PostPilot Pro logo
│
├── tests/
│   ├── test_publisher.py         # TODO: Smart routing unit tests
│   ├── test_generator.py         # TODO: Caption generation tests
│   ├── test_auth.py              # TODO: Token refresh/expiry tests
│   ├── test_api_mocks.py         # TODO: Mock API responses (no real calls)
│   └── test_routing.py           # TODO: Verify all routing rules
│
└── docs/
    ├── SETUP_FACEBOOK.md         # TODO: Facebook app setup guide
    ├── SETUP_GOOGLE.md           # TODO: Google Cloud console setup
    ├── SETUP_TIKTOK.md           # TODO: TikTok developer account guide
    ├── SETUP_YOUTUBE.md          # TODO: YouTube Data API setup
    ├── WEBSITE_EMBED.md          # TODO: Add embed to any website
    ├── API_REFERENCE.md          # TODO: Public API endpoint reference
    └── DEPLOY_RENDER.md          # TODO: Deploy to Render step-by-step
```

---

## 🔄 Retention Strategy

### The Daily Habit Loop
```
TRIGGER  → 7am notification: "Good morning! Where are you today?"
ACTION   → User types location + special, hits Push
REWARD   → "✅ Posted to 6 platforms! Yesterday's post got 47 likes 🎉"
```
Repeat daily. App becomes essential within 2 weeks.

### Retention Touchpoints
| Timing | Action |
|--------|--------|
| Day 1 | Welcome email + setup video |
| Day 3 | "You've posted X times! Here's your reach" |
| Day 7 | First weekly summary email |
| Day 14 | Audience insight: "Most active at 11:30am Fridays" |
| Day 30 | Monthly recap + upgrade prompt with specific ROI shown |
| Token expiry | Dashboard red alert + one-click reauth |
| 7 days no post | "It's been a week — your followers miss you 👀" |

---

## 🔑 Build Session Order

```
Session 1:  auth_manager.py — token persistence (SQLite + encryption)
Session 2:  notification_service.py — morning prompt (email + push)
Session 3:  ai_generator.py — OpenAI caption generation
Session 4:  media_handler.py — image auto-resize per platform
Session 5:  location_service.py — one-tap location post
Session 6:  onboarding.html — 5-minute guided setup wizard
Session 7:  google_client.py — full Google Business + YouTube
Session 8:  tiktok_client.py — TikTok Content Posting API
Session 9:  user_manager.py + login/register — multi-user accounts
Session 10: billing_manager.py + Stripe — subscriptions
Session 11: website_hub.html — hosted website per user
Session 12: api_manager.py — public API + developer docs
Session 13: index.html — marketing landing page
Session 14: tests/ — unit tests for all modules
Session 15: docs/ — setup guides + deploy guide
Session 16: Deploy to Render — go live
```
