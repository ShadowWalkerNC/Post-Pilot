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
Phase:        Phase 5 — Teams, Alembic migrations, analytics, Redis rate limiting
Priority:     Active
```

---

## Tech Stack

```
Language:     Python 3.11+
Framework:    Flask 3.x
Database:     Supabase (PostgreSQL via SQLAlchemy + psycopg2) + SQLite (local dev)
Hosting:      Vercel (serverless + Vercel Cron)
Key APIs:     Meta Graph API (Facebook/Instagram), Anthropic Claude, Stripe, Sentry
CI/CD:        GitHub Actions (.github/workflows/ci.yml) — ruff lint + pytest
Observability: Sentry (via SENTRY_DSN env var)
Auth:         Magic link email (no passwords)
Payments:     Stripe (subscription plans)
```

---

## Repository Structure

```
Post-Pilot/
  app.py               ← Flask app factory, blueprint registration, Sentry init
  blueprints/          ← Flask blueprints (one file per domain)
    auth.py            ← Magic link auth, session management
    dashboard.py       ← Main dashboard, post queue, platform overview
    generate.py        ← AI post generation (Claude)
    publish.py         ← Meta Graph API publish logic
    scheduler.py       ← Post scheduling interface
    cron.py            ← Vercel Cron endpoint (/api/cron/publish)
    billing.py         ← Stripe subscription management
    onboarding.py      ← New user setup flow
    settings.py        ← Account and platform settings
    admin.py           ← Internal admin tools
  modules/             ← Shared utilities and services
    db.py              ← SQLAlchemy engine, session factory, base models
    database.py        ← Safe proxy to db.py (backward compat)
    models.py          ← ORM models: User, Post, Platform, Schedule, Plan
    ai.py              ← Claude API wrapper, prompt management
    meta_api.py        ← Meta Graph API client
    scheduler_utils.py ← Scheduling logic (_publish_scheduled_posts)
    auth_utils.py      ← JWT, magic link generation, session helpers
    billing_utils.py   ← Stripe helpers, plan enforcement
    rate_limit.py      ← Flask-Limiter config, Redis integration
  templates/           ← Jinja2 HTML templates
  static/              ← CSS (Tailwind), JS, images
  alembic/             ← Database migrations (forward-only)
    versions/          ← Migration files
  tests/               ← pytest test suite
  mcp/                 ← Post-Pilot MCP server (planned)
  .github/
    workflows/
      ci.yml           ← GitHub Actions: ruff + pytest + coverage
    UPA_V1.md          ← (canonical copy in ShadowWalkerNC/.github)
    UPA_LIGHT_MODE.md
    UPA_ESCALATION_CHECKLIST.md
  vercel.json          ← Vercel deployment + Cron config
  requirements.txt     ← Pinned Python dependencies
  .env.example         ← All required env vars (no values)
  ARCHITECTURE.md      ← System design, data flows, DB schema
  TODO.md              ← Current open work — read every session
  CHANGELOG.md         ← What changed and when
  PLANNING.md          ← Full UPA phase planning document
  DEPLOY.md            ← Deployment runbook
  V1_API.md            ← External API documentation
```

---

## Active Agents for This Project

```
Always active:    COHERENCE · SECURITY · DOCS
Default on-demand: ENGINEER · DATABASE · DEVOPS · QA
Load when needed: ARCHITECT (system design changes), AI (Claude/prompt work),
                  PRODUCT (roadmap/scope), UX (template/UI work)
