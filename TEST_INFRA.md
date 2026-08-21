# Post-Pilot Test Infrastructure & 4-Tier E2E Testing Framework

## 1. Overview & Testing Philosophy

Post-Pilot utilizes an opaque-box, requirement-driven 4-Tier End-to-End (E2E) testing framework. The testing philosophy strictly adheres to:
- **Zero Dummy Implementations**: All tests exercise genuine runtime logic, database transactions, HTTP request/response lifecycles, and security boundary assertions.
- **Contract & Protocol Fidelity**: Validation against machine-readable and human-readable specifications (`V1_API.md`, `SHADOWREALM_NETWORK.md`, MCP protocol specs, Vercel Cron specs).
- **Isolation & Reproducibility**: Self-contained SQLite test environments, clean state resets between runs, deterministic fixture teardown, and explicit mock boundaries for third-party network APIs (Meta Graph API, OpenAI, PyGithub).

---

## 2. 4-Tier Testing Methodology

```
┌───────────────────────────────────────────────────────────────────┐
│              TIER 4: REAL-WORLD APPLICATION SCENARIOS             │
│  Morning Setup · Lunch Rush Automation · Full Business Lifecycle  │
├───────────────────────────────────────────────────────────────────┤
│              TIER 3: CROSS-FEATURE COMBINATIONS                   │
│  Special -> Embed · Publish -> History · API Key Full Lifecycle  │
├───────────────────────────────────────────────────────────────────┤
│              TIER 2: BOUNDARY & CORNER CASES                      │
│  Auth 401s · Validation 400s · Date Formats · ID 404s · State 409s│
├───────────────────────────────────────────────────────────────────┤
│              TIER 1: CORE FEATURE COVERAGE                        │
│  R1: Headless REST API  ·  R2: MCP Server Tools                  │
│  R3: AI & Cron Poller   ·  R4: Public Embed Feed & Drop-in Widget │
└───────────────────────────────────────────────────────────────────┘
```

### Tier 1: Feature Coverage (>=5 tests per feature area)
- **R1: Headless REST API & Schedule Endpoints**: Validates all headless `/v1/*` routes (`/v1/health`, `/v1/manifest`, `/v1/generate_post`, `/v1/publish_post`, `/v1/generate_and_publish`, `/v1/get_history`, `/v1/get_site_config`, `/v1/set_published`) and dashboard schedule endpoints (`/api/specials`, `/api/events`, `/api/hours`).
- **R2: MCP Server Tools**: Verifies all 7 FastMCP server tools (`get_repo_structure`, `read_file`, `audit_repo`, `write_file`, `list_open_issues`, `create_issue`, `list_recent_commits`) for repository inspection, auditing, and maintenance.
- **R3: AI Comment Moderation & Auto-Reply Poller (Cron)**: Exercises `/api/cron/publish`, `/api/cron/generate`, `/api/cron/health`, and the constant-time HMAC `CRON_SECRET` authorization mechanism.
- **R4: Public Embed Feed & Drop-in Widget**: Exercises `/api/embed/<slug>` (embed slug lookup, username fallback, 404 on missing slug, published posts filtering) and the client-side `static/embed.js` script structure.

### Tier 2: Boundary & Corner Cases (>=5 tests per boundary area)
- **Missing Bearer Token / Unauthorized Access (401)**: Missing headers, malformed tokens, unknown keys, expired API keys, and invalid cron secrets.
- **Empty Strings / Missing Required Parameters (400)**: Missing topics, captions, published flags, item names, event titles, hours titles, empty platform arrays, and missing key IDs.
- **Malformed Dates & Times (400)**: Non-ISO dates (e.g. `2026-13-45`, `invalid-date`), invalid 24-hour times (`25:70`, `99:99`), and malformed update payloads.
- **Unauthenticated Session Endpoints (302/401)**: Accessing session-authenticated routes without active Flask-Login session redirecting or rejecting cleanly.
- **Unknown / Missing ID Updates & Deletes (404)**: Attempting to update or delete non-existent IDs or IDs belonging to other tenant accounts (IDOR isolation).
- **Non-Pending Status Update Rejection (409 Conflict)**: Blocking mutation of records that have already transitioned to `published`, `queued`, or `cancelled`.

### Tier 3: Cross-Feature Combinations
Validates multi-subsystem flows where state mutations in one feature directly affect the outputs of another:
1. **Special Creation -> DB -> Public Embed**: Adding a special via schedule API, recording publication, and verifying visibility in the public embed feed.
2. **Post Publish -> Post History**: Publishing via `/v1/publish_post` and asserting immediate persistence in post history retrieved via `/v1/get_history`.
3. **Cron Secret Matrix**: Verifying strict authorization across cron endpoints while keeping health check publicly accessible.
4. **API Key Lifecycle**: Key creation (`POST /v1/keys/create`), token usage in Bearer headers, query verification in key list, revocation (`POST /v1/keys/revoke`), and immediate rejection on subsequent requests.

### Tier 4: Real-World Application Scenarios
Simulates realistic, day-in-the-life operational business workflows:
1. **Scenario 1: Food Truck Morning Setup**: Business profile configuration, daily special scheduling, holiday hours override creation, and public embed feed validation.
2. **Scenario 2: Lunch Rush Automation**: On-demand AI draft generation, immediate multi-platform publishing, history auditing, scheduled queueing, and cron auto-publish execution.
3. **Scenario 3: Full Business Operational Lifecycle**: Comprehensive end-to-end journey spanning key provisioning, website publishing, schedule management, content generation, cron poller execution, widget feed querying, and credential revocation.

---

## 3. Feature Inventory Coverage Matrix

