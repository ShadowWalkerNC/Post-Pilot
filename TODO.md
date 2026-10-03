# Post-Pilot — Task List
*Last updated: 2026-08-10 — Security audit doc on main; C1–C6 remediations in #12*

Priority levels: 🔴 Critical (stop-ship) · 🟠 High · 🟡 Medium · 🟢 Low

**Phase source of truth:** `PLANNING.md` · **Checkbox tracker:** `ROADMAP.md`

---

## 🔴 CRITICAL — Security (code fixes)

Full write-up: [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md)

- [x] **C1** CSRF re-enabled on session APIs; `static/js/csrf.js` + template meta
- [x] **C2** `/v1` IDOR — user API keys bound to key owner (`_resolve_scoped_user_id`)
- [x] **C3** Fail closed if `TOKEN_ENCRYPTION_KEY` missing/invalid in production
- [x] **C4** Untracked `.venv` and `__pycache__` from git
- [x] **C5** `get_db` imports fixed → `modules.database`
- [x] **C6** `POST /api/setup_tokens` always `410 Gone` (OAuth-only; aligned with Wave A)

Still open (ops / configuration in production dashboard):
- [x] Confirm `DEV_LOGIN_KEY` absent in production
- [x] Set stable `TOKEN_ENCRYPTION_KEY` / `FLASK_SECRET_KEY` / `CRON_SECRET` in Railway
- [x] H1 rate limits on login + generate/publish
- [x] H2 SSRF allowlist for media URLs (`modules/validator.py`)
- [x] H3 escape XSS in `static/embed.js`

---

## 🟢 LIVE PRODUCTION (Railway)

- [x] Production Docker container deployed and active on Railway
- [x] Public Domain: `https://postpilotops.up.railway.app` (HTTP 200 OK)
- [x] Integrated in-process APScheduler background scheduler worker active (`ENABLE_BACKGROUND_SCHEDULER=true`)
- [x] All 508 unit and integration tests passing

---

## 🔴 CRITICAL — Manual go-live checklist (Phase 5)

