# Post-Pilot Provider-Agnostic Migration Plan

Goal: reorganize the flat `modules/` + `blueprints/` layout into provider-agnostic
packages without changing runtime behavior. Flask is kept as the web framework;
this is a file-move + interface-cleanup migration, not a rewrite.

## 1. Target tree

```
core/            # cross-cutting: config, auth session, plan_guard, validator, tokens
ai/              # caption generation: ai_generator, generator, post_generator,
                 #   platform_adapter, reply_agent
skills/          # domain skills: automation_agent, scheduler, post_scheduler,
                 #   scheduler_worker, location_service, notification_service,
                 #   media_handler, website_manager
integrations/    # provider clients behind a common interface:
                 #   base.py (new), meta.py, google.py, tiktok.py
mcp/             # keep, import from new packages (server.py only)
api/             # HTTP layer: api_v1.py (+ ported keys/site_config routes),
                 #   embed_api.py, cron.py
web/             # browser UI: auth.py, billing.py, pages.py, website.py,
                 #   specials.py, events.py, hours.py, inbox.py, api.py, utils.py
db/              # database.py, db.py, models.py, analytics.py,
                 #   analytics_client.py (+ alembic/ unchanged at root)
tests/           # unchanged layout, imports updated per phase
```

## 2. Phase order

| Phase | Work | Gate |
|---|---|---|
| 0 | Freeze: all tests green on current tree; record route table (`/v1/*` + `/api/v1/*`) | pytest green |
| 1 | `db/`: move database.py, db.py, models.py, analytics*.py; add shim imports in `modules/` | pytest green, no caller edits |
| 2 | `integrations/`: canonicalize Meta client (see §4-A), add `base.py` provider ABC; move google/tiktok clients; route `publisher.py` fb/ig calls through `meta.py` | Meta publish + inbox tests green |
| 3 | `ai/`: move generators + platform_adapter + reply_agent | generate tests green |
| 4 | `skills/`: move scheduler_worker (WITH captions fix, §4-C), automation_agent, scheduler shims, services | cron/scheduler tests green |
| 5 | `api/`: port keys CRUD + site_config + set_published from api_manager into api_v1 (see §4-B); move embed_api, cron | route-table diff: no route lost |
| 6 | `web/`: move remaining blueprints; `core/`: plan_guard, validator, auth_manager, user_manager, billing_manager, utils | full pytest green |
| 7 | Delete `modules/` shims + deprecated files only after Phase 6 gate (§6) | test-before-delete gate |

Rules: one phase per PR; each phase = move + shim + import updates, no logic
changes except the two in-scope fixes (§4-B port, §4-C captions).

## 3. Per-file migrate-or-deprecate table

### modules/ → new homes

| File | Target | Action |
|---|---|---|
| meta_api.py | integrations/meta.py | MIGRATE (canonical Meta client) |
| meta_client.py | — | DEPRECATE (zero importers; byte-near-identical to meta_api.py) |
| publisher.py | integrations/publisher.py | MIGRATE (route fb/ig via meta.py) |
| google_client.py | integrations/google.py | MIGRATE |
| tiktok_client.py | integrations/tiktok.py | MIGRATE |
| ai_generator.py, generator.py, post_generator.py | ai/ | MIGRATE (same names) |
| platform_adapter.py, reply_agent.py | ai/ | MIGRATE |
| scheduler_worker.py | skills/scheduler_worker.py | MIGRATE + captions fix (§4-C) |
| scheduler.py, post_scheduler.py | skills/ | MIGRATE as shims (keep re-exports) |
| automation_agent.py | skills/ | MIGRATE |
| location_service.py, notification_service.py | skills/ | MIGRATE |
| media_handler.py, website_manager.py | skills/ | MIGRATE |
| comment_poller.py | skills/ | MIGRATE (uses canonical meta.py) |
| api_manager.py | — | DEPRECATE after porting keys/site_config/set_published into api/ (§4-B) |
| database.py, db.py, models.py | db/ | MIGRATE (needs ARCHITECT + DATABASE review per repo rules) |
| analytics.py, analytics_client.py | db/ | MIGRATE |
| auth_manager.py, user_manager.py | core/ | MIGRATE |
| billing_manager.py, plan_guard.py, validator.py | core/ | MIGRATE |

