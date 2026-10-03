# Post-Pilot — Roadmap

> Track what's done, what's next, and what's planned.  
> **Source of truth for phases:** `PLANNING.md` · **Open tasks:** `TODO.md`

---

## ✅ Phase 1–4 — Core product (shipped)

- [x] Flask app + web GUI (blueprints + modules)
- [x] Facebook + Instagram publishing (Meta Graph API)
- [x] Meta OAuth connect flow
- [x] Magic-link auth (Supabase) — no passwords
- [x] Encrypted token persistence (`auth_manager.py` + `TOKEN_ENCRYPTION_KEY`)
- [x] OpenAI caption generation + per-platform adaptation
- [x] Stripe billing + webhooks + `@require_plan` / `plan_guard.py`
- [x] Onboarding, dashboard, generate, schedule, analytics, billing UI
- [x] Specials / events / hours + automation agent
- [x] Vercel Cron (`/api/cron/generate`, `/api/cron/publish`)
- [x] Public embed API + `static/embed.js`
- [x] Alembic migrations through `0006`
- [x] CI (ruff + pytest) + MCP server scaffolding

---

## 📋 Phase 5 — Harden & go live (current)

- [ ] Manual go-live blockers in `TODO.md` §CRITICAL
- [ ] Rotate / set `FLASK_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `CRON_SECRET` in Vercel
- [ ] Production env: `OPENAI_API_KEY`, Stripe prices, `REDIS_URL`, `SENTRY_DSN`, Supabase keys
- [ ] `alembic upgrade head` against production Postgres
- [ ] Confirm `DEV_LOGIN_KEY` absent in Vercel production
- [ ] Remove Growth-tier orphans from code/env checklists
- [ ] Untrack secrets/binaries if still present (`.venv`, local DB artifacts)
- [ ] Smoke test: magic link → schedule special → cron generate → billing → connect platform
- [ ] Teams / multi-seat design (magic-link users only; no `password_hash`)
- [ ] Analytics verified with real Meta insights in prod

---

## 📋 Phase 6 — Retention & depth

- [x] Morning daily prompt (email first via notification_service + cron)
- [x] Location one-tap post (`/api/location/one_tap` + GPS reverse geocode)
- [x] Inbox: poll comments + AI draft replies + approve/edit/skip (`blueprints/inbox.py`)
- [ ] Embed slug onboarding + in-dashboard preview/copy UX
- [x] Complete Google Business posting (`integrations/google.py`)
- [x] Complete TikTok Content Posting API path (`integrations/tiktok.py`)
- [x] Complete YouTube upload path (`integrations/google.py`)
- [ ] Weekly planner (set 7, forget)

- [ ] Simple wins / best-performer resurfacing
- [ ] Review alerts (Google + Facebook)

---

## 📋 Phase 7 — Agency & ecosystem

- [ ] Multi-location Agency UX (up to 5 locations per `plan_guard`)
- [ ] White-label / reseller dashboard
- [ ] Custom domain for hosted mini-sites
- [ ] Square / Toast POS integrations (when partner access exists)
- [ ] Threads / X / Nextdoor (only after Meta + Google quality is solid)
- [ ] Affiliate program

---

## Explicitly out of plan

| Idea | Why not |
|---|---|
| Deploy to Render / Railway as primary | Production target is Vercel (+ Supabase) |
| Rebuild password auth / Flask-Login passwords | Magic link is the product auth |
| Re-add Growth tier | UI + `plan_guard` are Free/Starter/Pro/Agency |
| Restart Phase 4 “auth_manager from scratch” | Already shipped |
| Claim full TikTok auto as a differentiator today | Publish path not production-complete |
