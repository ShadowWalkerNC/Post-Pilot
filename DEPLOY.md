# Deploying Post-Pilot

Post-Pilot runs as a Python/Flask web app. The recommended host is **Render** (free tier works for testing; Starter $7/mo for always-on).

Sigil (the Discord bot) is already deployed on **Railway** — this guide covers wiring them together after Post-Pilot goes live.

---

## 1. Deploy Post-Pilot to Render

### Option A — render.yaml (recommended)

1. Push this repo to GitHub (already done).
2. Go to [render.com](https://render.com) → **New** → **Blueprint**.
3. Connect your GitHub account and select the `Post-Pilot` repo.
4. Render will detect `render.yaml` and pre-fill the service config.
5. Click **Apply** — Render will run `pip install -r requirements.txt` then start gunicorn.
6. Once deployed, copy your Render URL: `https://post-pilot-xxxx.onrender.com`

### Option B — Manual web service

1. Render dashboard → **New** → **Web Service**
2. Connect `Post-Pilot` repo, branch `main`
3. Runtime: **Python 3**
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app --workers 2 --threads 2 --timeout 120 --bind 0.0.0.0:$PORT`
6. Health check path: `/v1/health`

---

## 2. Set Environment Variables on Render

In the Render dashboard → your service → **Environment**, add:

| Variable | Where to get it |
|---|---|
| `FLASK_SECRET_KEY` | Any random 32+ char string (Render can auto-generate) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| `STRIPE_SECRET_KEY` | [dashboard.stripe.com](https://dashboard.stripe.com) → Developers → API keys |
| `STRIPE_WEBHOOK_SECRET` | Stripe → Webhooks → your endpoint → Signing secret |
| `STRIPE_PRICE_STARTER` | Stripe → Products → Starter plan → price ID |
| `STRIPE_PRICE_GROWTH` | Stripe → Products → Growth plan → price ID |
| `STRIPE_PRICE_AGENCY` | Stripe → Products → Agency plan → price ID |
| `FACEBOOK_APP_ID` | [developers.facebook.com](https://developers.facebook.com) |
| `FACEBOOK_APP_SECRET` | Same as above |
| `REDIRECT_URI` | `https://<your-render-domain>/auth/facebook/callback` |
| `GOOGLE_CLIENT_ID` | [console.cloud.google.com](https://console.cloud.google.com) |
| `GOOGLE_CLIENT_SECRET` | Same as above |
| `GOOGLE_REDIRECT_URI` | `https://<your-render-domain>/auth/google/callback` |
| `TIKTOK_CLIENT_KEY` | [developers.tiktok.com](https://developers.tiktok.com) |
| `TIKTOK_CLIENT_SECRET` | Same as above |
| `TIKTOK_REDIRECT_URI` | `https://<your-render-domain>/auth/tiktok/callback` |

---

## 3. Set Up Stripe Webhook

1. Stripe dashboard → **Developers** → **Webhooks** → **Add endpoint**
2. URL: `https://<your-render-domain>/webhooks/stripe`
3. Events to listen for:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
4. Copy the **Signing secret** → set as `STRIPE_WEBHOOK_SECRET` on Render.

---

## 4. Create Stripe Products

In the Stripe dashboard → **Products**, create three products:

| Product | Monthly price | Annual price |
|---------|-------------|-------------|
| Starter | $29/mo | $290/yr |
| Growth  | $59/mo | $590/yr |
| Agency  | $149/mo | $1490/yr |

Copy the **price IDs** (format: `price_xxx`) into Render env vars.

---

## 5. Wire Sigil → Post-Pilot

Once Post-Pilot is live:

1. Register at `https://<your-render-domain>` — create your account.
2. Go to **Settings → API Keys** → **Create Key** → name it `sigil`.
3. Copy the `pp_live_...` key.
4. In Railway (Sigil project) → **Variables**, set:
   ```
   POSTPILOT_URL=https://<your-render-domain>
   POSTPILOT_API_KEY=pp_live_...
   POSTPILOT_USER_ID=<your user ID from Post-Pilot settings>
   ```
5. Railway will auto-redeploy Sigil.
6. In Discord, run `/poststatus` — you should see 🟢 Online.

---

## 6. Update SRN_REGISTRY.json

In `ShadowRealm/SRN_REGISTRY.json`, replace the placeholders:

```json
"postpilot": {
  "live_url": "https://<your-render-domain>",
  "status": "live"
},
"sigil": {
  "live_url": "https://<your-railway-domain>"
}
```

---

## 7. Smoke Test Checklist

```
☐ GET  https://<domain>/           → marketing page loads
☐ GET  https://<domain>/v1/health  → { "status": "ok" }
☐ POST /register                   → creates account, redirects to onboarding
☐ Complete onboarding              → business profile saved
☐ GET  /billing                    → plans shown, Stripe checkout works
☐ GET  /website                    → website hub loads
☐ GET  /site/preview               → preview iframe renders
☐ POST /api/generate_post          → returns AI caption
☐ Discord /poststatus              → 🟢 Online
☐ Discord /postgenerate topic:test → caption embed appears
☐ Discord /post topic:test         → platform select → publishes
☐ POST /webhooks/stripe            → 200 OK (test with Stripe CLI)
```

---

## Local Development

```bash
# 1. Clone
git clone https://github.com/ShadowWalkerNC/Post-Pilot.git
cd Post-Pilot

# 2. Virtual env
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env with your keys

# 5. Run
python app.py
# Open http://localhost:5000
```
