# Post-Pilot Security & Project Audit

**Date:** 2026-08-06  
**Scope:** Full repository review (auth, API, tokens, cron, billing, XSS/CSRF, git hygiene, infra)  
**Method:** Static code review of Flask app, blueprints, modules, templates, Vercel config, git tracking  
**Status:** Findings only — no production secrets rotated in this pass  

---

## Executive summary

Post-Pilot has solid foundations in places (parameterized SQL, Stripe webhook signature verification, OAuth state tokens, Fernet token encryption *when keyed correctly*, cron HMAC when `CRON_SECRET` is set). It is **not production-hardened**. Several issues are stop-ship: CSRF exemption of session-authenticated APIs, `/v1` IDOR via `user_id`, ephemeral encryption keys on serverless, and a large tracked `.venv` tree.

| Severity | Count |
|----------|------:|
| Critical | 6 |
| High     | 8 |
| Medium   | 10 |
| Low / hygiene | 8 |

---

## Critical

### C1 — CSRF protection disabled on session-authenticated mutating APIs

**Where:** `blueprints/__init__.py` exempts `api_bp`, `specials_bp`, `events_bp`, `hours_bp` from CSRF.

**Impact:** Any site a logged-in user visits can forge `POST /api/publish`, `/api/push_all`, `/api/setup_tokens`, `/api/delete_post`, specials/events/hours mutations using the victim’s session cookie. `/api/setup_tokens` can overwrite OAuth tokens.

**Fix:** Remove CSRF exemption for browser-session blueprints. Send `X-CSRFToken` (or form token) from dashboard JS. Keep exemptions only for `cron_bp`, `stripe_webhook_bp`, and true Bearer-token `/v1` routes.

---

### C2 — `/v1` IDOR: callers can act as any `user_id`

**Where:** `modules/api_manager.py` — `generate_post`, `publish_post`, `generate_and_publish`, `get_history`, `get_site_config`, `set_published`.

```python
user_id = body.get('user_id') or g.api_user_id
```

**Impact:** A valid user API key (or SRN secret) can publish, read history, or toggle website publish for **any** user by supplying their UUID. Cross-tenant takeover of social publishing.

**Fix:** For user API keys, **always** bind `user_id = g.api_user_id` and ignore client-supplied IDs. For SRN secret, require an allowlist / explicit service ACL, not arbitrary UUID.

---

### C3 — `TOKEN_ENCRYPTION_KEY` falls back to ephemeral Fernet key

**Where:** `modules/auth_manager.py` (lines 33–46).

**Impact:** On Vercel cold starts without a stable env var, a new key is generated → all stored OAuth tokens fail to decrypt → publish/cron break silently or with crypto errors. Invalid keys are also replaced with another ephemeral key instead of failing closed.

**Fix:** Refuse to start in production if `TOKEN_ENCRYPTION_KEY` is missing/invalid. Never generate a runtime key in prod. Confirm SEC-1 rotation steps in `TODO.md`.

---

### C4 — Entire `.venv` committed to git (~13k files)

**Where:** `git ls-files '.venv'` ≈ 13,181 paths (Windows-style `Lib/site-packages`). Also thousands of `__pycache__/*.pyc` tracked despite `.gitignore`.

**Impact:** Repo bloat, accidental secret leakage from local env baked into packages, noisy diffs, supply-chain confusion. `.gitignore` is correct but files were force-added before ignore rules.

**Fix:**
```bash
git rm -r --cached .venv blueprints/__pycache__ modules/__pycache__
git commit -m "chore: untrack .venv and __pycache__"
```

---

### C5 — `from app import get_db` but `app.py` does not define `get_db`

**Where:** `blueprints/api.py`, `specials.py`, `events.py`, `hours.py`, `embed_api.py`.

**Impact:** Runtime `ImportError` on scheduled posts, history, platform settings, specials/events/hours. Dead or silently failing features; error handlers may mask this.

**Fix:** `from modules.database import get_db` everywhere (or re-export `get_db` from `app.py`).

---

### C6 — Manual token injection endpoint

**Where:** `POST /api/setup_tokens` (`blueprints/api.py`).

**Impact:** Authenticated (and CSRF-exempt — see C1) clients can write arbitrary platform access tokens. Combined with CSRF, an attacker can plant their tokens or wipe victim tokens. Prefer OAuth-only flows.

**Fix:** Remove or heavily restrict to admin/dev; never accept raw tokens from the browser in production.

