# Post-Pilot — Master Plan

> **Status:** In production (Vercel) · Phase 5 hardening  
> **Last Updated:** 2026-08-08  
> **Repo:** github.com/ShadowWalkerNC/Post-Pilot  
> **Canonical for:** phase status, stack, pricing, next work  
> **Open tasks:** see `TODO.md` · **Ship steps:** see `TODO.md` §CRITICAL

---

## What it is

Post-Pilot is AI-powered social media automation for food trucks, restaurants, hotels, cafes, and food companies. Operators generate platform-aware captions, publish to connected networks, keep specials/events/hours current, and optionally embed that data on their website.

**Working promise (shipped core):** write once → adapt per platform → publish or schedule via Vercel Cron.

**Stretch promise (not fully shipped):** one-tap location posts, morning habit loop, full Google/TikTok/YouTube publish, multi-location agency white-label.

---

## Who it's for

| Segment | Profile | Willingness to pay |
|---|---|---|
| Primary | Solo food/hospitality operator, 1–5 people, no marketer | $15–30/mo if it saves 2+ hrs/week |
| Secondary | Independent restaurant/cafe, 5–20 people | $30–60/mo |
| Tertiary | Local agency managing many food clients | Agency tier when multi-location + reseller are real |

---

## Stack (live — do not contradict)

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| App | Flask 3.x, Jinja2, Tailwind |
| Hosting | **Vercel** (serverless) + Vercel Cron |
| Database | Supabase PostgreSQL (SQLAlchemy + psycopg2); SQLite local |
| Auth | **Supabase magic link** (no passwords) |
| AI | **OpenAI** (`OPENAI_API_KEY`, GPT-4o-mini) via `modules/ai_generator.py` |
| Social | Meta Graph API (FB/IG); Google/TikTok/YouTube clients exist (completeness varies) |
| Billing | Stripe + `modules/billing_manager.py` + `modules/plan_guard.py` |
| Rate limits | Flask-Limiter; Redis/Upstash in prod |
| Observability | Sentry when `SENTRY_DSN` set |
| Migrations | Alembic (forward-only) |
| CI | GitHub Actions — ruff + pytest |

**Not the deploy target:** Render, Railway, Heroku, long-lived APScheduler workers. Cron must go through `vercel.json` → `/api/cron/*` + `CRON_SECRET`.

---

## Pricing (canonical — matches `billing.html` + `plan_guard.py`)

Hierarchy: `free < starter < pro < agency`  
**There is no Growth tier in the product UI or plan guard.** Orphan `growth_*` Stripe env keys / maps should be removed, not documented as live.

| Tier | Monthly | Annual equiv. | Posts/mo | Platforms | Locations | Highlights |
|---|---|---|---|---|---|---|
| Free | $0 | — | 5 | 3 | 1 | Manual publish only |
| Starter | $19 | $15/mo ($180/yr) | 30 | 5 | 1 | Agent, inbox read-only, basic embed, basic analytics |
| Pro | $49 | $39/mo ($468/yr) | Unlimited | 8 | 1 | Full agent, AI replies, full embed, advanced analytics, API |
| Agency | $99 | $79/mo ($948/yr) | Unlimited | 8 | 5 | Everything in Pro per location |

Stripe price env vars (only these):

- `STRIPE_PRICE_STARTER_MONTHLY` / `_ANNUAL`
- `STRIPE_PRICE_PRO_MONTHLY` / `_ANNUAL`
- `STRIPE_PRICE_AGENCY_MONTHLY` / `_ANNUAL`

Details and upgrade moments: `PRICING.md`.

---

## Phase status

### Done — foundation through SaaS core

Treat these as **built**, not rebuild targets:

- Flask app + blueprint layout (`blueprints/`, `modules/`)
- Magic-link auth (`blueprints/auth.py`, Supabase)
- Encrypted platform tokens (`modules/auth_manager.py`, Fernet / `TOKEN_ENCRYPTION_KEY`)
- OpenAI caption generation + per-platform adaptation (`ai_generator.py`, `platform_adapter.py`)
- Meta publish path + publisher routing
- Stripe billing + webhooks + plan gating
- Onboarding / login / billing / dashboard / generate / schedule / analytics templates
- Specials, events, hours CRUD + automation agent reads all three
- Vercel Cron: `/api/cron/generate` (hourly), `/api/cron/publish` (every minute)
- Public embed API + `static/embed.js` (`blueprints/embed_api.py`)
- Alembic migrations through `0006_events_hours` (incl. `0003_drop_password_hash`)
- CI (ruff + pytest), MCP server scaffolding

