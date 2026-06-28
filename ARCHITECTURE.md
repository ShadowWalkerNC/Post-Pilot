# Post-Pilot — Architecture

> **Purpose:** Complete technical reference for the Post-Pilot system. Read this before making any change to modules, database schema, environment variables, or integrations.
> **Maintained by:** Every agent session that changes behavior must update this file.
> **Last updated:** 2026-06-28

---

## System Overview

Post-Pilot is a multi-tenant SaaS application that generates AI-powered social media content for food and hospitality businesses and publishes it directly to Facebook and Instagram via the Meta Graph API. It runs as a Python Flask application deployed on Vercel (serverless), with Supabase (PostgreSQL) as the primary database and Vercel Cron for scheduled publishing.

```
User (browser)
    ↓ HTTPS
Vercel (serverless Flask)
    ├── Auth (magic link email)
    ├── Dashboard / Post Queue
    ├── AI Generation (→ Anthropic Claude)
    ├── Publish (→ Meta Graph API)
    ├── Scheduling (→ Vercel Cron)
    ├── Billing (→ Stripe)
    └── Cron Endpoint (/api/cron/publish)
         ↓ every minute
    Supabase (PostgreSQL)
         └── pp.users, pp.posts, pp.platforms,
             pp.schedules, pp.plans, pp.teams
```

---

## Module Map

### Flask Application Entry Point

**`app.py`**
- Flask app factory
- Registers all blueprints
- Initializes SQLAlchemy, Flask-Limiter, Sentry, CSRF, Mail
- Loads configuration from environment variables
- Sets up Jinja2 template globals

---

### Blueprints (`blueprints/`)

Each blueprint owns one domain. Routes, forms, and view logic live here. Business logic lives in `modules/`.

| Blueprint | File | Routes | Responsibility |
|---|---|---|---|
| Auth | `auth.py` | `/login`, `/auth/magic`, `/logout` | Magic link generation, session management, user creation |
| Dashboard | `dashboard.py` | `/`, `/dashboard` | Post queue view, platform status, recent activity |
| Generate | `generate.py` | `/generate` | Claude-powered post generation UI and API |
| Publish | `publish.py` | `/publish` | Manual and scheduled Meta Graph API publishing |
| Scheduler | `scheduler.py` | `/schedule` | Post scheduling interface, schedule CRUD |
| Cron | `cron.py` | `/api/cron/publish` | Vercel Cron endpoint — calls `_publish_scheduled_posts()` |
| Billing | `billing.py` | `/billing`, `/billing/webhook` | Stripe subscription, plan enforcement, webhook handler |
| Onboarding | `onboarding.py` | `/onboarding` | New user setup: connect platform, choose plan |
| Settings | `settings.py` | `/settings` | Account, platform tokens, notification prefs |
| Admin | `admin.py` | `/admin` | Internal tools — user management, system health |

---

### Modules (`modules/`)

Shared utilities. No Flask routes here. Called by blueprints.

| Module | File | Responsibility |
|---|---|---|
| Database engine | `db.py` | SQLAlchemy engine, session factory, declarative base |
| DB proxy | `database.py` | Backward-compat proxy to `db.py` — do not bypass |
| ORM Models | `models.py` | All database models (see DB Schema below) |
| AI | `ai.py` | Claude API wrapper, system prompt management, post generation |
| Meta API | `meta_api.py` | Meta Graph API client — publish, token refresh, page listing |
| Scheduler utils | `scheduler_utils.py` | `_publish_scheduled_posts()` — called by cron endpoint |
| Auth utils | `auth_utils.py` | JWT generation/validation, magic link creation, session helpers |
| Billing utils | `billing_utils.py` | Stripe API helpers, `@require_plan` decorator, plan limits |
| Rate limit | `rate_limit.py` | Flask-Limiter configuration, Redis integration |

---

## Data Flow

### Post Generation
```
User fills generation form
    → generate.py POST /generate
    → modules/ai.py: build_prompt(business_context, platform, tone)
    → Anthropic Claude API (claude-3-5-sonnet)
    → Return generated post text
    → Save as Draft post to pp.posts
    → Redirect to dashboard
```

### Manual Publish
```
User clicks Publish
    → publish.py POST /publish
    → modules/billing_utils.py: @require_plan check
    → modules/meta_api.py: publish_post(platform_token, post_content)
    → Meta Graph API: POST /{page-id}/feed
    → Update pp.posts.status = 'published', published_at = now()
    → Update dashboard
```

### Scheduled Publish (Cron)
```
Vercel Cron fires every minute
    → GET /api/cron/publish (Authorization: Bearer CRON_SECRET)
    → blueprints/cron.py: verify HMAC header
    → modules/scheduler_utils.py: _publish_scheduled_posts()
        → Query pp.schedules WHERE scheduled_at <= now() AND status = 'pending'
        → For each: modules/meta_api.py: publish_post()
        → Update pp.schedules.status = 'published' | 'failed'
    → Return 200 JSON summary
```

### Authentication (Magic Link)
```
User enters email → /login
    → modules/auth_utils.py: generate_magic_link(email)
    → Send email via Flask-Mail (SMTP)
    → User clicks link → /auth/magic?token=...
    → modules/auth_utils.py: validate_token(token)
    → Create or get pp.users row
    → Set Flask session
    → Redirect to dashboard or onboarding
```

---

## Database Schema

Primary database: **Supabase PostgreSQL**. Schema prefix: `pp`.
Local dev: SQLite (`postpilot.db`) — same models, different engine URL.

### `pp.users`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `email` | VARCHAR UNIQUE | User identifier |
| `created_at` | TIMESTAMP | |
| `last_login` | TIMESTAMP | |
| `plan_id` | FK → pp.plans | Current subscription plan |
| `stripe_customer_id` | VARCHAR | Stripe customer reference |
| `password_hash` | VARCHAR NULL | ⚠️ Deprecated — pending migration to drop (DB-1) |
| `team_id` | FK → pp.teams NULL | Phase 5 — teams feature |

