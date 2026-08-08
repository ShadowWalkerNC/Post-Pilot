# 🚀 Post-Pilot

**AI-powered social media automation for food trucks, restaurants, hotels, cafes, and food companies.**

Generates high-engagement posts via OpenAI and publishes directly to Facebook & Instagram via the Meta Graph API. Runs as a Flask SaaS on Vercel with Supabase (PostgreSQL), Stripe billing, magic-link auth, and Vercel Cron for scheduled publishing.

> **Status:** In production · Phase 5 — harden & go live (see `PLANNING.md` / `TODO.md`)

---

## 📄 Documentation

| File | Purpose |
|---|---|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System design, module map, data flow, DB schema, integrations |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Local setup, env vars, testing, branching, deployment |
| [AGENTS.md](./AGENTS.md) | AI agent instructions and project-specific rules |
| [TODO.md](./TODO.md) | Current open work and priorities |
| [PLANNING.md](./PLANNING.md) | Full UPA phase planning document |
| [DEPLOY.md](./DEPLOY.md) | Vercel deployment runbook |
| [CHANGELOG.md](./CHANGELOG.md) | What changed and when |
| [V1_API.md](./V1_API.md) | External API reference |
| [docs/embed-widget.md](./docs/embed-widget.md) | Public embed widget usage & API reference |

---

## ✨ What It Does

- Generates platform-optimised posts using **OpenAI** (GPT-4o-mini)
- Publishes directly to **Facebook** and **Instagram** via Meta Graph API
- Schedules posts with **Vercel Cron** (generate hourly, publish every minute, secret-authenticated)
- Manages subscriptions with **Stripe** (Free / Starter / Pro / Agency)
- Authenticates users via **magic link email** (no passwords)
- Monitors errors in production via **Sentry**
- Enforces plan limits per user with `@require_plan` decorator
- Serves a **public embed widget** so clients can show live posts/hours/services on any external site

---

## 🏗️ Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Framework | Flask 3.x |
| Database | Supabase (PostgreSQL) via SQLAlchemy + psycopg2 |
| Hosting | Vercel (serverless + Vercel Cron) |
| AI | OpenAI GPT-4o-mini (`OPENAI_API_KEY`) |
| Auth | Magic link via Supabase Auth |
| Payments | Stripe (Free / Starter / Pro / Agency) |
| Observability | Sentry (`sentry-sdk[flask]`) |
| Rate limiting | Flask-Limiter + Upstash Redis |
| Migrations | Alembic |
| CI/CD | GitHub Actions (ruff + pytest) |
| Styling | Tailwind CSS (Jinja2 templates) |

---

## 📁 Project Structure

```
Post-Pilot/
  app.py                  ← Flask app factory, blueprint registration, Sentry init
  blueprints/             ← Flask blueprints (one file per domain)
    auth.py               ← Magic link auth, OAuth connect, /dev-login
    billing.py            ← Stripe subscription management
    api.py                ← Generate / publish APIs
    pages.py              ← HTML pages (dashboard, generate, …)
    cron.py               ← Vercel Cron (/api/cron/generate, /publish)
    website.py            ← Website hub
    embed_api.py          ← Public embed API (/api/embed/<slug>)
    specials.py | events.py | hours.py
  modules/                ← Shared utilities and services
    auth_manager.py       ← Encrypted platform tokens
    ai_generator.py       ← OpenAI caption generation
    platform_adapter.py   ← Per-platform adaptation
    publisher.py          ← Publish router
    billing_manager.py    ← Stripe lifecycle
    plan_guard.py         ← @require_plan + limits
    automation_agent.py   ← Specials/events/hours → posts
    meta_api.py           ← Meta Graph API client
  templates/              ← Jinja2 HTML templates
  static/                 ← Tailwind CSS, JS, images
    embed.js              ← Drop-in public embed widget script
  alembic/versions/       ← Migrations 0001…0006
  tests/                  ← pytest test suite
  docs/embed-widget.md    ← Embed widget usage guide
  mcp/                    ← Post-Pilot MCP server
  vercel.json             ← Vercel deployment + Cron config
  PLANNING.md             ← Phase / pricing / stack source of truth
  TODO.md                 ← Open work + go-live checklist
```

