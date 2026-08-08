# AGENTS.md — Post-Pilot

> **Extends:** `ShadowWalkerNC/.github/AGENTS.md` — all global rules apply unconditionally.
> **Purpose:** Project-specific overrides and context for AI agents working in this repository.
> **Auto-loaded by:** Claude Code · GitHub Copilot · OpenAI Codex · Cursor · Windsurf · Perplexity MCP

---

## Project Identity

```
Project:      Post-Pilot
Description:  AI-powered social media automation for food trucks, restaurants, hotels,
              cafes, and food companies. Generates high-engagement posts and publishes
              directly to Facebook & Instagram via Meta Graph API.
Status:       In production (Vercel)
Phase:        Phase 5 — Harden & go live (keys, Redis, analytics verify, teams design)
Priority:     Active
```

---

## Tech Stack

```
Language:     Python 3.11+
Framework:    Flask 3.x
Database:     Supabase (PostgreSQL via SQLAlchemy + psycopg2) + SQLite (local dev)
Hosting:      Vercel (serverless + Vercel Cron)
Key APIs:     Meta Graph API (Facebook/Instagram), OpenAI, Stripe, Sentry, Supabase Auth
CI/CD:        GitHub Actions (.github/workflows/ci.yml) — ruff lint + pytest
Observability: Sentry (via SENTRY_DSN env var)
Auth:         Magic link email via Supabase (no passwords)
Payments:     Stripe (Free / Starter / Pro / Agency)
AI:           OpenAI GPT-4o-mini (OPENAI_API_KEY) via modules/ai_generator.py
```

---

## Repository Structure

```
Post-Pilot/
  app.py               ← Flask app factory, blueprint registration, Sentry init
  blueprints/          ← Flask blueprints (one file per domain)
    auth.py            ← Magic link auth, OAuth connect, /dev-login
    billing.py         ← Stripe checkout / portal / webhook
    api.py             ← Generate / publish / platform-settings APIs
    pages.py           ← HTML pages (dashboard, generate, schedule, …)
    cron.py            ← Vercel Cron (/api/cron/generate, /api/cron/publish)
    website.py         ← Website hub
    embed_api.py       ← Public GET /api/embed/<slug>
    specials.py        ← Specials CRUD + /schedule page
    events.py          ← Events CRUD
    hours.py           ← Hours overrides CRUD
  modules/             ← Shared utilities and services
    database.py / db.py← DB access
    auth_manager.py    ← Encrypted platform token store (Fernet)
    ai_generator.py    ← OpenAI caption generation
    platform_adapter.py← Per-platform caption adaptation
    publisher.py       ← Publish router
    billing_manager.py ← Stripe lifecycle
    plan_guard.py      ← @require_plan + tier limits
    user_manager.py    ← User records (magic-link era)
    automation_agent.py← Specials/events/hours → scheduled posts
    meta_api.py        ← Meta Graph API client
  templates/           ← Jinja2 HTML templates
  static/              ← CSS (Tailwind), JS, images, embed.js
  alembic/             ← Database migrations (forward-only)
    versions/          ← 0001 … 0006
  tests/               ← pytest test suite
  mcp/                 ← Post-Pilot MCP server
  vercel.json          ← Vercel deployment + Cron config
  requirements.txt     ← Python dependencies
  .env.example         ← All required env vars (no values)
  PLANNING.md          ← Phase / pricing / stack source of truth
  ROADMAP.md           ← Checkbox phase tracker
  TODO.md              ← Current open work — read every session
  ARCHITECTURE.md      ← System design reference
  PRICING.md           ← Tier copy (must match plan_guard + billing.html)
  DEPLOY.md            ← Vercel deployment runbook
  CHANGELOG.md         ← What changed and when
  V1_API.md            ← External API documentation
```

If a path is not on disk, do not invent it from older docs.

---

## Active Agents for This Project

```
Always active:    COHERENCE · SECURITY · DOCS
Default on-demand: ENGINEER · DATABASE · DEVOPS · QA
Load when needed: ARCHITECT (system design changes), AI (OpenAI/prompt work),
                  PRODUCT (roadmap/scope), UX (template/UI work)
Rarely needed:    BUSINESS (load only for pricing/go-to-market work)
```

---

## Project-Specific Rules

