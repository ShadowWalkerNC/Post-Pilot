# Post-Pilot — Architecture

> **Purpose:** Complete technical reference for the Post-Pilot system. Read this before making any change to modules, database schema, environment variables, or integrations.
> **Maintained by:** Every agent session that changes behavior must update this file.
> **Last updated:** 2026-10-02

---

## System Overview

Post-Pilot is a multi-tenant SaaS application that generates AI-powered social media content for food and hospitality businesses and publishes it directly to Facebook and Instagram via the Meta Graph API. It runs as a Python Flask application deployed on Vercel (serverless), with Supabase (PostgreSQL) as the primary database and Vercel Cron for scheduled publishing.

```
User (browser)
    ↓ HTTPS
Vercel (serverless Flask)
    ├── Auth (magic link email)
    ├── Dashboard / Post Queue
    ├── AI Generation (→ LLM gateway: Muse/OpenAI/Gemini/Claude)
    ├── Publish (→ Meta Graph API)
    ├── Scheduling (→ Vercel Cron)
    ├── Billing (→ Stripe)
    └── Cron Endpoints (/api/cron/generate, /api/cron/publish)
         ↓
    Supabase (PostgreSQL + Auth)
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
| Auth | `auth.py` | `/login`, `/register`, `/auth/*`, `/dev-login` | Supabase magic link, OAuth connect callbacks |
| Pages | `pages.py` | `/`, `/dashboard`, `/generate`, … | HTML pages for the product UI |
| API | `api.py` | `/api/generate`, `/api/push_all`, … | JSON generate/publish/platform settings |
| Cron | `cron.py` | `/api/cron/generate`, `/api/cron/publish` | Vercel Cron — automation + scheduled publish |
| Billing | `billing.py` | `/billing`, `/billing/webhook` | Stripe checkout, portal, webhooks |
| Website | `website.py` | website hub routes | Hosted/website data editing |
| Embed | `embed_api.py` | `/api/embed/<slug>` | Public embed JSON (no auth) |
| Specials | `specials.py` | `/schedule`, `/api/specials/*` | Specials CRUD + schedule UI |
| Events | `events.py` | `/api/events/*` | Events CRUD |
| Hours | `hours.py` | `/api/hours/*` | Hours override CRUD |

---

### Modules (`modules/`)

Shared utilities. No Flask routes here. Called by blueprints.

| Module | File | Responsibility |
|---|---|---|
| DB | `database.py` / `db.py` | Connection helpers — treat as foundation |
| Auth tokens | `auth_manager.py` | Encrypted platform token store (Fernet) |
| Users | `user_manager.py` | User records for magic-link era |
| AI | `ai_generator.py` | Caption generation via LLM gateway + template fallback |
| Adapter | `platform_adapter.py` | Per-platform caption shaping (via LLM gateway) |
| Publisher | `publisher.py` | Publish router across platforms |
| Meta API | `meta_api.py` / `meta_client.py` | Meta Graph API client |
| Billing | `billing_manager.py` | Stripe lifecycle + webhooks |
| Plan gates | `plan_guard.py` | `@require_plan`, post/platform/location limits |
| Automation | `automation_agent.py` | Specials/events/hours → generated posts |

---

### AI gateway (`ai/`) — provider-agnostic LLM layer

One `LLMProvider` contract (`generate`/`stream`/`structured_output`/
`tool_call`/`capabilities`/`is_available`) with four transport-only adapters —
no business logic, lazy SDK imports only. See `docs/LLM_GATEWAY.md`.

| File | Responsibility |
|---|---|
| `ai/gateway.py` | `AIGateway` facade: router-ordered fallback, `health()`, `explain()` |
| `ai/router.py` | `AIRouter`: preferred → task route → default → fallback order |
| `ai/context.py` | `TaskRequirements`, `GatewayConfig.from_env()`, default task routes |
| `ai/providers/muse.py` | `MuseProvider`: local HTTP endpoint (stdlib only) |
| `ai/providers/openai.py` | `OpenAIProvider`: OpenAI SDK, also serves `codex` alias |
| `ai/providers/gemini.py` | `GeminiProvider`: `google-genai` SDK (optional dep) |
| `ai/providers/anthropic.py` | `ClaudeProvider`: `anthropic` SDK (optional dep), `Claude` alias |

Default task routes: content/marketing → Muse, anthropic; structured/analysis
→ gemini; coding/dev/admin → openai. Env: `AI_DEFAULT_PROVIDER`,
`AI_FALLBACK_ORDER`, `AI_TASK_ROUTES`, per-provider keys/models. No provider is
ever required — any available subset serves traffic.

---

### Core (`core/`) — canonical content + business context

| File | Responsibility |
|---|---|
| `core/content/pipeline.py` | Canonical content pipeline delegating to legacy generators |
| `core/business_brain/models.py` | Structured business context model |
| `core/business_brain/service.py` | `load_context()`: single source for brand/menu/hours/specials/events/media/posts/performance/rules |

---

### Skills (`skills/`) — provider-agnostic prompt packs

| Skill dir | Purpose |
|---|---|
| `skills/loader.py` | stdlib-only loader: discover, parse frontmatter, render `{{placeholders}}`. NEVER imports an LLM SDK. |
| `skills/special_post/` | Daily-special caption (caption + hook prompts, price/urgency rules) |
| `skills/event_campaign/` | 3-post event series (announce / reminder / last-call) |
| `skills/weekly_plan/` | 7-day content calendar in parseable `DAY | TYPE | ...` lines |
| `skills/review_reply/` | Sentiment-matched review replies (pairs with `reply_agent`) |
| `skills/brand_guard/` | Pre-publish audit pass (PASS/FAIL verdict + fix) |

Each skill = `SKILL.md` (frontmatter + docs) + `prompts/*.md` + `rules/*.md`.
Rendered text is sent to any provider by the caller (OpenAI, Anthropic, template fallback).

---

### MCP product tools (`mcp/tools/`) — data/actions for MCP clients

Thin wrappers that delegate to existing `modules/` services. No new business logic.

| Tool | Module | Delegates to | Permission |
|---|---|---|---|
| `business.get` | `mcp/tools/business.py` | `UserManager.get_business_profile` | read |
| `menu.get` | `mcp/tools/business.py` | `websites.section_data` via `modules/db.py` | read |
| `specials.list` | `mcp/tools/specials.py` | `specials` table via `modules/db.py` | read |
| `events.list` | `mcp/tools/events.py` | `events` table via `modules/db.py` | read |
| `content.generate` | `mcp/tools/content.py` | `ai_generator.generate_with_adaptations` | write (plan quota) |
| `content.schedule` | `mcp/tools/content.py` | `scheduler_worker.PostScheduler.schedule` | write |
| `post.publish` | `mcp/tools/publish.py` | `publisher.UniversalPublisher.push_all` | publish |
| `analytics.get` | `mcp/tools/analytics.py` | `analytics_client.Analytics` | read |
| `inbox.reply` | `mcp/tools/inbox.py` | `reply_agent.analyze_and_draft` (draft-only) | write |
| `business.update` | `mcp/tools/business.py` | `UserManager.save_business_profile` (merged) | write |
| `menu.list` / `menu.item_get` | `mcp/tools/business.py` | `menu.get` projection | read |
| `specials.get` | `mcp/tools/specials.py` | `specials` row by id | read |
| `events.get` | `mcp/tools/events.py` | `events` row by id | read |
| `hours.get` | `mcp/tools/hours.py` | `hours_overrides` table | read |
| `content.adapt` | `mcp/tools/content.py` | `PlatformAdapter.adapt_all` | write (plan quota) |
| `content.preview` | `mcp/tools/content.py` | adapt + counts/warnings | read |
| `post.cancel` / `post.status` | `mcp/tools/publish.py` | `PostScheduler` jobs | write / read |
| `analytics.top_posts` | `mcp/tools/analytics.py` | summary ranked by metric | read |
| `analytics.performance_summary` | `mcp/tools/analytics.py` | summary KPIs | read |
| `inbox.list` | `mcp/tools/inbox.py` | `InboxItem.list_by_user` | read |
| `inbox.approve_reply` | `mcp/tools/inbox.py` | Meta API + `mark_replied` | publish |
| `inbox.skip` | `mcp/tools/inbox.py` | `mark_skipped` | write |
| `media.list` / `media.get` | `mcp/tools/media.py` | `post_history` attachments | read |
| `brand.get` / `brand.validate` | `mcp/tools/brand.py` | profile + deterministic checks | read |
| `automation.run` | `mcp/tools/automation.py` | `automation_agent` per-user | write |
| `automation.status` | `mcp/tools/automation.py` | `automation_log` | read |
| `provider.list` / `provider.route` / `provider.health` | `mcp/tools/provider.py` | `ai/` gateway (no network) | read |

Full 33-tool reference: `docs/MCP_TOOLS.md`. Gateway reference: `docs/LLM_GATEWAY.md`.

Auth model: explicit `user_id` scope on every tool, owner/team only, secrets
never returned. Each tool module carries a `SPEC_*` dict with permission + auth
notes; `mcp/tools/__init__.py` exposes the `TOOL_SPECS` registry.
Import note: the PyPI `mcp` SDK shadows local `mcp/`; call
`modules/mcp_bootstrap.py::ensure_local_mcp_tools()` before importing
`mcp.tools.*` (see `mcp/server.py`). The pre-existing GitHub audit tools in
`mcp/server.py` are unchanged.

---

### Integrations (`integrations/`) — external adapters (no marketing logic)

| Package | Contents |
|---|---|
| `integrations/culinaryos/` | `client.py` (REST pull + webhook verify/parse), `contract.md` (ownership, transports, security, failure modes) |

Rule: adapters normalize external data into Post-Pilot shapes only.
Generation, scheduling, publishing, and analytics stay in `modules/` and skills.

---

## Data Flow

### Post Generation
```
User submits topic / tone / platforms
    → api.py POST /api/generate (or generate page)
    → modules/ai_generator.py + platform_adapter.py
    → OpenAI API (GPT-4o-mini)
    → Return master + per-platform adapted captions
```

### Manual Publish
```
User clicks Publish All
    → api.py POST /api/push_all
    → plan_guard / billing checks
    → modules/publisher.py → meta_api / platform clients
    → Update post history / status
```

### Scheduled Publish (Cron)
```
Vercel Cron fires
    → /api/cron/generate (hourly) and /api/cron/publish (* * * * *)
    → blueprints/cron.py verifies CRON_SECRET
    → automation_agent / scheduler publish path
    → Return 200 JSON summary
```

### Authentication (Magic Link)
```
User enters email → /login
    → Supabase Auth magic link email
    → User clicks link → auth confirm callback
    → Upsert user via user_manager
    → Flask-Login session
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
| `password_hash` | — | Removed by migration `0003_drop_password_hash` |
| `team_id` | FK → pp.teams NULL | Phase 5 — teams design (not fully shipped) |

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

### OpenAI
- **Model:** GPT-4o-mini (primary) via `OPENAI_API_KEY`
- **Usage:** `modules/ai_generator.py` + `modules/platform_adapter.py`
- **Prompt strategy:** Business context + content type + tone + per-platform rules
- **Fallback:** Template captions when OpenAI is unavailable

### Stripe
- **Products:** Starter ($19), Pro ($49), Agency ($99) — monthly + annual
- **Webhooks:** `/billing/webhook` — subscription + invoice events
- **Plan enforcement:** `@require_plan` in `modules/plan_guard.py`
- **Docs:** `PRICING.md` (must match `billing.html`)

### Vercel Cron
- **Schedules:** `/api/cron/generate` hourly; `/api/cron/publish` every minute
- **Auth:** `Authorization: Bearer CRON_SECRET`
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
| SEC-2 | Ensure postpilot.db + .venv stay untracked | 🔴 Critical |
| SEC-3 | Confirm DEV_LOGIN_KEY absent in Vercel production | 🔴 Critical |
| INFRA-5 | Delete railway.toml (and any Render/Procfile leftovers) — Vercel only | 🟡 Medium |
| OPS-CRON | Confirm CRON_SECRET set in Vercel (blueprint already registered) | 🟠 High |
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