---

## ⚡ Quick Start

```bash
git clone https://github.com/ShadowWalkerNC/Post-Pilot.git
cd Post-Pilot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in .env — see DEVELOPMENT.md for the full guide
alembic upgrade head
flask run
# open http://localhost:5000
```

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the complete setup guide, env var reference, and troubleshooting.

---

## 🧩 Embed Widget — Manual Setup

The embed widget lets any client drop live posts, hours, and services onto their own website with a single `<div>` and `<script>` tag.

### 1. Blueprint registration

`embed_bp` is registered in `blueprints/__init__.py` (CSRF-exempt). No manual `app.py` wiring needed.

### 2. (Optional) Add a custom slug column

By default the widget uses the user's **username** as the slug. To support custom vanity slugs, run this migration once against your database:

```sql
ALTER TABLE users ADD COLUMN embed_slug TEXT UNIQUE;
```

### 3. Serve `static/embed.js` publicly

Ensure your Vercel / Flask static file config exposes `/static/embed.js`. No extra config is needed if you are already serving the `static/` folder (Flask does this by default).

### 4. Give clients their snippet

Replace `your-business-slug` with the user's username (or their custom `embed_slug`):

```html
<div
  data-postpilot-slug="your-business-slug"
  data-postpilot-theme="light"
  data-postpilot-sections="posts,hours,services"
></div>

<script src="https://yourapp.com/static/embed.js" async></script>
```

| Attribute | Options | Default | Description |
|---|---|---|---|
| `data-postpilot-slug` | any string | *(required)* | Username or custom embed slug |
| `data-postpilot-theme` | `light` \| `dark` | `light` | Widget colour scheme |
| `data-postpilot-sections` | comma-separated | `posts,hours,services` | Sections to display |

Full reference: [docs/embed-widget.md](./docs/embed-widget.md)

---

## 🗺️ Roadmap

See [`PLANNING.md`](./PLANNING.md) and [`ROADMAP.md`](./ROADMAP.md).

- [x] Phases 1–4 — Core product (auth, OpenAI, Meta publish, Stripe, cron, embed, specials/events/hours)
- [ ] **Phase 5** — Harden & go live (keys, Vercel env, Redis, smoke test, teams design)
- [ ] Phase 6 — Retention (morning prompt, location one-tap), inbox, finish non-Meta publishers
- [ ] Phase 7 — Agency multi-location / ecosystem

---

## 🤖 AI Agent Session Bootstrap

This repo follows the **Universal Project Architect (UPA)** framework. Every AI session (Perplexity, Claude, or any coding agent) must load the bootstrap files before planning or making changes.

**Full bootstrap reference:** [BOOT.md](https://github.com/ShadowWalkerNC/.github/blob/main/BOOT.md)

### Quick bootstrap (paste as first message)

```
Load and follow these files before responding:
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/AGENTS.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/SESSION_START.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/AGENT_DISPATCH.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/UPA_V1.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/agents/AGENT_COHERENCE.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/agents/AGENT_SECURITY.md
https://raw.githubusercontent.com/ShadowWalkerNC/.github/main/agents/AGENT_DOCS.md
https://raw.githubusercontent.com/ShadowWalkerNC/Post-Pilot/main/AGENTS.md
https://raw.githubusercontent.com/ShadowWalkerNC/Post-Pilot/main/ARCHITECTURE.md

PROJECT:      Post-Pilot
PHASE:        5 — Harden & go live (see PLANNING.md)
LAST COMMIT:  [paste last commit SHA or message]
MODE:         [full | quick | audit | hotfix | onboard]
AGENT:        [Perplexity | Claude | Cursor]
OPEN:         SEC-1 (key rotation), TODO.md §CRITICAL, [your third item]
SCOPE:        [what you want this session]
OUT OF SCOPE: [what you are not doing]
```

**iPhone shortcut:** Use `;upa` text replacement to expand the full block on mobile. See [BOOT.md](https://github.com/ShadowWalkerNC/.github/blob/main/BOOT.md) for setup instructions.

---

## 📄 License

MIT License — free to use, modify, and distribute.
