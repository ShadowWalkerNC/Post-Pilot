## 2026-08-19T18:18:27Z
You are Worker for Milestone M3 (worker_m3_2).
Working directory: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\worker_m3_2\
Project root: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot

Read the following files before starting:
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\ORIGINAL_REQUEST.md
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\PROJECT.md
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\sub_orch_m3\SCOPE.md
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\explorer_m3_1\report.md (DB schema, models, migrations)
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\explorer_m3_2\report.md (Meta API, AI reply agent, comment poller & cron)
- C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\explorer_m3_3\report.md (Inbox blueprint, UI template, plan guards, test suite)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Goal: Implement and verify all components for Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller).

Tasks & Write Ownership:
1. `modules/models.py`:
   - Add `InboxItem` model class with all required columns (`id`, `user_id`, `platform`, `platform_post_id`, `platform_comment_id`, `author_id`, `author_name`, `comment_text`, `comment_time`, `post_context`, `sentiment`, `ai_draft_reply`, `final_reply`, `status`, `auto_replied`, `replied_at`, `hidden_at`, `created_at`, `updated_at`), constants (`STATUS_*`, `SENTIMENT_*`), dictionary serialization (`to_dict()`), and static query methods (`get_by_id`, `get_by_comment_id`, `list_by_user`, `count_by_user`, `create`, `update_draft`, `mark_replied`, `mark_hidden`, `mark_skipped`).
2. `alembic/versions/0008_inbox.py`:
   - Create Alembic migration script for `inbox_items` table with all columns, indices, unique constraint on `(platform, platform_comment_id)`, and `down_revision = '0006'`.
3. `modules/meta_api.py` & `modules/meta_client.py`:
   - Add comment fetching (`get_facebook_comments`, `get_instagram_comments`, `fetch_comments`), comment replying (`reply_to_facebook_comment`, `reply_to_instagram_comment`, `reply_to_comment`), and comment hiding (`hide_facebook_comment`, `hide_instagram_comment`, `hide_comment`).
4. `modules/reply_agent.py`:
   - Implement `analyze_and_draft(comment_text, post_context=None, tone='friendly', business_name='Our Business', business_type='restaurant', location='')`.
   - Implement 5-class sentiment analysis (`positive`, `neutral`, `negative`, `question`, `spam`) with rule-based regex fallback and Claude / OpenAI LLM integration.
   - Implement tone prompt matching (`hype`, `friendly`, `urgent`, `funny`, `community`) and deterministic fallback template matrix when AI APIs are unavailable.
5. `modules/comment_poller.py`:
   - Implement `poll_user_comments(user_id)` and `poll_all_active_users()`.
   - Ingest comments from Meta Graph API, deduplicate by `platform_comment_id`, classify sentiment, generate AI draft replies, and store in `inbox_items`.
6. `blueprints/cron.py`:
   - Add `/api/cron/poll_comments` route (GET and POST) protected by HMAC `CRON_SECRET` validation.
7. `blueprints/inbox.py`:
   - Implement `/inbox` dashboard route with status, sentiment, and platform filters.
   - Implement `/api/inbox/poll_now`, `/api/inbox/<item_id>/reply`, `/api/inbox/<item_id>/regenerate`, `/api/inbox/<item_id>/hide`, `/api/inbox/<item_id>/skip`, `/api/inbox/stats`.
   - Enforce plan tier guards (`@require_plan('starter')` for viewing/polling, `@require_plan('pro')` for replying/regenerating/hiding).
8. `blueprints/__init__.py`:
   - Register `inbox_bp` and add `csrf.exempt(inbox_bp)`.
9. `templates/inbox.html`:
   - Create full-featured dark-theme Tailwind UI matching Post-Pilot style (`#07071a` background) with status tabs, sentiment pills, post context preview, inline draft reply editor, tone pills, and 1-click action buttons with toast notifications.
10. `templates/dashboard.html` / `templates/base.html`:
    - Add Inbox navigation item.
11. `tests/conftest.py`:
    - Add `inbox_items` SQLite table creation to the `app` fixture.
12. `tests/test_inbox.py`:
    - Create comprehensive test suite testing plan gating, dashboard rendering, moderation actions, mock Meta API calls, Claude reply agent & fallbacks, cross-user isolation, and cron poller.
