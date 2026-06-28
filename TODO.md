# Post-Pilot — Task List
*Last updated: 2026-06-28 — UPA session (automation agent + publisher cleanup)*

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

### SEC-2 · Remove binary files from git tracking (run locally)
- [x] `.gitignore` covers `*.db`, `.venv/`, `__pycache__/`
- [ ] **Run locally and push:**
  ```bash
  git rm --cached postpilot.db .venv __pycache__ -r --ignore-unmatch
  git commit -m "chore: untrack .db, .venv, __pycache__"
  git push
  ```

### SEC-3 · Confirm /dev-login is disabled in production
- [ ] **Confirm `DEV_LOGIN_KEY` is absent or empty in Vercel production env vars**

---

## 🟠 HIGH PRIORITY

### INFRA-1 · Confirm production redeploy is live
- [ ] Trigger fresh Vercel redeploy after rotating keys
- [ ] Smoke test: visit `/login`, request magic link
- [ ] Check Vercel Cron tab — confirm both `/api/cron/generate` and `/api/cron/publish` are listed

### INFRA-2 · Add Redis for real rate limiting
- [ ] Provision Upstash Redis (free tier — https://upstash.com)
- [ ] Add `REDIS_URL` to Vercel environment variables

### INFRA-6 · Scheduler — Vercel Cron
- [x] `blueprints/cron.py` — `/api/cron/publish` (every minute)
- [x] `blueprints/cron.py` — `/api/cron/generate` (every hour) — calls AutomationAgent
- [x] `vercel.json` updated — both cron jobs registered
- [x] `cron_bp` registered in `blueprints/__init__.py` with CSRF exemption
- [ ] **Add `CRON_SECRET` to Vercel environment variables:**
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] Redeploy and confirm Vercel Cron tab shows both jobs

### INFRA-7 · Automation Agent
- [x] `modules/automation_agent.py` — full autonomous generation loop
- [x] `alembic/versions/0004_automation_log.py` — audit trail table
- [x] Content rotation: daily_special → location → general → repeat
- [x] 4-hour minimum gap between autonomous posts per user
- [x] Optimal post times: 8 AM (location), 11 AM (daily_special), 5 PM (general)
- [x] Per-platform captions stored in `post_history.results` JSON for publisher
- [ ] **Apply migration:** `alembic upgrade head`
- [ ] **Add `OPENAI_API_KEY` to Vercel environment variables** (if not already set)
- [ ] Test: manually POST `/api/cron/generate` with correct `Authorization` header
- [ ] Future: pull `special` from a dedicated specials table (currently hardcoded)

---

## 🟡 MEDIUM PRIORITY

### DEV-1 · CI pipeline
- [x] `.github/workflows/ci.yml` hardened
- [ ] Add `CI_TOKEN_ENCRYPTION_KEY` to GitHub Actions secrets

### DEV-2 · Error monitoring
- [x] Sentry wired in `app.py`
- [ ] Sign up at https://sentry.io, add `SENTRY_DSN` to Vercel

### DB-1 · Drop password_hash
- [x] Migration `0003_drop_password_hash.py` written
- [ ] `grep -r "password_hash" . --include="*.py"` — verify zero matches
- [ ] `alembic upgrade head`

### DB-2 · Automation log table
- [x] Migration `0004_automation_log.py` written
- [ ] `alembic upgrade head` (apply after 0003)

### AUTOMATION-1 · Specials table
- [ ] Design `specials` table: user_id, item_name, description, available_date
- [ ] AutomationAgent reads today’s special instead of using hardcoded placeholder

### AUTOMATION-2 · Agent activity dashboard
- [ ] `/dashboard/automation` page — show `automation_log` rows for current user
- [ ] Display: content_type, tone, scheduled_at, master_caption preview, status

---

## 🟢 LOW PRIORITY

### PERF-1 · Caching layer
- [ ] Add Redis-backed caching via `flask-caching` for 3 most-called DB queries

### OPS-1 · Structured logging
- [ ] Replace `print()` statements with `app.logger` calls

### UX-1 · Favicon
- [ ] Add `favicon.ico` to `static/` and `<link rel="icon">` to `base.html`

---

## ✅ COMPLETED

- [x] INFRA-7: `automation_agent.py` — autonomous content generation + scheduling loop
- [x] INFRA-7: `0004_automation_log.py` migration written
- [x] INFRA-6: Vercel Cron — `/api/cron/generate` (hourly) + `/api/cron/publish` (every minute)
- [x] INFRA-5: Deleted `railway.toml`, `render.yaml`, `nixpacks.toml`, `Procfile`
- [x] INFRA-6 (code): `cron_bp` registered in `blueprints/__init__.py` with CSRF exemption
- [x] Publisher: LinkedIn and Pinterest stubs removed
- [x] Publisher: `_update_website` fixed — now writes to DB instead of ephemeral filesystem
- [x] Publisher: Added `timeout=15` to all `requests` calls
- [x] Publisher: `content_type` routing rules extended (daily_special, location, general)
- [x] DB-1: `0003_drop_password_hash.py` written
- [x] Sentry, CI, CORS, `/dev-login` guard, OAuth state namespacing, XSS fix
- [x] `AGENTS.md`, `ARCHITECTURE.md`, `DEVELOPMENT.md`, `README.md` all written
- [x] UPA v2.0 system fully set up in `.github/`
