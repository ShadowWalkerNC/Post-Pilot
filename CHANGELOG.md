# Changelog

All notable changes to Post-Pilot are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security
- Re-enabled CSRF on session-authenticated APIs (`api` / specials / events / hours); dashboard pages send `X-CSRFToken` via `static/js/csrf.js`
- Fixed `/v1` IDOR: user API keys ignore client-supplied `user_id` and bind to the key owner
- Production refuses to start with missing/invalid `TOKEN_ENCRYPTION_KEY` (no ephemeral Fernet key)
- Disabled `POST /api/setup_tokens` in production unless `ALLOW_MANUAL_TOKEN_SETUP=1`
- Removed tracked `.venv` and `__pycache__` from version control
- Fixed broken `from app import get_db` imports (now `modules.database.get_db`)
- Hardened session cookies (`HttpOnly`, `SameSite=Lax`, `Secure` in production)
- Cron endpoints accept GET+POST (Vercel Cron); error bodies no longer leak exception strings
- Dev-login uses constant-time key compare; analytics no longer accepts client-supplied Meta tokens

### Tests
- Added `tests/test_security_c1_c6.py`; updated fixtures for magic-link auth

---

## [0.4.0] — 2026-06-22

### ✨ Option B: Per-Platform Caption Generation

End-to-end feature allowing users to generate, edit, and publish
platform-adapted captions from a single topic input.

#### Added
- **`modules/platform_adapter.py`** — `PlatformAdapter` class
  - `adapt(master, platform, tone, content_type)` produces captions tailored
    to each platform's tone, length limits, and best practices
  - Supports: `fb`, `ig`, `tt`, `yt`, `yts`, `li`, `tw`, `pi`, `gb`, `web`
  - Hashtag strategy varies per platform (heavy on IG, none on GB, etc.)
  - Falls back gracefully to master caption on unknown platforms

- **`modules/ai_generator.py`** — extended for multi-platform output
  - `generate_adapted(topic, platforms, tone, content_type)` returns
    `{ master, adapted: {pid: caption} }`
  - Wired into `POST /api/generate`

- **`modules/publisher.py`** — Option B publish path
  - `publish_all(captions, platforms, user_id, content_type)` dispatches
    per-platform captions to each adapter
  - Returns per-platform result dict `{ pid: { success, message } }`
  - Wired into `POST /api/push_all`

- **`blueprints/api.py`** — two new endpoints
  - `POST /api/generate` — accepts `{ topic, tone, content_type, platforms }`
    → returns `{ success, master, adapted }`
  - `POST /api/platform_settings` — save per-user platform enable/disable state
  - `GET  /api/platform_settings` — retrieve current platform settings

- **`alembic/versions/0002_platform_settings.py`** — DB migration
  - New table `platform_settings (user_id TEXT, platform TEXT, enabled INTEGER DEFAULT 1)`
  - Composite primary key `(user_id, platform)`
  - Index `idx_platform_settings_user` on `user_id`
  - Migration chain: `0001 → 0002`

- **`templates/generate.html`** — ✨ Per-Platform tab (third tab)
  - Topic textarea, content type selector, tone selector
  - Platform toggles loaded from `/api/platform_settings`
  - **Generate Captions** button calls `POST /api/generate`
  - Skeleton shimmer while adapting (one card per platform)
  - Per-platform editable `<textarea>` with live character counter
    (green ≤90 % of limit · amber 90–100 % · red over limit)
  - Collapsible master caption reference strip (`<details>`)
  - **Skip** toggle per platform card (excluded from publish payload)
  - **🚀 Publish All** → `POST /api/push_all` with `captions` dict
  - **📅 Schedule All** → same endpoint with `schedule_time`
  - Existing 7-Day Schedule and Single Post tabs unchanged

- **`templates/setup.html`** — 📲 Platforms settings tab
  - New sixth tab between Schedule and Notifications
  - Toggle row for all 10 platforms with custom pill-style switch UI
  - Green `connected` badge or grey `not connected` badge per row
  - Disconnected rows are greyed (`.disabled-row`) but still toggleable
  - Saves on toggle change, debounced 300 ms → `POST /api/platform_settings`
  - Loads on page load in parallel with connection status and business profile

#### Changed
- `setTab()` in `generate.html` updated to handle 3 tabs (`weekly`, `single`, `adapt`)
- `loadSettings()` in `setup.html` now also fetches `/api/platform_settings`
- Removed `user_id: 'default'` hardcoding from weekly/single fetch calls
  (now resolved server-side from session)

---

## [0.3.0] — 2026-06-15

### 🌐 Website Hub

- New `/website_hub` page and blueprint
- `modules/website_manager.py` — static site generation from business profile
- `templates/website_hub.html` — full hub UI with preview, publish controls,
  page section editor, and SEO metadata fields
- `GET /api/website_status`, `POST /api/website_publish` endpoints

---

## [0.2.0] — 2026-06-08

### 📅 Calendar & Scheduling

- New `/calendar` page with full month/week view
- `POST /api/schedule_post`, `POST /api/bulk_schedule` endpoints
- Drag-to-reschedule UI (planned; static in this release)
- `alembic/versions/0001_scheduled_posts.py` — `scheduled_posts` table

---

## [0.1.0] — 2026-05-28

### 🚀 Initial Release

- Flask app with Jinja2 templating, SQLite via SQLAlchemy + Alembic
- User auth: register, login, logout, session management
- Business profile setup (`/setup`, `POST /api/setup_business`)
- AI caption generation — 7-day schedule and single-post modes
  (`POST /api/generate_posts`, `POST /api/generate_single`)
- Analytics page with placeholder chart data
- Billing page (Stripe integration stubbed)
- OAuth connection stubs for Facebook, Instagram, TikTok, YouTube,
  Google Business, Website Hub
- Responsive dark UI across all pages (Tailwind CSS via CDN)
- Deploy configs: `Procfile`, `railway.toml`, `render.yaml`
- Docs: `README.md`, `DEPLOY.md`, `API_NOTES.md`, `PLANNING.md`,
  `ROADMAP.md`, `PRICING.md`

---

## Version Policy

Post-Pilot follows **semver-lite**:
- `0.x.0` — new feature milestone (new page, major module, or API surface)
- `0.x.y` — bug fixes, copy changes, minor UI tweaks within a milestone
- `1.0.0` — first public beta / paying customers onboarded