Rarely needed:    BUSINESS (load only for pricing/go-to-market work)
```

---

## Project-Specific Rules

1. All Supabase/Alembic migrations must be reviewed by DATABASE agent before any push. Migrations are forward-only — no rollbacks without explicit approval.
2. Every new blueprint route requires `@require_plan` or `@login_required` — no unauthenticated endpoints except `/login`, `/auth/*`, and `/api/cron/publish` (CRON_SECRET protected).
3. Do not modify `modules/db.py` or `modules/database.py` without ARCHITECT + DATABASE agents active. These are the database foundation.
4. `modules/scheduler_utils.py` and `blueprints/cron.py` are tightly coupled — changes to either require reviewing both.
5. All secrets and API keys go in `.env` locally and Vercel environment variables in production. Never hardcode. Never commit `.env`.
6. Branch naming: `feature/[ticket-id]-[short-description]` · `fix/[ticket-id]-[description]` · `hotfix/[description]`
7. `postpilot.db`, `.venv/`, and `__pycache__/` are gitignored — never track these.
8. The `/dev-login` route is gated behind `DEV_LOGIN_KEY` — confirm this env var is absent in Vercel production before every deploy.
9. Rate limiting uses Flask-Limiter. Redis (Upstash) is the target backend — SQLite fallback is dev only.
10. Sentry is activated by the presence of `SENTRY_DSN` — always set this in Vercel production.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | Supabase PostgreSQL connection string (pooler URL) |
| `FLASK_SECRET_KEY` | Yes | Flask session signing key — rotate if exposed |
| `TOKEN_ENCRYPTION_KEY` | Yes | Fernet key for encrypting OAuth tokens at rest |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for post generation |
| `META_APP_ID` | Yes | Meta developer app ID |
| `META_APP_SECRET` | Yes | Meta developer app secret |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `CRON_SECRET` | Yes | HMAC secret for Vercel Cron authentication |
| `SENTRY_DSN` | Yes (prod) | Sentry DSN for error monitoring |
| `REDIS_URL` | Yes (prod) | Upstash Redis URL for rate limiting |
| `DEV_LOGIN_KEY` | Dev only | Enables /dev-login — must be absent in production |
| `APP_ENV` | Yes | `development` or `production` |
| `MAIL_SERVER` | Yes | SMTP server for magic link emails |
| `MAIL_USERNAME` | Yes | SMTP username |
| `MAIL_PASSWORD` | Yes | SMTP password |

See `.env.example` for the full list. Never commit values.

---

## Current Phase Context

```
Phase goal:         Phase 5 — Teams & multi-user, Alembic migration cleanup,
                    Redis rate limiting (Upstash), analytics dashboard, performance audit
Definition of done: Teams CRUD complete, all migrations clean, Redis live in prod,
                    analytics page live, SEC-1/SEC-2/SEC-3 manual steps confirmed done
Blocking issues:    SEC-1 (TOKEN_ENCRYPTION_KEY rotation) must be done before Phase 5 begins
Next phase:         Phase 6 — Public launch prep, onboarding flow, marketing site
```

---

## Known Issues / Watch List

```
- SEC-1 CRITICAL: TOKEN_ENCRYPTION_KEY and FLASK_SECRET_KEY need rotation in Vercel
  environment variables. See TODO.md §SEC-1 for exact steps.
- SEC-2: postpilot.db and .venv are tracked in git — run untrack commands from TODO.md §SEC-2.
- INFRA-6: Vercel Cron blueprint (cron.py) needs to be registered in blueprints/__init__.py
  and CRON_SECRET set in Vercel env vars before cron runs.
- DB-1: password_hash column still exists in pp.users — migration needed to drop it.
- INFRA-5: railway.toml, render.yaml, nixpacks.toml, Procfile should be deleted
  (Vercel is the only deployment target).
- scheduler_utils.py and cron.py are tightly coupled — changes to either affect both.
```

---

## Agent Confirmation for This Repo

After loading this file, add to the `DISPATCH CONFIRMED` block:

```
Project AGENTS.md: loaded
Project: Post-Pilot
Stack: Python 3.11 · Flask 3.x · Supabase · Vercel
Phase: 5 — Teams, Alembic, Redis, analytics
Project rules active: 10 overrides
Known issues noted: yes — SEC-1 critical, INFRA-6 pending registration
```

---

*Version: 1.0 | Extends: ShadowWalkerNC/.github/AGENTS.md | Repo: [Post-Pilot](https://github.com/ShadowWalkerNC/Post-Pilot)*
