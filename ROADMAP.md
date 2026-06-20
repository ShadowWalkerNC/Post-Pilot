# PostPilot Pro — Roadmap

> Track what's done, what's next, and what's planned.

---

## ✅ Phase 1 — Foundation
- [x] Flask app + web GUI
- [x] Facebook publishing via Meta Graph API
- [x] Instagram publishing via Meta Graph API
- [x] Meta OAuth flow (FB + IG in one connect)
- [x] 5 post templates per business type

## ✅ Phase 2 — Scheduling & Analytics
- [x] Post scheduler (APScheduler)
- [x] Visual content calendar
- [x] Analytics dashboard (Meta Insights)
- [x] Weekly auto-schedule generator

## ✅ Phase 3 — Smart Hub
- [x] One-page Command Center
- [x] Smart content routing (video → video, text → text, image → image)
- [x] Google Business OAuth shell
- [x] TikTok script generator + OAuth shell
- [x] YouTube OAuth shell
- [x] Website hub editor (specials, hours, location, banner)
- [x] embed.js — one-line website integration
- [x] Live preview per platform
- [x] Platform connection status indicators

## 📋 Phase 4 — Make It Work
- [ ] `auth_manager.py` — token persistence + expiry detection
- [ ] Morning daily prompt — push notification + email
- [ ] `ai_generator.py` — OpenAI caption generation + tone selector
- [ ] `media_handler.py` — auto-resize images per platform spec
- [ ] `location_service.py` — one-tap location post for food trucks
- [ ] `onboarding.html` — 5-minute guided setup wizard
- [ ] Full `google_client.py` — Google Business posting + YouTube upload
- [ ] Full `tiktok_client.py` — TikTok Content Posting API

## 📋 Phase 5 — SaaS Launch
- [ ] Multi-user login (Flask-Login)
- [ ] PostgreSQL user + token database
- [ ] Stripe billing + subscription tiers
- [ ] Hosted website per user (yourbusiness.postpilot.app)
- [ ] Custom domain support via Cloudflare
- [ ] Public API with per-user API keys
- [ ] Developer docs (docs.postpilotpro.com)
- [ ] Square App Marketplace listing
- [ ] Toast Partner Marketplace listing
- [ ] Marketing landing page (index.html)
- [ ] Deploy to Render (production)

## 📋 Phase 6 — Growth & Stickiness
- [ ] Weekly Planner — set and forget 7-day schedule
- [ ] Simple Wins Dashboard — feel-good metrics
- [ ] Review Alerts — Google + Facebook in one inbox
- [ ] Repost Best Performers — surface top posts from 90 days
- [ ] Photo Templates — "TODAY'S SPECIAL" overlays
- [ ] Competitor Peek — compare posting frequency
- [ ] Square / Toast POS Integration — auto-post menu updates
- [ ] Threads — reuses existing Meta OAuth
- [ ] X/Twitter — simple REST API
- [ ] Nextdoor — hyper-local food truck discovery
- [ ] White-label Agency tier
- [ ] Annual recap shareable graphic
- [ ] Affiliate program (20% recurring)
