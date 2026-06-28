# Post-Pilot — Development Guide

> **Purpose:** Everything you need to run, develop, test, and deploy Post-Pilot. Read `ARCHITECTURE.md` first for system design context.
> **Last updated:** 2026-06-28

---

## Prerequisites

- Python 3.11+
- `pip` or `uv` (recommended for speed)
- Git
- A Supabase project (or use SQLite for local dev)
- A Vercel account (for deployment)
- A Meta Developer account (for Facebook/Instagram publishing)

---

## Local Setup

### 1. Clone the repo
```bash
git clone https://github.com/ShadowWalkerNC/Post-Pilot.git
cd Post-Pilot
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
Or with `uv` (faster):
```bash
uv pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
```
Open `.env` and fill in every variable. See the table below for what each one does.

### 5. Run database migrations
```bash
alembic upgrade head
```
This applies all migrations in `alembic/versions/` to your local SQLite database.

### 6. Start the development server
```bash
flask run
```
The app runs at `http://localhost:5000`.

---

## Environment Variable Guide

| Variable | Where to get it | Notes |
|---|---|---|
| `DATABASE_URL` | Supabase → Settings → Database → Connection string (pooler) | Use `postgresql+psycopg2://` prefix. Omit for SQLite local dev — app defaults to `postpilot.db` |
| `FLASK_SECRET_KEY` | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` | Keep secret. Rotate if exposed. |
| `TOKEN_ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | Fernet key. Rotate if exposed. |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys | |
| `META_APP_ID` | developers.facebook.com → Your App → Settings | |
| `META_APP_SECRET` | developers.facebook.com → Your App → Settings → Show | |
| `STRIPE_SECRET_KEY` | dashboard.stripe.com → Developers → API Keys | Use test key for dev |
| `STRIPE_WEBHOOK_SECRET` | dashboard.stripe.com → Webhooks → Signing secret | Use Stripe CLI for local webhook testing |
| `CRON_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Set this in Vercel too |
| `SENTRY_DSN` | sentry.io → Project → Settings → Client Keys | Omit in local dev to disable Sentry |
| `REDIS_URL` | upstash.com → Create database → REST URL | Omit in local dev — Flask-Limiter falls back to memory |
| `DEV_LOGIN_KEY` | Any string you choose | **Dev only.** Must be absent in Vercel production. Enables `/dev-login`. |
| `APP_ENV` | `development` or `production` | Controls behavior in several modules |
| `MAIL_SERVER` | Your SMTP provider | e.g. `smtp.gmail.com` |
| `MAIL_USERNAME` | Your email address | SMTP login |
| `MAIL_PASSWORD` | Your email app password | SMTP login — use app password, not account password |

---

## Running Tests

```bash
pytest
```

With coverage:
```bash
pytest --cov=. --cov-report=term-missing
```

Tests live in `tests/`. Add new tests for every new function, endpoint, or module.
CI runs the same command — if it passes locally it passes in CI.

**Required secret for CI:**
Add `CI_TOKEN_ENCRYPTION_KEY` to GitHub Actions secrets (a valid Fernet key).

---

## Linting

```bash
ruff check .
```

Fix automatically:
```bash
ruff check . --fix
```

CI runs `ruff` on every push. Fix all lint errors before pushing.

---

## Branching Rules

| Branch type | Naming | Notes |
|---|---|---|
| Feature | `feature/[ticket-id]-[short-description]` | e.g. `feature/INFRA-6-cron-registration` |
| Bug fix | `fix/[ticket-id]-[description]` | e.g. `fix/DB-1-drop-password-hash` |
| Hotfix | `hotfix/[description]` | Production emergency — narrow scope only |
| Docs | `docs/[description]` | Documentation-only changes |

- Branch from `main`.
- PR into `main`.
- All PRs must pass CI (ruff + pytest) before merge.
- Squash merge preferred for clean history.

---

## Alembic Migrations

All schema changes go through Alembic. Never modify the database directly in production.

**Create a new migration:**
```bash
alembic revision --autogenerate -m "describe what this migration does"
```

**Review the generated file** in `alembic/versions/` before applying. Auto-generate is not always correct.

**Apply migrations:**
```bash
alembic upgrade head
```

**Check current state:**
```bash
alembic current
```

**Rules:**
- Migrations are forward-only. No `alembic downgrade` in production without explicit approval.
- Every migration needs DATABASE agent review before push (per `AGENTS.md`).
- Migrations that affect existing data require a manual data migration plan.

---

## Vercel Deployment

See `DEPLOY.md` for the full deployment runbook.

**Quick reference:**
1. Push to `main` — Vercel auto-deploys.
2. All env vars must be set in Vercel dashboard before deploying.
3. Vercel Cron runs `/api/cron/publish` every minute — `CRON_SECRET` must be set.
4. Check Vercel Function Logs after deploy to confirm zero errors.
5. Smoke test: visit `/login` and request a magic link.

---

## Using SESSION_START with AI Agents

Every AI session on Post-Pilot should start with this context block. Copy, fill in, paste as your first message:

```
PROJECT: Post-Pilot
PHASE: 5 — Teams, Alembic migrations, Redis, analytics
LAST COMMIT: [paste last commit message or SHA]
MODE: full | quick
AGENT: Perplexity | Claude | Gemini
OPEN: SEC-1 (key rotation), INFRA-6 (register cron blueprint), [third open item]
SCOPE: [what you want to accomplish this session]
```

The agent loads `SESSION_START.md` from `ShadowWalkerNC/.github` and is immediately calibrated to:
- Post-Pilot's stack (Python · Flask · Supabase · Vercel)
- Current phase and open items
- UPA process rules (plan before build, atomic commits, docs follow code)
- Which agents to activate per the task type

**iPhone shortcut:** Use `;upa` text replacement (see `BOOT.md` in `.github` repo) to expand the full context block on mobile.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `Cannot assign requested address` in Vercel logs | Supabase connection string format issue | Use pooler URL with `postgresql+psycopg2://` prefix |
| Flask-Limiter error on startup | `REDIS_URL` not set | Omit `REDIS_URL` in local dev — Limiter falls back to memory |
| Magic link not arriving | SMTP config wrong | Check `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` in `.env` |
| `/api/cron/publish` returns 403 | `CRON_SECRET` mismatch | Verify `CRON_SECRET` matches in `.env` and Vercel env vars |
| Sentry not capturing errors | `SENTRY_DSN` not set | Add `SENTRY_DSN` to Vercel env vars |
| Alembic `target database is not up to date` | Unapplied migrations | Run `alembic upgrade head` |
| `postpilot.db` committed to git | .gitignore not applied | Run SEC-2 untrack commands from `TODO.md` |

---

*Canonical location: `ShadowWalkerNC/Post-Pilot/DEVELOPMENT.md`*
*Read alongside: `ARCHITECTURE.md`, `AGENTS.md`, `TODO.md`, `DEPLOY.md`*