---

## High

### H1 — No rate limits on auth or API

**Where:** `app.py` — `Limiter(..., default_limits=[])`. No `@limiter.limit` on `/login`, `/register`, magic link, or `/api/*`.

**Impact:** Magic-link email bombing, OTP spam, AI generation cost abuse, publish spam.

**Fix:** e.g. `5/minute` on login/register; tiered limits on `/api/generate*` and `/api/publish*`. Require `REDIS_URL` in production (memory:// is per-instance and ineffective on serverless).

---

### H2 — SSRF via user-controlled media URLs

**Where:** `modules/publisher.py` `_publish_twitter` does `requests.get(image_url)`. Meta/TikTok paths also pass `image_url`/`video_url`/`file_url` to third parties (second-order SSRF).

**Impact:** Server-side fetch of internal metadata endpoints (`169.254.169.254`, `localhost`, private RFC1918). Validator only checks `http/https` + netloc — no blocklist.

**Fix:** Allowlist public HTTPS hosts; block private/link-local/metadata IPs after DNS resolve; prefer upload-to-blob then serve known URLs.

---

### H3 — Stored XSS in embed widget

**Where:** `static/embed.js` interpolates API fields into `innerHTML` without escaping (`caption`, hours keys/values, service name/desc/price, `image_url` in `src`).

**Impact:** A compromised or malicious business profile can XSS any site embedding the widget (session/cookie theft on that origin).

**Fix:** Use `textContent` / `createElement`; escape HTML; sanitize URLs (`https:` only).

---

### H4 — DEV_LOGIN timing-unsafe compare + remember cookie

**Where:** `blueprints/auth.py` — `request.args.get('key') != dev_key`; `login_user(..., remember=True)`.

**Impact:** If `DEV_LOGIN_KEY` leaks into production, full account impersonation via query string (also lands in logs/Referer). Non-constant-time compare.

**Fix:** Confirm env absent in Vercel prod (TODO Step 5). Use `hmac.compare_digest`. Prefer short-lived session without `remember=True`.

---

### H5 — Session cookie flags not hardened

**Where:** `app.py` — no `SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE`, `REMEMBER_COOKIE_*`.

**Impact:** Session leakage over HTTP / some CSRF assistance if SameSite unset.

**Fix:** In production set `Secure=True`, `HttpOnly=True`, `SameSite='Lax'` (or `Strict` where viable).

---

### H6 — Cron routes are POST-only; Vercel Cron invokes GET

**Where:** `vercel.json` cron paths + `blueprints/cron.py` `methods=['POST']`.

**Impact:** Scheduled generate/publish may never run (405). Operational outage, not just security.

**Fix:** Accept `GET` and `POST`, or configure invocation to match. Keep Bearer `CRON_SECRET` check. Note: `/api/cron/health` is unauthenticated and enumerates endpoints (low).

---

### H7 — `SRN_SECRET` compared with `==`

**Where:** `modules/api_manager.py` `require_api_key`.

**Impact:** Timing side-channel on shared service secret. Prefer `hmac.compare_digest`. Empty `SRN_SECRET` correctly disables that path; ensure it is never accidentally set to a short value.

---

### H8 — Analytics accepts client-supplied Meta tokens

**Where:** `api_analytics` — `token = tokens.get('facebook_token') or data.get('access_token')` (same for `page_id` / `ig_id`).

**Impact:** Authenticated user can point analytics at arbitrary tokens/pages (abuse Meta API via your app, confuse audit trails). Prefer stored tokens only.

---

## Medium

### M1 — `check_post_limit()` never enforced on publish

**Where:** `modules/plan_guard.py` defines limits; TODO notes wiring missing; `api_publish` / `api_push_all` / cron generate ignore monthly caps.

**Impact:** Billing bypass / cost overrun.

### M2 — `embed_api` blueprint not registered

**Where:** `blueprints/embed_api.py` exists; `register_blueprints` never imports `embed_bp`.

**Impact:** Public embed API dead; docs/`embed.js` call a missing route (or 404).

### M3 — Website hub / disconnect CSRF mismatch

**Where:** `website_bp` and `auth.disconnect` are **not** CSRF-exempt, but frontend `fetch()` calls omit CSRF tokens (`website_hub.html`, `connect.html`). Disconnect uses GET-style `fetch` against a POST route.

**Impact:** Features broken in real CSRF-on mode; teams may “fix” by exempting more routes (widening C1).

### M4 — DATABASE_URL partially logged

**Where:** `modules/db.py` logs `DATABASE_URL[:40]` — often includes credentials.

**Impact:** Secret leakage to logs/Sentry/Vercel log drains.

### M5 — `app.run(debug=True)` in entrypoint

**Where:** `app.py` `__main__`. Low risk on Vercel (not used), high if someone runs the module in a shared host.

### M6 — Public site IDOR-ish enumeration

**Where:** `GET /site/<user_id>` — predictable UUID/path discloses published site content. Prefer opaque slugs + rate limits.

### M7 — Privacy/legal copy outdated

**Where:** `templates/legal/privacy.html`, `register.html` still describe passwords/bcrypt while auth is magic-link only.

**Impact:** Compliance/trust issue, not direct exploit.

### M8 — CORS allowlist includes specific Vercel hosts only

**Where:** `app.py`. Fine if intentional; custom domains need explicit addition. No credentials mode review documented.

### M9 — Error responses leak exception strings

**Where:** cron 500 returns `str(e)`; `/v1` returns `str(e)` on several handlers.

**Impact:** Internal path/DB detail disclosure.

### M10 — No security headers

Missing CSP, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`, HSTS (may be at Vercel edge — confirm).

---

## Low / hygiene

| ID | Issue |
|----|--------|
| L1 | `railway.toml` still present; AGENTS.md says Vercel-only (INFRA-5) |
| L2 | AGENTS.md still lists INFRA-6 cron registration as open; cron **is** registered — docs drift |
| L3 | Env naming drift: `FACEBOOK_APP_*` vs docs `META_APP_*`; Stripe price env names inconsistent between `.env.example` and `billing_manager.py` |
| L4 | Tests (`test_smoke.py`) still assert password auth — suite likely stale vs magic-link |
| L5 | `_uid()` fallback to `'default'` documented as dangerous if `@login_required` missed |
| L6 | Requirements unpinned (`flask>=3.0.0`) — reproducibility / supply chain |
| L7 | MCP server can read arbitrary repo files given `GITHUB_TOKEN` — expected for ops tool; protect token scope |
| L8 | Demo dashboard routes `/demo` unauthenticated — intentional marketing surface; ensure no live tokens |

---

## What looks solid

- SQL uses bound parameters (`?` / `%s`) — no obvious SQLi in reviewed paths  
- Stripe webhooks use `Webhook.construct_event`  
- OAuth flows use `secrets.token_urlsafe` state and validate on callback  
- Cron rejects requests when `CRON_SECRET` unset (`hmac.compare_digest`)  
- Sentry `send_default_pii=False`  
- Production refuses start without `FLASK_SECRET_KEY` / Supabase URL+anon key when `VERCEL_ENV` / production Flask env set  
- Post deletes scoped by `user_id`  
- API keys stored as SHA-256 hashes, not plaintext  

---

## Recommended remediation order

1. **Immediate (ops):** Confirm `DEV_LOGIN_KEY` absent in Vercel; set stable `TOKEN_ENCRYPTION_KEY`, `FLASK_SECRET_KEY`, `CRON_SECRET`, `REDIS_URL`, `SENTRY_DSN` (TODO Steps 1–5).  
2. **Immediate (code):** Fix C2 IDOR; re-enable CSRF for session APIs (C1); fail closed on encryption key (C3); untrack `.venv` (C4); fix `get_db` imports (C5).  
3. **Next:** Rate limits (H1), SSRF controls (H2), embed XSS (H3), session cookie flags (H5), cron GET/POST (H6).  
4. **Then:** Wire `check_post_limit`, register or remove embed blueprint, align CSRF on website/disconnect, scrub logs, security headers, doc/test cleanup.

---

## Verification checklist (after fixes)

- [ ] CSRF: cross-origin POST to `/api/publish` with session cookie → 400  
- [ ] `/v1/publish_post` with user API key + foreign `user_id` → 403  
- [ ] Restart without `TOKEN_ENCRYPTION_KEY` in prod-like env → process exits  
- [ ] `git ls-files '.venv' | wc -l` → `0`  
- [ ] Specials/events/hours CRUD works (get_db import fixed)  
- [ ] Vercel cron hits publish/generate successfully with secret  
- [ ] Embed widget with malicious caption does not execute script  

---

*Audit performed as a Cloud Agent pass against repo `main` at 2026-08-06. Production Vercel/Supabase live config was not mutated.*
