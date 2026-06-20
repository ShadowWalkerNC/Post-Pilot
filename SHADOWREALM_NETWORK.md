# ShadowRealm Network (SRN) — App Contract v1.0

Every app in the **ShadowWalkerNC ecosystem** that wants to participate in the
ShadowRealm Network MUST implement this contract. It is the only thing ShadowRealm
needs to discover, call, and monitor any app automatically.

> Copy this file verbatim into every participating repo as `SHADOWREALM_NETWORK.md`.
> Do not modify it locally — changes are made here and propagated.

---

## 1. Required Endpoints

Every app exposes these three routes under `/v1/`:

| Method | Path | Auth Required | Purpose |
|--------|------|--------------|--------|
| `GET`  | `/v1/health`   | No  | Liveness check — ShadowRealm polls this |
| `GET`  | `/v1/manifest` | No  | Tool discovery — returns all callable tools |
| `POST` | `/v1/<tool>`   | Yes | Execute a tool by name |

### `/v1/health` response
```json
{
  "status":  "ok",
  "app":     "post-pilot",
  "version": "1.2.0",
  "uptime":  3600
}
```

### `/v1/manifest` response
```json
{
  "app":     "post-pilot",
  "version": "1.2.0",
  "tools": [
    {
      "name":        "publish_post",
      "description": "Generate and publish a social media post",
      "method":      "POST",
      "path":        "/v1/publish_post",
      "input": {
        "caption":   { "type": "string",  "required": true  },
        "platforms": { "type": "array",   "required": false },
        "image_url": { "type": "string",  "required": false }
      },
      "output": {
        "success": "boolean",
        "results": "object"
      }
    }
  ]
}
```

---

## 2. Authentication

All `/v1/*` routes **except `/v1/health` and `/v1/manifest`** require:

```
Authorization: Bearer <app_api_key>
X-SRN-App: <calling_app_name>
```

- `app_api_key` — issued by the target app to the calling app (stored in `.env`)
- `X-SRN-App` — the name of the calling app (e.g. `sigil`, `shadowrealm`, `culinaryos`)

### Key format
Keys follow the pattern: `<app_prefix>_live_<32_hex_chars>`  
Example: `pp_live_a1b2c3...` (Post-Pilot), `sg_live_...` (Sigil)

---

## 3. Standard Response Envelope

All `/v1/<tool>` responses use this envelope:

**Success**
```json
{ "success": true, "data": { ... } }
```

**Failure**
```json
{
  "success": false,
  "error":   "Human readable message",
  "code":    "MACHINE_READABLE_CODE"
}
```

### Standard error codes
| Code | Meaning |
|------|---------|
| `AUTH_REQUIRED`    | Missing or invalid API key |
| `FORBIDDEN`        | Key valid but lacks permission |
| `NOT_FOUND`        | Tool or resource does not exist |
| `VALIDATION_ERROR` | Missing or invalid input field |
| `RATE_LIMITED`     | Too many requests |
| `INTERNAL_ERROR`   | Unexpected server error |

---

## 4. `.env` Keys Every App Adds

```bash
# This app's SRN identity
SRN_APP_NAME=post-pilot

# Shared inbound secret — ShadowRealm uses this to call this app
# Generate with: openssl rand -hex 32
SRN_INBOUND_SECRET=srn_live_xxxxxxxx

# ShadowRealm registry URL (set when ShadowRealm is deployed)
SRN_REGISTRY_URL=https://shadowrealm.example.com

# Per-app outbound keys (add one per app you call)
# e.g. if this app calls Post-Pilot:
POSTPILOT_URL=https://postpilot.onrender.com
POSTPILOT_API_KEY=pp_live_xxxxxxxx
```

---

## 5. Webhook Events (Optional but Recommended)

Apps that emit events (e.g. "new menu item added", "reservation made") should
`POST` to ShadowRealm's event bus:

```
POST https://shadowrealm.example.com/v1/events
Authorization: Bearer <SRN_INBOUND_SECRET>
X-SRN-App: sigil

{
  "event":  "menu.item.added",
  "source": "sigil",
  "data":   { "item": "Brisket Tacos", "price": 12.00 }
}
```

ShadowRealm then decides which other apps to notify or trigger.

---

## 6. SRN_REGISTRY.json

The master registry lives at `ShadowWalkerNC/ShadowRealm/SRN_REGISTRY.json`.
Update it whenever a new app joins the network or a URL changes.
ShadowRealm reads this on startup to know what apps exist.

---

## 7. Implementation Checklist

When adding SRN support to an app, check off:

- [ ] `GET /v1/health` returns correct envelope
- [ ] `GET /v1/manifest` lists all callable tools with full schema
- [ ] All `/v1/<tool>` routes use standard response envelope
- [ ] Auth middleware validates `Authorization: Bearer` header
- [ ] `.env` has `SRN_APP_NAME` and `SRN_INBOUND_SECRET`
- [ ] `SHADOWREALM_NETWORK.md` present in repo root
- [ ] `V1_API.md` documents all tools in plain English
- [ ] Entry added/updated in `ShadowWalkerNC/ShadowRealm/SRN_REGISTRY.json`
- [ ] `srn_ready: true` set in registry once checklist complete

---

*ShadowRealm Network v1.0 — ShadowWalkerNC ecosystem*
