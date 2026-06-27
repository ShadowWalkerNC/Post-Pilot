# Post-Pilot — Task List
*Last updated: 2026-06-26 — UPA v2.0 Assessment*

Priority levels: 🔴 Critical (stop-ship) · 🟠 High · 🟡 Medium · 🟢 Low

---

## 🔴 CRITICAL — Do These First

### SEC-1 · Rotate TOKEN_ENCRYPTION_KEY and remove .env from git
The `.env` file is committed to the public repository and contains a live Fernet key.
Anyone who has cloned this repo can decrypt every stored OAuth token.

- [ ] `git rm --cached .env`
- [ ] Add `.env` to `.gitignore` (confirm it's there)
- [ ] Generate a new Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- [ ] Update `TOKEN_ENCRYPTION_KEY` in Vercel environment variables
- [ ] Re-encrypt all existing rows in `platform_tokens` with the new key (write a one-time migration script)
- [ ] Rotate `FLASK_SECRET_KEY` in Vercel environment variables
- [ ] Audit full git history for any real API keys: `git log --all --full-history -- .env`
- [ ] Force-push or use `git filter-repo` to scrub `.env` from history if real keys were ever committed

### SEC-2 · Remove binary and generated files from git
- [ ] `git rm --cached postpilot.db`
- [ ] `git rm -r --cached .venv`
- [ ] `git rm -r --cached __pycache__`
- [ ] Confirm `.gitignore` includes: `*.db`, `.venv/`, `__pycache__/`, `*.pyc`, `.env`
- [ ] Commit and push the cleanup

### SEC-3 · Remove or hard-gate /dev-login in production
A debug auth bypass is live on the production domain.
- [ ] Add `DEV_LOGIN_ENABLED=false` to Vercel environment variables
- [ ] Wrap the `/dev-login` route so it returns 404 unless `DEV_LOGIN_ENABLED=true` AND `FLASK_ENV != production`
- [ ] Confirm the route returns 404 on `post-pilot-opal.vercel.app` after redeploy

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
- [ ] Decide: `generator.py` vs `ai_generator.py` vs `post_generator.py` — pick one or clarify their distinct roles in code comments
- [ ] Decide: `analytics.py` (stub, 329B) vs `analytics_client.py` (13KB) — delete the stub or promote it
- [ ] Remove or clearly separate `meta_api.py` vs `meta_client.py`

### INFRA-5 · Consolidate deployment configuration
`Procfile`, `railway.toml`, `render.yaml`, `nixpacks.toml`, and `vercel.json` all exist. Pick one target.
- [ ] Confirm Vercel is the chosen deployment platform
- [ ] Delete `railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile` if not needed
- [ ] Document the deployment target in `DEPLOY.md`

### INFRA-6 · Resolve scheduler worker for serverless
`modules/scheduler_worker.py` cannot run as a persistent process on Vercel.
- [ ] Decide: Vercel Cron Jobs (simple, limited) vs a separate worker on Railway/Render (reliable)
- [ ] If Vercel Cron: add `vercel.json` cron config and a `/api/cron/publish` endpoint
- [ ] If external worker: document the worker service in `DEPLOY.md` and add it to the deployment checklist

---

## 🟡 MEDIUM PRIORITY

### DEV-1 · Add GitHub Actions CI pipeline
- [ ] Create `.github/workflows/ci.yml`
- [ ] Run `pytest` on every push to `main` and on all PRs
- [ ] Add `CI_TOKEN_ENCRYPTION_KEY` as a GitHub Actions secret (generate a test-only key)
- [ ] Add a lint step (`flake8` or `ruff`)

### DEV-2 · Add error monitoring
- [ ] Sign up for Sentry (free tier)
- [ ] Add `sentry-sdk[flask]` to `requirements.txt`
- [ ] Initialize Sentry in `app.py` with `SENTRY_DSN` env var
- [ ] Add `SENTRY_DSN` to Vercel environment variables

### DEV-3 · Fix CORS for production
`localhost` origins are in the production CORS allowlist.
- [ ] Make CORS origins environment-conditional — only add localhost origins when `FLASK_ENV=development`

### DB-1 · Clean up pp.users schema
`password_hash` column exists but is now nullable after the magic-link migration. The schema is misleading.
- [ ] Write a migration to drop `password_hash` column from `pp.users`
- [ ] Apply via Supabase migration tool
- [ ] Verify no code still references `password_hash`

### DB-2 · Add GitHub secret for CI
- [ ] Go to GitHub repo → Settings → Secrets → Actions → New repository secret
- [ ] Name: `CI_TOKEN_ENCRYPTION_KEY`
- [ ] Value: a freshly generated test-only Fernet key

---

## 🟢 LOW PRIORITY / NICE TO HAVE

### PERF-1 · Add caching layer
- [ ] Identify the 3 most-called DB queries (likely user profile, platform tokens, posts list)
- [ ] Add Redis-backed caching with short TTLs (30–60s) using `flask-caching`

### OPS-1 · Add structured logging
- [ ] Replace `print()` statements with `app.logger` calls throughout
- [ ] Add request ID to every log line for traceability

### OPS-2 · Write a rollback runbook
- [ ] Document what to do if a deploy breaks production
- [ ] Document how to restore from Supabase point-in-time backup

### UX-1 · Add favicon
Both production and preview deployments log 404s for `/favicon.ico` and `/favicon.png` on every page load.
- [ ] Add a `favicon.ico` and `favicon.png` to `static/`
- [ ] Add `<link rel="icon">` to `base.html`

---

## ✅ COMPLETED

- [x] Switched `DATABASE_URL` from direct connection to Supabase pooler (fixes IPv6 error on Vercel)
- [x] `pp.users` row created for `shadowwalkernc@gmail.com` (UUID: `c5c46a84-c7ee-4079-a590-5451ec306e8d`)
- [x] `password_hash` made nullable in `pp.users` (magic-link users have no password)
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
