# Post-Pilot — Task List
*Last updated: 2026-06-28 — UPA session (gap analysis + GitHub fixes)*

Priority levels: 🔴 Critical (stop-ship) · 🟠 High · 🟡 Medium · 🟢 Low

---

## 🔴 CRITICAL — Manual Steps Required (You Must Do These)

### SEC-1 · Rotate TOKEN_ENCRYPTION_KEY
- [x] `.gitignore` created — `.env`, `*.db`, `.venv/`, `__pycache__/` covered
- [x] `.env` replaced with safe placeholders
- [ ] **Generate new Fernet key locally:**
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- [ ] **Update `TOKEN_ENCRYPTION_KEY` in Vercel environment variables**
- [ ] **Update `FLASK_SECRET_KEY` in Vercel environment variables**
- [ ] **Re-encrypt existing `platform_tokens` rows** (write one-time migration if real tokens exist)
- [ ] **Audit git history:** `git log --all --full-history -- .env`
  - If real keys appear: use `git filter-repo` to scrub history

### SEC-2 · Remove binary files from git tracking (run locally)
- [x] `.gitignore` covers `*.db`, `.venv/`, `__pycache__/`
- [ ] **Run locally and push:**
  ```bash
  git rm --cached postpilot.db .venv __pycache__ -r --ignore-unmatch
  git commit -m "chore: untrack .db, .venv, __pycache__"
  git push
  ```

### SEC-3 · Confirm /dev-login is disabled in production
- [x] `/dev-login` safely gated behind `DEV_LOGIN_KEY` env var (returns 403 if unset)
- [ ] **Confirm `DEV_LOGIN_KEY` is absent or empty in Vercel production env vars**

---

## 🟠 HIGH PRIORITY

### INFRA-1 · Confirm production redeploy is live
- [ ] Trigger a fresh Vercel redeploy after rotating keys above
- [ ] Check Vercel logs — confirm zero `Cannot assign requested address` errors
- [ ] Smoke test: visit `/login` and request a magic link

### INFRA-2 · Add Redis for real rate limiting
- [ ] Provision Upstash Redis (free tier — https://upstash.com)
- [ ] Add `REDIS_URL` to Vercel environment variables
- [ ] Redeploy — Flask-Limiter will pick it up automatically

### INFRA-3 · Dual-database architecture
- [x] Resolved — `database.py` is a safe proxy to `db.py`
- [x] Architecture documented in `app.py` module docstring
- [ ] Confirm no direct SQLite references remain (search: `sqlite:///`, `postpilot.db`)

### INFRA-4 · Duplicate module ambiguity
- [x] Resolved — all modules have distinct roles, documented in `app.py` docstring

### INFRA-6 · Scheduler worker for serverless
- [x] **Resolved — Vercel Cron implemented**
- [x] `blueprints/cron.py` — `/api/cron/publish` endpoint with `CRON_SECRET` auth
- [x] `vercel.json` updated — cron runs every minute (`* * * * *`)
- [x] Endpoint calls `_publish_scheduled_posts()` directly (no APScheduler needed)
- [x] Constant-time HMAC comparison for auth header (timing attack safe)
- [x] `cron_bp` registered in `blueprints/__init__.py` with CSRF exemption
- [ ] **Add `CRON_SECRET` to Vercel environment variables:**
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] Redeploy and confirm Vercel Cron tab shows the `/api/cron/publish` job

---

## 🟡 MEDIUM PRIORITY

### DEV-1 · CI pipeline
- [x] `.github/workflows/ci.yml` hardened with `ruff`, GitHub secret, coverage
- [ ] Add `CI_TOKEN_ENCRYPTION_KEY` to GitHub Actions secrets

### DEV-2 · Error monitoring (Sentry)
- [x] `sentry-sdk[flask]` in `requirements.txt`
- [x] Sentry wired in `app.py` (activates when `SENTRY_DSN` is set)
- [ ] Sign up at https://sentry.io, add `SENTRY_DSN` to Vercel environment variables

### DEV-3 · CORS
- [x] Localhost origins are dev-environment-only

### DB-1 · Clean up users schema — drop password_hash
- [x] `password_hash` made nullable (prior session)
- [x] Migration `0003_drop_password_hash.py` written and pushed
- [ ] **Verify no code references `password_hash`:**
  ```bash
  grep -r "password_hash" . --include="*.py"
  ```
  Expected: zero matches (excluding alembic history)
- [ ] **Apply migration:**
  ```bash
  alembic upgrade head
  ```
- [ ] Verify column is gone: check schema in Supabase SQL editor

---

## 🟢 LOW PRIORITY

### PERF-1 · Add caching layer
- [ ] Identify 3 most-called DB queries
- [ ] Add Redis-backed caching via `flask-caching`

### OPS-1 · Structured logging
- [ ] Replace `print()` statements with `app.logger` calls
- [ ] Add request ID to every log line

### OPS-2 · Rollback runbook
- [ ] Document deploy rollback procedure
- [ ] Document Supabase point-in-time restore steps

### UX-1 · Favicon
- [ ] Add `favicon.ico` and `favicon.png` to `static/`
- [ ] Add `<link rel="icon">` to `base.html`

---

## ✅ COMPLETED

- [x] INFRA-5: Deleted `railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile` — Vercel is the only deployment target
- [x] INFRA-6 (code): `cron_bp` registered in `blueprints/__init__.py` with CSRF exemption
- [x] INFRA-6 (impl): Vercel Cron implemented (`blueprints/cron.py` + `vercel.json`)
- [x] DB-1 (migration): `0003_drop_password_hash.py` written — apply with `alembic upgrade head`
- [x] Sentry wired in `app.py`
- [x] CI hardened: `ruff`, GitHub Actions secret, coverage reporting
- [x] Module architecture documented in `app.py` docstring
- [x] Dual-DB confusion resolved
- [x] `.gitignore` created
- [x] `.env` sanitized
- [x] CORS — localhost origins dev-only
- [x] `/dev-login` gated behind `DEV_LOGIN_KEY`
- [x] `DATABASE_URL` switched to Supabase pooler
- [x] `pp.users` row created
- [x] `password_hash` made nullable
- [x] `init_scheduler()` guarded to main process only
- [x] `@require_plan` applied to all premium routes
- [x] `check_platform_limit` enforced
- [x] XSS in fallback site renderer fixed
- [x] OAuth state keys namespaced per-platform
- [x] `?limit=abc` ValueError fixed
- [x] Silent exceptions now log via `app.logger.exception()`
- [x] `import requests` moved to top-level
- [x] `WTF_CSRF_TIME_LIMIT` raised to 7200
- [x] `REDIS_URL` and `APP_ENV` added to `.env.example`
- [x] `AGENTS.md` completed with full stack, rules, env vars, known issues
- [x] `ARCHITECTURE.md` created — module map, data flows, DB schema, integrations
- [x] `DEVELOPMENT.md` created — local setup, env var guide, branching, troubleshooting
- [x] `README.md` rewritten — current stack, structure, docs links, session bootstrap
- [x] UPA v1.0, Light Mode, and Escalation Checklist added to `.github/`