### STEP 1 · Secure keys generated & injected into Railway
- [x] `FLASK_SECRET_KEY` injected
- [x] `TOKEN_ENCRYPTION_KEY` injected
- [x] `CRON_SECRET` injected
- [x] `ENABLE_BACKGROUND_SCHEDULER=true` injected
- [x] `APP_ENV=production` injected
```bash
# Flask secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Fernet encryption key for platform tokens
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Cron secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### STEP 2 · Add to Vercel Environment Variables
- [ ] `FLASK_SECRET_KEY` → output from Step 1
- [ ] `TOKEN_ENCRYPTION_KEY` → Fernet key from Step 1
- [ ] `CRON_SECRET` → urlsafe token from Step 1
- [ ] `OPENAI_API_KEY` → from https://platform.openai.com
- [ ] `STRIPE_PRICE_STARTER_MONTHLY` / `STRIPE_PRICE_STARTER_ANNUAL`
- [ ] `STRIPE_PRICE_PRO_MONTHLY` / `STRIPE_PRICE_PRO_ANNUAL`
- [ ] `STRIPE_PRICE_AGENCY_MONTHLY` / `STRIPE_PRICE_AGENCY_ANNUAL`
- [ ] `REDIS_URL` — Upstash Redis URL
- [ ] `SENTRY_DSN` — production error tracking
- [ ] Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `DATABASE_URL` — Supabase Postgres pooler URL
- [ ] Meta / Stripe / mail vars per `.env.example`

> Do **not** create Growth price env vars — product tiers are Free / Starter / Pro / Agency only.

### STEP 3 · Add to GitHub Actions Secrets
- [ ] Repo → Settings → Secrets and variables → Actions
- [ ] `CI_TOKEN_ENCRYPTION_KEY` → same Fernet key used in Vercel

### STEP 4 · Run DB migrations
```bash
DATABASE_URL=your_postgres_connection_string alembic upgrade head
```
> Applies through `0008_inbox` (includes `0003_drop_password_hash`, `0006_events_hours`, `0008_inbox`).

### STEP 5 · Security check
- [ ] Confirm `DEV_LOGIN_KEY` is **absent or empty** in Vercel production
- [ ] Re-encrypt existing platform token rows if `TOKEN_ENCRYPTION_KEY` changed

### STEP 6 · Git cleanup (if binaries still tracked)
```bash
git rm --cached postpilot.db .venv __pycache__ -r --ignore-unmatch
git commit -m "chore: untrack .db, .venv, __pycache__"
git push
```

### STEP 7 · Deploy + smoke test
- [ ] Fresh Vercel redeploy after env vars are set
- [ ] `/login` → magic link → dashboard
- [ ] `/schedule` → add a Special
- [ ] Cron generate with `Authorization: Bearer <CRON_SECRET>`
- [ ] Confirm automation/post history row written
- [ ] `/billing` → Free / Starter ($19) / Pro ($49) / Agency ($99)
- [ ] Connect one platform (Facebook or Google)

---

## 🟠 HIGH — Phase 5 code hardening (see `docs/PRODUCT_AUDIT.md`)

- [x] Remove Growth orphan from Stripe maps / user limit dicts / env docs
- [x] Register `embed_bp` in `blueprints/__init__.py`
- [x] Wave A: User/session, Stripe subscription kwargs, post_history logging, business profile save
- [x] Wave A: Cron GET+POST, get_db rewire, Fernet prod hard-fail, plan escalation fix
- [x] Wave A: `check_post_limit()` on publish/push-all; disable `/api/setup_tokens`
- [x] Wave B: Magic-link auth UI + landing pricing honesty + schedule standalone
- [x] Untrack `.venv` from git (SEC-2)
- [x] Delete `railway.toml` (Vercel-only deploy)
- [x] Delete leftover non-Vercel deploy configs (`railway.toml`, etc.) when confirmed unused
- [x] Agent activity log page — show `automation_log` rows
- [x] Confirm `CRON_SECRET` set in Vercel prod (blueprint already registered)
- [x] Fix `tests/conftest.py` (`app.init_db` missing) so CI smoke suite boots
- [x] Schema migration aligning Alembic `subscription_tier` ↔ live `plan` columns

---

## 🟠 HIGH — Phase 6: Inbox

- [x] Alembic migration — `inbox_items` table (`0008_inbox.py`)
- [x] `modules/comment_poller.py` — FB + IG comments on recent posts
- [x] `modules/reply_agent.py` — AI draft reply, tone-matched
- [x] Inbox blueprint + template — approve / edit / skip (`blueprints/inbox.py`, `templates/inbox.html`)
- [x] `vercel.json` — `/api/cron/poll_comments` every 15 min

---

## 🟠 HIGH — Phase 6: Retention

- [x] Morning daily prompt (email at user-set time + `/api/cron/daily_prompt` + `vercel.json`)
- [x] Location one-tap post (`POST /api/location/one_tap` + `modules/location_service.py`)
- [ ] Embed slug choose/confirm in onboarding + dashboard preview/copy UX
  - Note: `embed_api.py` + `static/embed.js` already ship; polish slug UX remains

---

## 🟡 MEDIUM

- [ ] Add `/schedule` link to dashboard sidebar nav (if missing)
- [ ] Replace remaining `print()` with `app.logger`
- [ ] Verify analytics against live Meta insights

---

## 🟢 LOW

- [ ] Redis-backed caching for hot DB queries
- [ ] Favicon (`static/favicon.ico`)
- [ ] Mobile-responsive dashboard nav
- [ ] Bulk reschedule / drag-and-drop calendar view

---

## ✅ COMPLETED

- [x] CI pipeline — `.github/workflows/ci.yml` (lint + pytest + coverage)
- [x] Stripe webhook handler — `billing_manager.py` (5 Stripe events)
- [x] Tests — `test_smoke.py`, `test_p0_fixes.py`, `test_validator.py`, `conftest.py`
- [x] MCP server — `mcp/server.py`
- [x] Blueprints registered (auth, billing, api, website, pages, cron, specials, events, hours, embed, v1)
- [x] Events + hours CRUD + migration `0006_events_hours`
- [x] `automation_agent.py` reads specials + events + hours
- [x] `schedule.html` tabbed UI (Specials / Events / Hours)
- [x] `plan_guard.py` — Free/Starter/Pro/Agency limits
- [x] `billing.html` — $0 / $19 / $49 / $99 with annual toggle
- [x] Specials table + CRUD + agent
- [x] Vercel Cron — `/api/cron/generate` + `/api/cron/publish`
- [x] Public embed — `blueprints/embed_api.py` + `static/embed.js`
- [x] Token encryption — `auth_manager.py`
- [x] OpenAI generation — `ai_generator.py` + `platform_adapter.py`
- [x] Magic-link auth — Supabase (`blueprints/auth.py`)
- [x] Migration `0003_drop_password_hash`
- [x] Docs rebased — `PLANNING.md` / `ROADMAP.md` / `PRICING.md` aligned to live stack (2026-08-08)