### `pp.posts`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → pp.users | |
| `platform_id` | FK → pp.platforms | |
| `content` | TEXT | Generated post body |
| `status` | ENUM | `draft`, `scheduled`, `published`, `failed` |
| `created_at` | TIMESTAMP | |
| `published_at` | TIMESTAMP NULL | Set on successful publish |
| `meta_post_id` | VARCHAR NULL | Meta Graph API post ID after publish |

### `pp.platforms`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | FK → pp.users | |
| `platform_type` | ENUM | `facebook`, `instagram` |
| `page_id` | VARCHAR | Meta page/account ID |
| `access_token` | TEXT | Encrypted via TOKEN_ENCRYPTION_KEY (Fernet) |
| `token_expires_at` | TIMESTAMP NULL | |
| `connected_at` | TIMESTAMP | |
| `is_active` | BOOLEAN | |

### `pp.schedules`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `post_id` | FK → pp.posts | |
| `user_id` | FK → pp.users | |
| `scheduled_at` | TIMESTAMP | When to publish |
| `status` | ENUM | `pending`, `published`, `failed`, `cancelled` |
| `created_at` | TIMESTAMP | |
| `error_message` | TEXT NULL | Set on failure |

### `pp.plans`
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | VARCHAR | `free`, `starter`, `pro`, `agency` |
| `post_limit` | INTEGER | Monthly post limit |
| `platform_limit` | INTEGER | Number of connected platforms allowed |
| `price_monthly` | DECIMAL | Stripe price |
| `stripe_price_id` | VARCHAR | Stripe price object ID |

### `pp.teams` *(Phase 5 — in development)*
| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `name` | VARCHAR | Team name |
| `owner_id` | FK → pp.users | Team creator/owner |
| `created_at` | TIMESTAMP | |
| `plan_id` | FK → pp.plans | Team-level plan |

---

## Platform Integrations

### Meta Graph API
- **Auth:** OAuth 2.0 — user grants page permissions, tokens stored encrypted in `pp.platforms`
- **Publish:** `POST /{page-id}/feed` (Facebook), `POST /{ig-user-id}/media` + `/media_publish` (Instagram)
- **Token refresh:** Long-lived tokens (60 days) — refresh logic in `modules/meta_api.py`
- **Rate limits:** Meta enforces per-page limits — respect 200 calls/hour
- **Docs:** `API_NOTES.md`, `V1_API.md`

### Anthropic Claude
- **Model:** `claude-3-5-sonnet` (primary), `claude-opus-4` (heavy tasks)
- **Usage:** Post generation in `modules/ai.py`
- **Prompt strategy:** System prompt with business context + platform + tone + brand voice
- **Cost control:** Token limits enforced per request

### Stripe
- **Products:** Starter, Pro, Agency plans
- **Webhooks:** `/billing/webhook` — handles `customer.subscription.updated`, `invoice.payment_succeeded`, `invoice.payment_failed`
- **Plan enforcement:** `@require_plan` decorator in `modules/billing_utils.py`
- **Docs:** `PRICING.md`

### Vercel Cron
- **Schedule:** Every minute (`* * * * *`)
- **Endpoint:** `GET /api/cron/publish`
- **Auth:** `Authorization: Bearer CRON_SECRET` header, HMAC constant-time comparison
- **Config:** `vercel.json`

### Sentry
- **SDK:** `sentry-sdk[flask]`
- **Activation:** Presence of `SENTRY_DSN` env var
- **Captures:** Unhandled exceptions, performance traces

---

## Environment Variables Reference

See `AGENTS.md §Environment Variables` for the full annotated table.
See `.env.example` for the key list without values.

**Critical rotation needed (SEC-1):**
- `TOKEN_ENCRYPTION_KEY` — Fernet key, must be rotated in Vercel env vars
- `FLASK_SECRET_KEY` — Flask session key, must be rotated in Vercel env vars

---

## Known Technical Debt

| ID | Description | Priority |
|---|---|---|
| SEC-1 | TOKEN_ENCRYPTION_KEY + FLASK_SECRET_KEY need rotation in Vercel | 🔴 Critical |
| SEC-2 | postpilot.db + .venv tracked in git — need untrack + history audit | 🔴 Critical |
| SEC-3 | Confirm DEV_LOGIN_KEY absent in Vercel production | 🔴 Critical |
| DB-1 | Drop password_hash column from pp.users via Alembic migration | 🟡 Medium |
| INFRA-5 | Delete railway.toml, render.yaml, nixpacks.toml, Procfile | 🟡 Medium |
| INFRA-6 | Register cron blueprint in blueprints/__init__.py + set CRON_SECRET | 🟠 High |
| PERF-1 | Add Redis caching for top 3 DB queries | 🟢 Low |
| OPS-1 | Replace print() with app.logger throughout | 🟢 Low |

---

## CI/CD Pipeline

**GitHub Actions** (`.github/workflows/ci.yml`):
- Trigger: push to main, all pull requests
- Steps: `ruff` lint → `pytest` with coverage
- Secrets needed: `CI_TOKEN_ENCRYPTION_KEY` (GitHub Actions secrets)

**Vercel deployment:**
- Trigger: push to main branch
- Build: Python serverless functions
- Env vars: set in Vercel dashboard (never in code)
- Cron: defined in `vercel.json`

---

*Canonical location: `ShadowWalkerNC/Post-Pilot/ARCHITECTURE.md`*
*Read alongside: `TODO.md`, `AGENTS.md`, `PLANNING.md`, `DEPLOY.md`*