### blueprints/ → new homes

| File | Target | Action |
|---|---|---|
| api_v1.py | api/v1.py | MIGRATE (canonical REST API) |
| embed_api.py, cron.py | api/ | MIGRATE |
| auth.py, billing.py, pages.py, website.py | web/ | MIGRATE |
| specials.py, events.py, hours.py, inbox.py | web/ | MIGRATE |
| api.py (dashboard session APIs) | web/ | MIGRATE |
| utils.py (`_get_tokens`) | core/tokens.py | MIGRATE (keep `blueprints.utils` shim 1 release) |

### Keep in place

`app.py` (import paths only), `alembic/` (untouched), `mcp/server.py`
(import updates only), `templates/`, `static/`, `tests/` (import updates only).

## 4. Key decisions

**A. Canonical Meta client = `meta_api.py`.** Verified importers:
`modules/comment_poller.py:14`, `modules/scheduler_worker.py:105`,
`blueprints/inbox.py:23` — all import from `meta_api`. `meta_client.py` has
zero importers and a near-identical `MetaAPI` class → delete in Phase 7.
`publisher.py` currently uses inline `requests.post` for fb/ig (imports only
google/tiktok clients) → Phase 2 routes fb/ig through `integrations/meta.py`.

**B. Canonical API = `blueprints/api_v1.py` (`/api/v1`).**
`modules/api_manager.py` (Blueprint `v1`, prefix `/v1`) overlaps it:
both expose generate/publish/history. `api_v1` is larger and RESTful
(`/posts/*`, specials/events/hours CRUD). `api_manager` uniquely owns
keys CRUD (`/keys/create`, `/keys`, `/keys/revoke`), `/get_site_config`,
`/set_published` → port these into `api/` in Phase 5, then deprecate
`api_manager.py`. Route-table compare (Phase 0 artifact) must show zero
lost routes after the port.

**C. Scheduler captions fix is in scope (Phase 4).**
`publisher.push_all()` accepts per-platform `captions` dict (Option B) and its
docstring claims `scheduler_worker` passes it — but
`_publish_scheduled_posts()` SELECTs only
`(id, user_id, caption, content_type, image_url, video_url, platforms)`
(`modules/scheduler_worker.py:212`) and calls `push_all` without `captions`
(lines 239–245), so scheduled posts lose per-platform adaptation. Phase 4
adds the `captions` column read + kwarg passthrough (with migration if the
column is missing).

**D. Flask is kept.** Serverless/Vercel + Flask-Limiter + blueprints stay;
`api/` and `web/` remain Flask blueprints, only relocated.

**E. Provider interface.** New `integrations/base.py` defines a minimal
`ProviderClient` ABC (`publish`, `schedule`, `get_insights`); meta/google/
tiktok adapt to it incrementally — no behavior change in this migration.

## 5. Preserved behaviors (must not regress)

- Meta publish (fb feed/photos, ig container+publish, scheduling)
- Stripe checkout / portal / webhook lifecycle
- Supabase magic-link auth + session handling
- Cron (`/api/cron/*`, CRON_SECRET) and APScheduler background worker
- Inbox poll/reply/hide flows
- Full pytest suite green at every phase gate

## 6. Test-before-delete gate (Phase 7)

Nothing is deleted until ALL hold on the same commit:

1. `pytest` (full suite) green with `modules/` shims removed from `sys.path`.
2. Route-table diff (Phase 0 snapshot vs current) shows zero lost routes.
3. `grep -rn "modules\.meta_client\|modules\.api_manager" --include=*.py` +
   `grep -rn "from modules import\|from modules\."` return zero hits outside
   deleted shims.
4. Vercel preview smoke test green (login → generate → schedule → publish).

Only then: delete `modules/meta_client.py`, `modules/api_manager.py`,
remaining `modules/*` shims, and the old `blueprints/` paths.
