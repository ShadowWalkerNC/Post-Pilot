# Post-Pilot — Task List
*Last updated: 2026-06-26 — UPA v1.0 Full Run*

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
- [x] **Resolved — `database.py` is a safe proxy to `db.py`**, not a duplicate
- [x] Architecture documented in `app.py` module docstring
- [ ] Confirm no direct SQLite file path references remain in code (search: `sqlite:///`, `postpilot.db`)

### INFRA-4 · Duplicate module ambiguity
- [x] **Resolved — all modules have distinct roles**, documented in `app.py` docstring:
  - `generator.py` — static template posts (no AI)
  - `ai_generator.py` — OpenAI caption generation
  - `post_generator.py` — orchestrator (template vs AI routing)
  - `analytics.py` — tombstone shim re-exporting from `analytics_client.py`
  - `meta_api.py` — low-level Graph API calls
  - `meta_client.py` — higher-level Meta client

### INFRA-5 · Consolidate deployment configuration
- [ ] Confirm Vercel is the chosen deployment platform
- [ ] Delete unused configs: `railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile`
- [ ] Create `DEPLOY.md` documenting the deployment target and process

### INFRA-6 · Resolve scheduler worker for serverless
**Decision needed:** Vercel Cron Jobs vs external worker (Railway / Render)
- [ ] **If Vercel Cron:** Add `crons` config to `vercel.json` + `/api/cron/publish` endpoint
- [ ] **If external worker:** Set up Railway/Render service, document in `DEPLOY.md`

---

## 🟡 MEDIUM PRIORITY

### DEV-1 · CI pipeline
- [x] `.github/workflows/ci.yml` exists
- [x] **Hardened:** now uses `secrets.CI_TOKEN_ENCRYPTION_KEY` instead of hardcoded value
- [x] **Added:** `ruff` lint step alongside `flake8`
- [x] **Added:** coverage reporting (`--cov` flags)
- [x] **Added:** all missing dummy env vars (Twitter, Supabase, Stripe webhook)
- [ ] **Add GitHub Actions secret:** Settings → Secrets → Actions → `CI_TOKEN_ENCRYPTION_KEY`
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```

### DEV-2 · Error monitoring (Sentry)
- [x] `sentry-sdk[flask]` already in `requirements.txt`
- [x] **Sentry wired in `app.py`** — initializes when `SENTRY_DSN` env var is set
- [x] `send_default_pii=False` — user PII never sent to Sentry
- [x] 20% performance tracing sample rate
- [ ] **Sign up at https://sentry.io** (free tier)
- [ ] **Add `SENTRY_DSN` to Vercel environment variables**

### DEV-3 · CORS
- [x] Localhost origins are dev-environment-only in `app.py`

### DB-1 · Clean up pp.users schema
- [ ] Write migration to drop `password_hash` column from `pp.users`
- [ ] Apply via Supabase SQL editor or migration tool
- [ ] Verify no code references `password_hash`

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

- [x] Sentry wired in `app.py` (activates when `SENTRY_DSN` is set)
- [x] CI hardened: `ruff` lint, GitHub Actions secret, coverage, all dummy env vars
- [x] Module architecture documented in `app.py` docstring
- [x] Dual-DB confusion resolved: `database.py` confirmed as safe proxy
- [x] `.gitignore` created
- [x] `.env` sanitized — all real secrets replaced with placeholders
- [x] CORS — localhost origins dev-only
- [x] `/dev-login` gated behind `DEV_LOGIN_KEY` env var
- [x] `DATABASE_URL` switched to Supabase pooler (fixes IPv6 on Vercel)
- [x] `pp.users` row created for `shadowwalkernc@gmail.com`
- [x] `password_hash` made nullable
- [x] `init_scheduler()` guarded to main process only
- [x] `@require_plan` applied to all premium routes
- [x] `check_platform_limit` enforced on `/api/push_all` and `/api/publish`
- [x] XSS in fallback site renderer fixed
- [x] OAuth state keys namespaced per-platform
- [x] `?limit=abc` ValueError fixed
- [x] Silent exceptions now log via `app.logger.exception()`
- [x] `import requests` moved to top-level
- [x] `WTF_CSRF_TIME_LIMIT` raised to 7200
- [x] `REDIS_URL` and `APP_ENV` added to `.env.example`
- [x] UPA v1.0, Light Mode, and Escalation Checklist added to `.github/`