| Feature ID | Feature Area | Endpoint / Tool / Path | Auth Model | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|---|:---:|:---:|:---:|:---:|
| **R1.1** | System Health | `GET /v1/health` | Public | ✅ | — | — | ✅ |
| **R1.2** | SRN Tool Manifest | `GET /v1/manifest` | Bearer (API Key / SRN) | ✅ | ✅ (401) | ✅ | ✅ |
| **R1.3** | AI Post Generation | `POST /v1/generate_post` | Bearer (API Key / SRN) | ✅ | ✅ (400, 401) | — | ✅ |
| **R1.4** | Multi-Platform Publish | `POST /v1/publish_post` | Bearer (API Key / SRN) | ✅ | ✅ (400, 401) | ✅ | ✅ |
| **R1.5** | One-Shot Gen & Publish | `POST /v1/generate_and_publish` | Bearer (API Key / SRN) | ✅ | ✅ (400, 401) | — | ✅ |
| **R1.6** | Post History Retrieval | `GET /v1/get_history` | Bearer (API Key / SRN) | ✅ | ✅ (401) | ✅ | ✅ |
| **R1.7** | Website Config | `GET /v1/get_site_config` | Bearer (API Key / SRN) | ✅ | ✅ (401) | — | ✅ |
| **R1.8** | Publish Website Hub | `POST /v1/set_published` | Bearer (API Key / SRN) | ✅ | ✅ (400, 401) | — | ✅ |
| **R1.9** | Specials CRUD | `/api/specials` (GET, POST, PUT, DEL, CANCEL) | Flask-Login Session | ✅ | ✅ (400, 404, 409) | ✅ | ✅ |
| **R1.10** | Events CRUD | `/api/events` (GET, POST, PUT, DEL, CANCEL) | Flask-Login Session | ✅ | ✅ (400, 404, 409) | — | ✅ |
| **R1.11** | Hours Overrides CRUD | `/api/hours` (GET, POST, PUT, DEL, CANCEL) | Flask-Login Session | ✅ | ✅ (400, 404, 409) | — | ✅ |
| **R2.1** | MCP Repo Structure | `get_repo_structure` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R2.2** | MCP File Reader | `read_file` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R2.3** | MCP Audit Checklist | `audit_repo` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R2.4** | MCP File Writer | `write_file` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R2.5** | MCP Issue Management | `list_open_issues`, `create_issue` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R2.6** | MCP Commits Listing | `list_recent_commits` | `GITHUB_TOKEN` | ✅ | — | — | — |
| **R3.1** | Cron Publish Poller | `GET/POST /api/cron/publish` | `Bearer <CRON_SECRET>` | ✅ | ✅ (401) | ✅ | ✅ |
| **R3.2** | Cron Generate Poller | `GET/POST /api/cron/generate` | `Bearer <CRON_SECRET>` | ✅ | ✅ (401) | ✅ | ✅ |
| **R3.3** | Cron Health Check | `GET /api/cron/health` | Public | ✅ | — | ✅ | — |
| **R4.1** | Embed Slug Lookup | `GET /api/embed/<slug>` | Public | ✅ | ✅ (404) | ✅ | ✅ |
| **R4.2** | Embed Username Fallback | `GET /api/embed/<username>` | Public | ✅ | — | — | ✅ |
| **R4.3** | Embed Posts Filter | `GET /api/embed/<slug>` (published only) | Public | ✅ | — | ✅ | ✅ |
| **R4.4** | Drop-in JS Widget | `static/embed.js` | Public Static Asset | ✅ | — | — | — |

---

## 4. Test Runner Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Pytest Test Runner                    │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────┐             ┌───────────────────────┐
│  Flask Web Client     │             │  FastMCP Tool Runner  │
│  (HTTP / JSON API)    │             │  (Direct Tool Exec)   │
└───────────┬───────────┘             └───────────┬───────────┘
            │                                     │
            ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    SQLite In-Memory / File                  │
│   (users, api_keys, specials, events, hours, post_history)  │
└─────────────────────────────────────────────────────────────┘
```

- **Runner**: `pytest` 9.x with `pytest-asyncio` / standard fixture injection.
- **Client**: `app.test_client()` configured with `TESTING=True`, `WTF_CSRF_ENABLED=False`, and isolated SQLite database.
- **Isolation Boundaries**:
  - `UniversalPublisher` network calls mocked using `unittest.mock.patch` to prevent unauthenticated outbound HTTP requests to Meta/Google/TikTok.
  - `PyGithub` client mocked for MCP tools to verify tool logic without requiring live GitHub tokens.
  - `api_keys` hash generation and matching via standard `hashlib.sha256`.

---

## 5. Pass / Fail Semantics

- **HTTP Status Codes**: Exact status assertions (200, 201, 302, 400, 401, 403, 404, 409, 410).
- **JSON Contract Compliance**: Assertions check for `success: True/False`, exact error codes (`MISSING_AUTH`, `INVALID_KEY`, `KEY_EXPIRED`, `MISSING_TOPIC`, `MISSING_CAPTION`), and data field types.
- **Tenant Isolation**: Verifies that user A cannot view, mutate, or delete records created by user B.
- **Exit Code**: Test suite execution must terminate with exit code 0 (`0 failures`, `0 errors`).

---

## 6. Fixture Design

1. `app`: Session-scoped Flask app with SQLite database configured and tables initialized.
2. `client`: Function-scoped Flask test client.
3. `e2e_db_setup`: Fixture that ensures all canonical schema tables exist before executing tests.
4. `mock_user_a` & `mock_user_b`: Deterministic user fixtures with distinct UUIDs and profile metadata for multi-tenant isolation tests.
5. `logged_in_client`: Authenticated client configured with Flask-Login session transaction.
6. `user_a_api_key`: Active API key (`pp_live_...`) generated and persisted for user A.