1. All Supabase/Alembic migrations must be reviewed by DATABASE agent before any push. Migrations are forward-only — no rollbacks without explicit approval.
2. Every new blueprint route requires `@require_plan` or `@login_required` — no unauthenticated endpoints except `/login`, `/auth/*`, `/api/embed/<slug>`, and `/api/cron/*` (CRON_SECRET protected).
3. Do not modify `modules/db.py` or `modules/database.py` without ARCHITECT + DATABASE agents active. These are the database foundation.
4. Automation/cron paths (`modules/automation_agent.py`, scheduler helpers, `blueprints/cron.py`) are tightly coupled — changes to one require reviewing the others.
5. All secrets and API keys go in `.env` locally and Vercel environment variables in production. Never hardcode. Never commit `.env`.
6. Branch naming: `feature/[ticket-id]-[short-description]` · `fix/[ticket-id]-[description]` · `hotfix/[description]`
7. `postpilot.db`, `.venv/`, and `__pycache__/` are gitignored — never track these.
8. The `/dev-login` route is gated behind `DEV_LOGIN_KEY` — confirm this env var is absent in Vercel production before every deploy.
9. Rate limiting uses Flask-Limiter. Redis (Upstash) is the target backend — memory fallback is dev only.
10. Sentry is activated by the presence of `SENTRY_DSN` — always set this in Vercel production.
11. Pricing truth is Free / Starter / Pro / Agency only (`plan_guard.py` + `billing.html`). Do not reintroduce a Growth tier.
12. Deploy target is Vercel only — do not add Render/Railway as primary hosting.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes (prod) | Supabase PostgreSQL connection string (pooler URL) |
| `FLASK_SECRET_KEY` | Yes | Flask session signing key — rotate if exposed |
| `TOKEN_ENCRYPTION_KEY` | Yes | Fernet key for encrypting OAuth tokens at rest |
| `OPENAI_API_KEY` | Yes | OpenAI API key for caption generation |
| `SUPABASE_URL` | Yes | Supabase project URL (magic-link auth) |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role (server only) |
| `META_APP_ID` / `FACEBOOK_APP_ID` | Yes | Meta developer app ID |
| `META_APP_SECRET` / `FACEBOOK_APP_SECRET` | Yes | Meta developer app secret |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `STRIPE_PRICE_*_{MONTHLY,ANNUAL}` | Yes | Starter / Pro / Agency price IDs |
| `CRON_SECRET` | Yes | Secret for Vercel Cron authentication |
| `SENTRY_DSN` | Yes (prod) | Sentry DSN for error monitoring |
| `REDIS_URL` | Yes (prod) | Upstash Redis URL for rate limiting |
| `DEV_LOGIN_KEY` | Dev only | Enables /dev-login — must be absent in production |
| `APP_ENV` | Yes | `development` or `production` |

See `.env.example` for the full list. Never commit values.

---

## Current Phase Context

```
Phase goal:         Phase 5 — Harden & go live: SEC keys, Vercel env, Redis,
                    alembic on prod, analytics verify, teams design (magic-link)
Definition of done: TODO.md §CRITICAL complete, Redis + Sentry live in prod,
                    Growth orphans gone, smoke test green
Blocking issues:    SEC-1 (TOKEN_ENCRYPTION_KEY / FLASK_SECRET_KEY rotation)
Next phase:         Phase 6 — Retention (morning prompt, location one-tap),
                    inbox, finish non-Meta publishers
```

Read `PLANNING.md` before proposing phase work. Do not restart “Phase 4 rebuild auth_manager.”

---

## Known Issues / Watch List

```
- SEC-1 CRITICAL: TOKEN_ENCRYPTION_KEY and FLASK_SECRET_KEY need rotation in Vercel.
  See TODO.md §CRITICAL.
- SEC-2: Ensure postpilot.db / .venv are not tracked — untrack commands in TODO.md.
- SEC-3: Confirm DEV_LOGIN_KEY absent in Vercel production.
- INFRA-5: Delete railway.toml (and any Render/Procfile leftovers) — Vercel only.
- OPS: CRON_SECRET must be set in Vercel for /api/cron/* (blueprint already registered).
- Pricing drift: any remaining Growth references in marketing copy must be removed.
```

---

## Agent Confirmation for This Repo

After loading this file, add to the `DISPATCH CONFIRMED` block:

```
Project AGENTS.md: loaded
Project: Post-Pilot
Stack: Python 3.11 · Flask 3.x · Supabase · Vercel · OpenAI
Phase: 5 — Harden & go live
Project rules active: 12 overrides
Known issues noted: yes — SEC-1 critical; plan docs rebasing required if drift returns
```

---

*Version: 1.1 | Extends: ShadowWalkerNC/.github/AGENTS.md | Repo: [Post-Pilot](https://github.com/ShadowWalkerNC/Post-Pilot)*
