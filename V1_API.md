# Post-Pilot — V1 API Reference

> SRN status: **🔨 Building** — `/v1/` layer added in Session 12

Base URL: `https://postpilot.onrender.com`

---

## Public Endpoints (no auth)

### `GET /v1/health`
Returns app liveness status.
```json
{ "status": "ok", "app": "post-pilot", "version": "1.0", "uptime": 3600 }
```

### `GET /v1/manifest`
Returns all callable tools with full input/output schema.
ShadowRealm fetches this on startup.

---

## Authenticated Endpoints
All require: `Authorization: Bearer pp_live_<key>` and `X-SRN-App: <caller>`

### `POST /v1/generate_post`
Generate a social media caption using AI.

**Input:**
```json
{
  "topic":    "Today's special: Brisket Tacos",
  "platform": "instagram",
  "tone":     "friendly"
}
```
**Output:** `{ "success": true, "data": { "caption": "..." } }`

---

### `POST /v1/publish`
Publish a post to one or more platforms.

**Input:**
```json
{
  "caption":      "Brisket Tacos $12 today only 🔥",
  "platforms":    ["fb", "ig", "tt"],
  "content_type": "text",
  "image_url":    null
}
```
**Output:** `{ "success": true, "data": { "results": { "fb": "ok", "ig": "ok" } } }`

---

### `GET /v1/history`
Return recent post history for the authenticated user.

**Query params:** `limit` (default 20), `offset` (default 0)

**Output:** `{ "success": true, "data": { "posts": [...] } }`

---

## .env Keys Required
```bash
SRN_APP_NAME=post-pilot
SRN_INBOUND_SECRET=srn_live_xxxxx
SRN_REGISTRY_URL=https://shadowrealm.example.com
```

---

*See [SHADOWREALM_NETWORK.md](./SHADOWREALM_NETWORK.md) for the full SRN contract.*
