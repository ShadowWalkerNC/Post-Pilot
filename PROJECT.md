# Project: PostPilot Pro Enterprise Expansion

## Architecture
PostPilot Pro is an AI-native social media and website automation engine for hospitality businesses.
- **REST API Layer (`modules/api_v1.py` / `blueprints/api_v1.py`)**: Headless API under `/api/v1/*` (and legacy `/v1/*`) secured by Bearer API keys (`@require_api_key`) and rate-limited.
- **MCP Server Layer (`mcp/server.py`)**: FastMCP server exposing tools for AI agents under stdio and SSE transport.
- **Comment Moderation & Auto-Reply (`modules/reply_agent.py`, `modules/comment_poller.py`, `blueprints/inbox.py`, `templates/inbox.html`)**: Meta Graph API comment ingestion, sentiment analysis & tone-matched AI draft generation, dashboard moderation UI, and cron poller.
- **Public Embed Engine (`blueprints/embed_api.py`, `static/embed.js`)**: Public cached JSON feed under `/api/embed/<slug>` with ETag/304 caching and responsive JavaScript drop-in widget.
- **Database & Services (`modules/db.py`, `modules/models.py`, `modules/meta_api.py`, `modules/ai_generator.py`)**: Unified persistence, encryption, token management, and platform dispatch.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Headless Post Draft Creation | `/api/v1/posts/draft` and `/api/v1/posts/generate` for AI & custom drafts | M1 | R1 |
| 2 | Multi-Platform Queue Dispatch | `/api/v1/posts/dispatch` and `/api/v1/posts/schedule` multi-channel routing | M1 | R1 |
| 3 | Daily Specials REST API | `/api/v1/specials` CRUD with date/active filters and validation | M1 | R1 |
| 4 | Upcoming Events REST API | `/api/v1/events` CRUD with date/status filters and validation | M1 | R1 |
| 5 | Hours Overrides REST API | `/api/v1/hours/overrides` CRUD with date range / holiday flags | M1 | R1 |
| 6 | API Key Auth & Rate Limiting | Bearer token auth with scopes, error handling, rate limiting | M1 | R1 |
| 7 | MCP FastMCP Dual-Transport Fix | Fix SSE/stdio transport configuration & port binding | M2 | R2 |
| 8 | MCP Post Management Tools | `create_post`, `schedule_post`, `publish_post`, `list_post_history`, `delete_post` | M2 | R2 |
| 9 | MCP Specials & Hours Tools | `list_specials`, `create_special`, `update_special`, `delete_special`, `list_events`, `create_event`, `list_hours_overrides`, `create_hours_override` | M2 | R2 |
| 10 | MCP Analytics & Health Tools | `get_analytics_summary`, `get_platform_metrics`, `get_connection_health`, `refresh_platform_token` | M2 | R2 |
| 11 | Inbox DB Schema & Migrations | `inbox_items` table with sentiment, draft reply, status tracking | M3 | R3 |
| 12 | Meta Graph API Comment Client | Facebook & Instagram comment fetch, reply, hide endpoints | M3 | R3 |
| 13 | AI Tone-Matched Reply Agent | Sentiment detection (`positive`, `neutral`, `negative`, `question`, `spam`) and Claude draft replies | M3 | R3 |
| 14 | Comment Poller & Cron Job | `/api/cron/poll_comments` and `/api/inbox/poll_now` with CRON_SECRET | M3 | R3 |
| 15 | Dashboard Comment Inbox UI | `/inbox` route & `templates/inbox.html` with Approve, Edit, Hide, Skip | M3 | R3 |
| 16 | Public Embed Cached Feed | `/api/embed/<slug>` with multi-tier in-memory TTL, ETag, CORS wildcard | M4 | R4 |
| 17 | Multi-fallback Slug Resolver | Resolve slug via subdomain, business profile, user id, or business name | M4 | R4 |
| 18 | Drop-in JavaScript Widget | `static/embed.js` rendering specials, events, hours overrides, and updates | M4 | R4 |
| 19 | E2E Test Suite (Tiers 1-4) | Comprehensive opaque-box test suite for R1-R4 (`TEST_READY.md`) | M-E2E | Acceptance |
| 20 | Adversarial & Stress Hardening | Tier 5 white-box stress testing, transport tests, zero regressions | M5 | Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | R1: Unified Headless REST API | Headless `/api/v1/*` routes, post dispatch, specials/events/hours CRUD, API key auth | none | IN_PROGRESS |
| M2 | R2: Expanded MCP Server Tool Suite | FastMCP server dual-transport, 16 domain tools for posts, specials, hours, analytics, health | M1 | PLANNED |
| M3 | R3: AI Social Comment Inbox & Poller | `inbox_items` schema, Meta comments API, reply agent, poller cron, dashboard UI | none | IN_PROGRESS |
| M4 | R4: Public Embed Feed & Widget | `/api/embed/<slug>`, multi-tier caching, ETag/304, CORS, `static/embed.js` | M1 | PLANNED |
| M-E2E | E2E Testing Suite Track | Requirement-driven test suite (Tiers 1-4) creating `TEST_READY.md` | none | DONE |
| M5 | Final Verification & Hardening | Pass 100% E2E tests, Tier 5 adversarial hardening, zero regressions | M1, M2, M3, M4, M-E2E | PLANNED |

## Code Layout
- `blueprints/api_v1.py` / `modules/api_v1.py`: R1 REST API endpoints and blueprint registration
- `mcp/server.py`: R2 MCP server and tool implementations
- `modules/reply_agent.py`, `modules/comment_poller.py`, `blueprints/inbox.py`, `templates/inbox.html`: R3 Inbox & Comment moderation
- `blueprints/embed_api.py`, `static/embed.js`: R4 Public embed feed API & client widget
- `modules/meta_api.py`, `modules/meta_client.py`: Graph API extensions for comments & publishing
- `alembic/versions/0008_inbox.py`: Database migration for `inbox_items`
- `tests/`: Test suites (`test_api_v1.py`, `test_mcp_server.py`, `test_inbox.py`, `test_embed_api.py`, `test_e2e_suite.py`)

## Interface Contracts
### API Key Auth & REST Responses (`blueprints/api_v1.py`)
- Header: `Authorization: Bearer <api_key>`
- Responses: JSON `{ "status": "success", "data": ... }` or `{ "status": "error", "message": ..., "code": ... }`
- Error codes: 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 429 Too Many Requests, 500 Internal Error

### MCP Server (`mcp/server.py`)
- Framework: `FastMCP("PostPilot")`
- Transports: `--transport stdio` (default), `--transport sse --port <port>`
- Tool return: Standard dict or string response compatible with MCP Tool format

### Public Embed Feed (`blueprints/embed_api.py`)
- Route: `GET /api/embed/<slug>`
- Response headers: `Access-Control-Allow-Origin: *`, `Cache-Control: public, max-age=60, stale-while-revalidate=300`, `ETag: W/"..."`
- JSON payload: `{ "business": {...}, "specials": [...], "events": [...], "hours_today": {...}, "hours_overrides": [...], "recent_posts": [...] }`

### Comment Poller & Reply Agent (`modules/comment_poller.py`, `modules/reply_agent.py`)
- Cron: `GET /api/cron/poll_comments` with Header `Authorization: Bearer <CRON_SECRET>` or query `?secret=<CRON_SECRET>`
- Sentiment types: `positive`, `neutral`, `negative`, `question`, `spam`
- Item statuses: `pending`, `approved`, `auto_replied`, `hidden`, `skipped`
