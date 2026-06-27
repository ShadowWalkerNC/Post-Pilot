# Post-Pilot — Task List
*Last updated: 2026-06-26 — UPA v2.0 Assessment*

Priority levels: 🔴 Critical (stop-ship) · 🟠 High · 🟡 Medium · 🟢 Low

---

## 🔴 CRITICAL — Do These First

### SEC-1 · Rotate TOKEN_ENCRYPTION_KEY and remove .env from git
The `.env` file was committed to the public repository and contained a live Fernet key.

- [x] `.gitignore` created — `.env`, `*.db`, `.venv/`, `__pycache__/` all covered
- [x] `.env` replaced with a safe placeholder-only file
- [ ] **YOU MUST DO:** Generate a new Fernet key locally:
  ```
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- [ ] **YOU MUST DO:** Update `TOKEN_ENCRYPTION_KEY` in Vercel environment variables with the new key
- [ ] **YOU MUST DO:** Update `FLASK_SECRET_KEY` in Vercel environment variables with a new strong random value
- [ ] **YOU MUST DO:** Re-encrypt all existing rows in `platform_tokens` with the new key (write a one-time migration script if tokens exist)
- [ ] **YOU MUST DO:** Audit git history: `git log --all --full-history -- .env` — if real API keys were ever in history, use `git filter-repo` to scrub them

### SEC-2 · Remove binary and generated files from git
- [x] `.gitignore` now covers `*.db`, `.venv/`, `__pycache__/`, `*.pyc`
- [ ] **YOU MUST DO locally:** `git rm --cached postpilot.db .venv/ __pycache__/ -r --ignore-unmatch`
- [ ] Commit and push the removal

### SEC-3 · /dev-login is already safely gated
- [x] `/dev-login` checks `DEV_LOGIN_KEY` env var — returns 403 if not set
- [x] `.env` now ships with `DEV_LOGIN_KEY=` (empty = disabled)
- [ ] Confirm `DEV_LOGIN_KEY` is NOT set in Vercel production env vars
- [ ] After beta launch: delete the `/dev-login` route entirely

---

## 🟠 HIGH PRIORITY

### INFRA-1 · Confirm production redeploy is live and working
- [ ] Trigger a redeploy on Vercel (pooler `DATABASE_URL` was set Wednesday — confirm it took effect)
- [ ] Hit `/dev-login?email=shadowwalkernc@gmail.com&uid=c5c46a84-c7ee-4079-a590-5451ec306e8d&key=devtest123` and confirm 200 + session cookie
- [ ] Check Vercel logs — confirm zero `Cannot assign requested address` errors

### INFRA-2 · Add Redis for real rate limiting
Without Redis, rate limiting resets on every cold start — effectively useless on Vercel serverless.
- [ ] Provision Upstash Redis (free tier — https://upstash.com)
- [ ] Add `REDIS_URL` to Vercel environment variables
- [ ] Confirm Flask-Limiter picks it up on next deploy (already wired in `app.py`)

### INFRA-3 · Resolve dual-database architecture
`modules/database.py` (SQLite) and `modules/db.py` (PostgreSQL) both exist. This split causes silent routing failures.
- [ ] Audit every file that imports from `database.py` vs `db.py`
- [ ] Migrate all callers to `db.py` (PostgreSQL / Supabase pooler)
- [ ] Delete `modules/database.py`
- [ ] Delete `postpilot.db` references from all code
- [ ] Run a full smoke test after migration

### INFRA-4 · Resolve duplicate module ambiguity
Three overlapping AI/generation modules and two analytics modules exist.
- [ ] Decide: `generator.py` vs `ai_generator.py` vs `post_generator.py` — pick one or clarify distinct roles
- [ ] Decide: `analytics.py` (stub, 329B) vs `analytics_client.py` (13KB) — delete the stub or promote it
- [ ] Clarify or merge: `meta_api.py` vs `meta_client.py`

### INFRA-5 · Consolidate deployment configuration
`Procfile`, `railway.toml`, `render.yaml`, `nixpacks.toml`, and `vercel.json` all exist.
- [ ] Confirm Vercel is the chosen deployment platform
- [ ] Delete `railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile` if not needed
- [ ] Document the deployment target in `DEPLOY.md`

### INFRA-6 · Resolve scheduler worker for serverless
`modules/scheduler_worker.py` cannot run as a persistent process on Vercel.
- [ ] Decide: Vercel Cron Jobs vs a separate worker on Railway/Render
- [ ] If Vercel Cron: add cron config to `vercel.json` and a `/api/cron/publish` endpoint
- [ ] If external worker: document the worker service in `DEPLOY.md`

---

## 🟡 MEDIUM PRIORITY

### DEV-1 · Add GitHub Actions CI pipeline
- [ ] Create `.github/workflows/ci.yml`
- [ ] Run `pytest` on every push to `main` and on all PRs
- [ ] Add `CI_TOKEN_ENCRYPTION_KEY` as a GitHub Actions secret
- [ ] Add a lint step (`ruff` recommended)

### DEV-2 · Add error monitoring
- [ ] Sign up for Sentry (free tier)
- [ ] Add `sentry-sdk[flask]` to `requirements.txt`
- [ ] Initialize Sentry in `app.py` with `SENTRY_DSN` env var
- [ ] Add `SENTRY_DSN` to Vercel environment variables

### DEV-3 · CORS — localhost origins now dev-only
- [x] CORS updated in `app.py` — localhost origins only added when `FLASK_ENV=development`

### DB-1 · Clean up pp.users schema
- [ ] Write a migration to drop `password_hash` column from `pp.users`
- [ ] Apply via Supabase migration or `execute_sql`
- [ ] Verify no code still references `password_hash`

### DB-2 · Add GitHub Actions secret
- [ ] Go to GitHub repo → Settings → Secrets → Actions → New repository secret
- [ ] Name: `CI_TOKEN_ENCRYPTION_KEY` — value: a freshly generated test-only Fernet key

---

## 🟢 LOW PRIORITY

### PERF-1 · Add caching layer
- [ ] Identify 3 most-called DB queries (user profile, platform tokens, posts list)
- [ ] Add Redis-backed caching with short TTLs using `flask-caching`

### OPS-1 · Structured logging
- [ ] Replace `print()` statements with `app.logger` calls throughout
- [ ] Add request ID to every log line

### OPS-2 · Rollback runbook
- [ ] Document what to do if a deploy breaks production
- [ ] Document Supabase point-in-time restore process

### UX-1 · Add favicon
- [ ] Add `favicon.ico` and `favicon.png` to `static/`
- [ ] Add `<link rel="icon">` to `base.html`

---

## ✅ COMPLETED

- [x] `.gitignore` created (covers `.env`, `*.db`, `.venv/`, `__pycache__/`, `node_modules/`)
- [x] `.env` sanitized — all real secrets replaced with placeholders
- [x] CORS updated — localhost origins are now dev-environment-only
- [x] `/dev-login` confirmed safely gated behind `DEV_LOGIN_KEY` env var
- [x] Switched `DATABASE_URL` to Supabase pooler (fixes IPv6 error on Vercel)
- [x] `pp.users` row created for `shadowwalkernc@gmail.com`
- [x] `password_hash` made nullable in `pp.users`
- [x] `init_scheduler()` guarded to main process only
- [x] `@require_plan` applied to all premium routes
- [x] `check_platform_limit` enforced on `/api/push_all` and `/api/publish`
- [x] XSS in fallback site renderer fixed
- [x] OAuth state keys namespaced per-platform
- [x] `?limit=abc` ValueError fixed in `api_post_history`
- [x] Silent exception swallowing now logs via `app.logger.exception()`
- [x] `import requests` moved to top-level
- [x] `WTF_CSRF_TIME_LIMIT` raised to 7200
- [x] `REDIS_URL` and `APP_ENV` added to `.env.example`
