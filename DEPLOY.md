# Deploying Post-Pilot

Post-Pilot is a Python/Flask app deployed on **Vercel** (serverless) with **Supabase** (Postgres + Auth) and **Vercel Cron** for scheduled generate/publish.

> Older Railway/Render runbooks are obsolete. Do not deploy this app as a long-lived APScheduler worker.

---

## 1. Link the Vercel project

1. Import `ShadowWalkerNC/Post-Pilot` in the Vercel dashboard (or `vercel link` locally).
2. Framework preset: Other / Python. Entry is `app.py` (see `vercel.json`).
3. Production deploys on push to `main`.

`vercel.json` defines:

- Build: `@vercel/python` on `app.py`
- Routes: all traffic → `app.py`
- Crons (Hobby-compatible — once per day max):
  - `/api/cron/generate` — daily at 14:00 UTC (`0 14 * * *`)
  - `/api/cron/publish` — daily at 15:00 UTC (`0 15 * * *`)

> **Hobby vs Pro:** Vercel Hobby rejects cron expressions that run more than once per day (deploys fail with the cron usage error). On **Pro**, you can tighten schedules (e.g. publish `* * * * *`, generate `0 * * * *`) for near-real-time scheduling.

---

## 2. Provision dependencies

| Service | Purpose |
|---|---|
| **Supabase** | Postgres (`DATABASE_URL`) + magic-link auth keys |
| **Upstash Redis** | `REDIS_URL` for Flask-Limiter across instances |
| **Stripe** | Products/prices for Starter / Pro / Agency (monthly + annual) |
| **OpenAI** | `OPENAI_API_KEY` for caption generation |
| **Sentry** | `SENTRY_DSN` for production errors |
| **Meta app** | Facebook/Instagram OAuth + Graph API |

---

## 3. Set Vercel environment variables

Use `.env.example` as the checklist. Minimum production set:

- `FLASK_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, `CRON_SECRET`
- `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_STARTER_MONTHLY` / `_ANNUAL`
- `STRIPE_PRICE_PRO_MONTHLY` / `_ANNUAL`
- `STRIPE_PRICE_AGENCY_MONTHLY` / `_ANNUAL`
- `REDIS_URL`, `SENTRY_DSN`
- Meta / Google / TikTok OAuth vars as needed
- `APP_ENV=production`

**Must be absent in production:** `DEV_LOGIN_KEY`

Also set GitHub Actions secret `CI_TOKEN_ENCRYPTION_KEY` to the same Fernet key.

---

## 4. Run migrations

From a trusted machine with network access to Supabase:

```bash
DATABASE_URL=your_postgres_connection_string alembic upgrade head
```

Forward-only. Current head includes through `0006_events_hours`.

---

## 5. Stripe webhook

Point Stripe to:

`https://<your-vercel-domain>/billing/webhook`

Events: `customer.subscription.created|updated|deleted`, `invoice.payment_failed`, `invoice.payment_succeeded`.

---

## 6. Smoke test

Follow `TODO.md` §CRITICAL Step 7:

1. Magic link login
2. Add a Special on `/schedule`
3. Hit cron generate with `Authorization: Bearer <CRON_SECRET>`
4. Confirm billing tiers ($0 / $19 / $49 / $99)
5. Connect a platform

---

## 7. Local vs production

| | Local | Production |
|---|---|---|
| Host | `flask run` | Vercel serverless |
| DB | SQLite (`DATABASE_PATH`) | Supabase Postgres |
| Cron | Manual curl to cron routes | Vercel Cron |
| Rate limit | memory:// | Redis (`REDIS_URL`) |
| Auth | Supabase magic link (+ optional `DEV_LOGIN_KEY`) | Magic link only |

Full env notes: `DEVELOPMENT.md` · go-live checklist: `TODO.md` · phase context: `PLANNING.md`.
