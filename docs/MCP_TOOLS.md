# MCP Tools (33)

Product tools in `mcp/tools/*`, exposed over stdio/SSE by `mcp/server.py`.
Every tool delegates to an existing service; no new business logic here.

## Auth model

- Transport authenticates the caller (local process or authed SSE proxy).
- Every user-data tool takes `user_id` and touches only that user's rows.
- Write/publish tools require owner/team with matching rights; plan quota is
  enforced at the API layer — MCP callers confirm quota before invoking.
- No tool ever returns tokens or API keys.

## Tool list

| Tool | Perm | Backing |
|---|---|---|
| `business.get` / `business.update` | read / write | `UserManager` business_profiles |
| `menu.get` / `menu.list` / `menu.item_get` | read | websites section_data |
| `specials.list` / `specials.get` | read | specials table |
| `events.list` / `events.get` | read | events table |
| `hours.get` | read | hours_overrides table |
| `content.generate` | write | `ai_generator` + adapter |
| `content.adapt` | write | `PlatformAdapter` |
| `content.schedule` | write | `PostScheduler` |
| `content.preview` | read | adapt + counts/warnings |
| `post.publish` | publish | `UniversalPublisher` |
| `post.cancel` / `post.status` | write / read | `PostScheduler` jobs |
| `analytics.get` | read | `Analytics` combined summary |
| `analytics.top_posts` | read | summary ranked by metric |
| `analytics.performance_summary` | read | summary KPIs |
| `inbox.list` | read | `InboxItem` |
| `inbox.reply` | write | `analyze_and_draft` (draft only) |
| `inbox.approve_reply` | publish | Meta API + `mark_replied` |
| `inbox.skip` | write | `mark_skipped` |
| `media.list` / `media.get` | read | post_history attachments |
| `brand.get` | read | business_profiles brand fields |
| `brand.validate` | read | deterministic checks (v1, no LLM) |
| `automation.run` | write | `automation_agent` per-user |
| `automation.status` | read | automation_log ([] if missing) |
| `provider.list` | read | gateway registry + health |
| `provider.route` | read | router explain (no generation) |
| `provider.health` | read | gateway health (no network) |

## Honest limitations

- `post.cancel`/`post.status` cover in-memory scheduler jobs only; schedules
  sent straight to the Meta API cannot be recalled or tracked.
- `media.*` reflects attachments on post_history rows; there is no standalone
  media library table.
- `brand.validate` is deterministic v1 (presence/tone/name/keywords); an
  LLM-backed brand-guard pass is future work.
- `automation.status` returns `[]` on schemas without `automation_log`.
- `provider.*` reports configuration status, never live pings or keys.
