# CulinaryOS ↔ Post-Pilot Contract

> **Ownership:** Post-Pilot owns ALL marketing logic — caption generation,
> platform adaptation, scheduling, publishing, analytics, and reply drafting.
> The CulinaryOS package (`integrations/culinaryos/`) is an **adapter only**:
> it fetches/normalizes CulinaryOS data and hands Post-Pilot-shaped dicts to
> existing Post-Pilot services. It must never contain prompts, templates,
> publishing calls, or scheduling decisions.

---

## 1. Data shapes (adapter output → Post-Pilot input)

| CulinaryOS source | Normalizer | Post-Pilot consumer |
|---|---|---|
| menu | `normalize_menu` → `{'items': [{name, description, price}]}` | `mcp/tools/business.menu_get` fallback, `ai_generator` business context |
| specials | `normalize_specials` → specials-shaped rows | `specials` table / `automation_agent` / `special_post` skill |
| events | `normalize_events` → events-shaped rows | `events` table / `automation_agent` / `event_campaign` skill |
| hours | `normalize_hours` → `{'summary', 'days'}` | `hours_overrides` / business profile `hours` |

Normalizers accept dict-or-list payloads and tolerate missing keys (empty
strings). They raise nothing on bad data — webhook parsing wraps failures.

## 2. Transports

### 2a. REST pull (implemented — `CulinaryOSClient`)

- Base URL: `CULINARYOS_BASE_URL`, e.g. `https://api.culinaryos.example`
- Auth: `Authorization: Bearer $CULINARYOS_API_KEY`
- Endpoints: `GET /v1/menu`, `/v1/specials`, `/v1/events`, `/v1/hours`,
  `GET /v1/health` (no auth)
- Timeouts: 10s default; errors raise `CulinaryOSError` with safe messages
  (no secrets in messages).

### 2b. Webhooks (implemented — `verify_webhook_signature`, `parse_webhook_event`)

- Signature: HMAC-SHA256 hex of raw body, secret `CULINARYOS_WEBHOOK_SECRET`.
- Receiver (Post-Pilot side, future blueprint) must: verify → parse →
  upsert into Post-Pilot tables → optionally trigger `automation_agent`.
- Event types: `menu.updated`, `special.created`, `event.created`,
  `hours.updated`. Unknown types pass through as `type='unknown'`.

### 2c. MCP (future)

- CulinaryOS-backed reads may be exposed as MCP tools that call the same
  normalizers (e.g. a `menu.get` that prefers CulinaryOS when configured).
- Same auth model as `mcp/tools`: explicit `user_id` scope, owner/team only,
  no secrets in outputs.

### 2d. Plugin SDK (future)

- If CulinaryOS ships a plugin host, the plugin entrypoint must call only:
  `CulinaryOSClient`, `normalize_*`, `parse_webhook_event`, and Post-Pilot
  public services (`ai_generator`, `publisher`, `scheduler_worker`).
- The plugin must not duplicate marketing logic; version-pin the adapter.

## 3. Security

- Secrets via env vars only: `CULINARYOS_BASE_URL`, `CULINARYOS_API_KEY`,
  `CULINARYOS_WEBHOOK_SECRET`. Never commit values.
- Webhook receivers reject missing/invalid signatures with 401 and log
  without echoing the body.
- Adapter errors never include the API key or secret.

## 4. Failure modes

| Failure | Behavior |
|---|---|
| CulinaryOS unreachable | `CulinaryOSError`; caller falls back to Post-Pilot tables |
| 401 from CulinaryOS | `CulinaryOSError` naming the key (not its value) |
| Non-JSON body | `CulinaryOSError` |
| Bad webhook payload | `parse_webhook_event` returns `{'error': ...}`, never raises |
| Unknown event type | Pass-through with `type='unknown'` |

## 5. Non-goals

- Post-Pilot never writes back to CulinaryOS (no menu editing, no order flow).
- The adapter never calls OpenAI/Meta/Stripe directly.
- No background threads in the adapter; scheduling stays in Post-Pilot's
  scheduler/cron layer.