### Now — Phase 5: harden & go live

Definition of done:

1. Manual go-live blockers in `TODO.md` §CRITICAL completed (keys, Vercel env, migrations, smoke test)
2. Doc/code single source of truth (this file + `TODO.md` + `ROADMAP.md`)
3. Redis rate limiting live in prod (`REDIS_URL`)
4. Growth-tier orphans removed from billing maps / env checklists
5. Teams / multi-user (if still required) designed against magic-link users — **no password_hash**
6. Analytics page verified against real Meta insights data
7. SEC-1 / SEC-2 / SEC-3 confirmed done

### Next — Phase 6: retention & depth

Ship only after Phase 5 go-live:

- Morning daily prompt (email; push later) — habit loop
- Location one-tap post (food-truck daily action)
- Inbox comment poll + AI draft replies (plan-gated)
- Embed slug onboarding polish + dashboard preview UX
- Full Google Business / TikTok / YouTube publish (beyond OAuth shells)
- Weekly planner, review alerts, repost winners
- Marketing site polish + public launch checklist

### Later — Phase 7: agency & ecosystem

- True multi-location / reseller dashboard matching Agency limits
- Custom domains for hosted mini-sites
- POS integrations (Square / Toast) when API access is real
- Extra networks (Threads, X, Nextdoor) only after Meta + Google quality is solid

---

## Architecture map (actual layout)

```
Post-Pilot/
  app.py                      # Flask factory, limiter, Sentry, blueprint register
  blueprints/
    auth.py                   # Magic link, OAuth connect callbacks, /dev-login
    billing.py                # Stripe checkout / portal / webhook
    api.py                    # Generate / publish / platform settings APIs
    cron.py                   # Vercel Cron generate + publish
    pages.py                  # HTML pages (dashboard, generate, etc.)
    website.py                # Website hub
    embed_api.py              # Public GET /api/embed/<slug>
    specials.py | events.py | hours.py
  modules/
    auth_manager.py           # Encrypted token store
    ai_generator.py           # OpenAI captions
    platform_adapter.py       # Per-platform adaptation
    publisher.py              # Publish router
    billing_manager.py        # Stripe lifecycle
    plan_guard.py             # @require_plan + limits
    user_manager.py           # Users (magic-link era)
    automation_agent.py       # Specials/events/hours → posts
    meta_api.py / meta_client.py
    google_client.py | tiktok_client.py | …
  alembic/versions/           # 0001 … 0006
  templates/ | static/
  vercel.json                 # Builds + cron schedules
  TODO.md                     # Executable checklist (source for open work)
```

Agents must not invent missing files from old plans (`auth_utils.py`, `generate.py` blueprint, `modules/ai.py` Claude wrapper, etc.). If a path is not on disk, it is not the architecture.

---

## Execution order (from here)

```
1. Complete TODO.md §CRITICAL (manual ops — keys, Vercel env, alembic upgrade, smoke)
2. Remove Growth orphan from billing_manager / env docs / checklists
3. Confirm Redis + Sentry in Vercel production
4. Wire remaining plan gates (e.g. check_post_limit on publish paths)
5. Inbox + morning prompt + location one-tap (Phase 6 product)
6. Finish non-Meta publishers only after Meta path is reliable in prod
7. Agency multi-location / white-label last
```

Do **not** restart with “Session 1: rebuild auth_manager” or “Deploy to Render.”

---

## Retention (still the product north star)

```
TRIGGER  → morning ping: "Where are you today? What's the special?"
ACTION   → location + special → Push
REWARD   → posted confirmation + simple reach win
```

Keep this as Phase 6 priority after go-live. Do not block production deploy on it.

---

## Doc ownership

| Doc | Role |
|---|---|
| `PLANNING.md` | **This file** — strategy, stack, phases, pricing truth |
| `ROADMAP.md` | Checkbox phase tracker (must match this file) |
| `TODO.md` | Actionable open work + manual go-live steps |
| `PRICING.md` | Tier marketing copy + Stripe notes (must match plan_guard) |
| `ARCHITECTURE.md` | Technical reference (must match repo layout) |
| `AGENTS.md` | Agent rules (must match stack above) |
| `DEPLOY.md` | Vercel deploy runbook only |

When these disagree, **code + `plan_guard.py` + `billing.html` + `vercel.json` win**, then update the docs in the same PR.
