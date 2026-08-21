## 2026-08-19T12:33:49Z
You are Sub-Orchestrator for Milestone M3 (sub_orch_m3).
Working directory: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\sub_orch_m3\
Project root: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot
Original request path: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\ORIGINAL_REQUEST.md
Project plan path: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\PROJECT.md
Survey report path: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\explorer_survey_3\survey_report.md

Your scope: Milestone M3 — AI Social Comment Inbox & Auto-Reply Poller (Phase 3).
Requirements to deliver:
1. Database Schema & Migration:
   - Schema for `inbox_items` table (id, user_id, platform, platform_post_id, platform_comment_id, author_id, author_name, comment_text, comment_time, post_context, sentiment, ai_draft_reply, final_reply, status, auto_replied, replied_at, hidden_at, created_at, updated_at).
   - Alembic migration `alembic/versions/0008_inbox.py` and ensure SQLite table creation in `modules/db.py` / `tests/conftest.py`.
2. Meta Graph API Client Extensions (`modules/meta_api.py` / `modules/meta_client.py`):
   - Ingest post comments for Facebook (`/{post_id}/comments`) and Instagram (`/{media_id}/comments`).
   - Reply to comments for Facebook (`/{comment_id}/comments`) and Instagram (`/{comment_id}/replies`).
   - Hide comments for Facebook (`is_hidden=true`) and Instagram (`hide=true`).
3. Tone-Matched Reply Agent (`modules/reply_agent.py`):
   - Sentiment analysis (`positive`, `neutral`, `negative`, `question`, `spam`).
   - Claude AI draft response generation matching hospitality business context & tone prompts (`hype`, `friendly`, `urgent`, `funny`, `community`).
   - Deterministic fallback templates when AI service is unavailable.
4. Background Polling & Cron (`modules/comment_poller.py`):
   - Periodic polling logic that fetches recent comments, classifies sentiment, generates AI draft replies, and stores in `inbox_items`.
   - `/api/cron/poll_comments` endpoint in `blueprints/cron.py` protected by HMAC `CRON_SECRET`.
   - `/api/inbox/poll_now` on-demand polling trigger for authenticated users.
5. Dashboard Moderation Review Interface (`blueprints/inbox.py`, `templates/inbox.html`):
   - Interactive comment moderation dashboard with status tabs (`pending`, `approved`, `auto_replied`, `hidden`, `skipped`).
   - Actions: 1-click Approve & Send, Edit & Send, Regenerate AI Draft, Hide Spam, Skip.
   - Enforce plan guards (`inbox_read`, `inbox_reply`).
6. Unit & Integration Tests:
   - Create comprehensive test suite `tests/test_inbox.py` verifying comment polling, sentiment analysis, AI drafting, moderation actions, and cron security.
   - Ensure 100% test pass on `pytest tests/ -v` with no regressions.

## 2026-08-19T18:18:07Z
From: parent (9d8a9f72-cf31-4df3-9362-39a4628924f2)
**Context**: Milestone M3 Progress Check
**Content**: Status report requested. Please provide your progress, current iteration step, and results for Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller).
**Action**: Send your current progress update and handoff report.
