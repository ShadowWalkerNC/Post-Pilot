# Review & Adversarial Challenge Report — Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller)

**Reviewer**: Reviewer 1 (`reviewer_m3_1`)  
**Verdict**: **APPROVE**  
**Integrity Assessment**: **CLEAN (No integrity violations detected)**  
**Overall Risk Assessment**: **LOW**  

---

## 1. Observation

Direct inspection was performed across all 8 target components and verification test runs:

1. **`modules/models.py` (InboxItem Model & CRUD)**:
   - Contains full `inbox_items` table schema with all columns (`id`, `user_id`, `platform`, `platform_post_id`, `platform_comment_id`, `author_id`, `author_name`, `comment_text`, `comment_time`, `post_context`, `sentiment`, `ai_draft_reply`, `final_reply`, `status`, `auto_replied`, `replied_at`, `hidden_at`, `created_at`, `updated_at`).
   - Declares status constants (`STATUS_PENDING`, `STATUS_APPROVED`, `STATUS_AUTO_REPLIED`, `STATUS_HIDDEN`, `STATUS_SKIPPED`) and sentiment constants (`SENTIMENT_POSITIVE`, `SENTIMENT_NEUTRAL`, `SENTIMENT_NEGATIVE`, `SENTIMENT_QUESTION`, `SENTIMENT_SPAM`).
   - Implements parameterized SQLite/Postgres queries for `get_by_id`, `get_by_comment_id`, `list_by_user`, `count_by_user`, `create`, `update_draft`, `mark_replied`, `mark_hidden`, and `mark_skipped`. All update/mutation methods enforce `user_id` scoping to prevent IDOR vulnerabilities.

2. **`alembic/versions/0008_inbox.py` (Database Migration)**:
   - Revision ID `0008` correctly revises `0006`.
   - Defines table `inbox_items` with matching column types, `UniqueConstraint('platform', 'platform_comment_id', name='uq_inbox_platform_comment')`, and 4 explicit indices: `idx_inbox_user`, `idx_inbox_user_status`, `idx_inbox_user_sentiment`, and `idx_inbox_platform_comment`.
   - `downgrade()` systematically drops indices and the table.

3. **`modules/meta_api.py` & `modules/meta_client.py` (Graph API Extensions)**:
   - Facebook endpoints: `GET /{post_id}/comments` (`get_facebook_comments`), `POST /{comment_id}/comments` (`reply_to_facebook_comment`), and `POST /{comment_id}` with `is_hidden=True` (`hide_facebook_comment`).
   - Instagram endpoints: `GET /{media_id}/comments` (`get_instagram_comments`), `POST /{comment_id}/replies` (`reply_to_instagram_comment`), and `POST /{comment_id}` with `hide=True` (`hide_instagram_comment`).
   - Universal routers `fetch_comments`, `reply_to_comment`, and `hide_comment` correctly dispatch by platform string (`'fb'`/`'facebook'` vs `'ig'`/`'instagram'`).

4. **`modules/reply_agent.py` (Sentiment Analysis & AI Reply Drafting)**:
   - `classify_sentiment(comment_text)` implements a 5-class evaluation pipeline with prioritized regex evaluation: Spam → Negative → Question → Positive → Neutral.
   - `_get_fallback_reply` defines a deterministic 5-sentiment × 5-tone (`friendly`, `hype`, `urgent`, `funny`, `community`) template matrix with business name and location interpolation. Spam comments return an empty reply string (`""`).
   - `_call_claude_llm` and `_call_openai_llm` implement structured JSON schema response formatting (`{"sentiment": "...", "reply": "..."}`). When API keys are unavailable or fail, execution falls back cleanly to regex classification and template generation without throwing unhandled exceptions.

5. **`modules/comment_poller.py` (Comment Ingestion & Deduplication)**:
   - `poll_user_comments(user_id)` queries connected Meta platform tokens via `load_token('facebook', user_id)`, fetches Facebook page posts/comments and Instagram media comments, deduplicates using `InboxItem.get_by_comment_id`, performs sentiment analysis & draft generation, and stores pending items.
   - `poll_all_active_users()` discovers distinct active users with Meta platform tokens and processes each in turn, aggregating totals and logging errors without aborting on single-user exceptions.

6. **`blueprints/cron.py` (`/api/cron/poll_comments` Endpoint)**:
   - Supports `GET` (Vercel Cron invocation) and `POST` (manual invocation).
   - Validates `Authorization: Bearer <CRON_SECRET>` using `hmac.compare_digest`. Rejects requests with 401 when `CRON_SECRET` is unset or invalid.

7. **`blueprints/inbox.py` & `templates/inbox.html` (Plan Guards, Dashboard UI & REST Endpoints)**:
   - Plan tier gating:
     - `@require_plan('starter')`: `/inbox` page, `/api/inbox/items` listing, `/api/inbox/stats`, `/api/inbox/poll_now`, `/api/inbox/<item_id>/skip`.
     - `@require_plan('pro')`: `/api/inbox/<item_id>/reply`, `/api/inbox/<item_id>/regenerate`, `/api/inbox/<item_id>/hide`.
   - Strict tenant isolation: All API handlers resolve `uid = _uid()` and verify item ownership before modifying state (unowned items return 404).

8. **`tests/test_inbox.py` (Verification Test Suite)**:
   - Execution command: `pytest tests/test_inbox.py -v`
   - Result: 23 passed in 7.10s (100% pass rate).
   - Covers: Model CRUD & unique constraint deduplication, sentiment analysis, tone matrix fallback, Meta API client calls, poller ingestion, plan guard enforcement, REST moderation endpoints, multi-tenancy cross-user isolation, and cron HMAC authentication.

---

## 2. Logic Chain

1. **Schema & Migration Consistency**: The `inbox_items` schema in `alembic/versions/0008_inbox.py`, `modules/models.py`, and `tests/conftest.py` are strictly identical. The composite unique constraint `(platform, platform_comment_id)` ensures database-level deduplication idempotency across repeated cron poll cycles.
2. **Meta Graph API Conformance**: Graph API calls in `modules/meta_api.py` and `modules/meta_client.py` use official v19.0 endpoint signatures for comment retrieval, comment reply threading, and comment hiding.
3. **Resilience & Fallback**: `modules/reply_agent.py` implements a layered sentiment and reply generation pipeline (Claude Haiku → OpenAI GPT-4o-mini → Rule-based Regex + Tone Matrix). The fallback ensures uninterrupted service even if external LLM provider APIs encounter outages or quota limits.
4. **Security & Monetization Architecture**: `blueprints/inbox.py` enforces plan differentiation:
   - Free users are blocked with 302 redirect / 403 `PLAN_REQUIRED`.
   - Starter users can ingest, view, filter, and skip comments.
   - Pro users unlock automated AI reply regeneration, 1-click platform replies, and spam comment hiding.
   - All operations are scoped by user ID, preventing cross-tenant data access.
5. **No Integrity Violations**: Source code was verified for authentic logic. No hardcoded test responses, facades, or shortcuts exist.

---

## 3. Caveats

- **Meta Graph API OAuth Scopes**: In a production environment, Meta comment reading, replying, and hiding require the following permissions granted during OAuth: `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`, and `instagram_manage_comments`.
- **Legacy Test Suite State Isolation**: When running the entire global test suite `pytest tests/ -v`, test isolation artifacts in `post_history` in `test_postpilot.db` (exceeding monthly post limits for default test user 1) can affect legacy tests if the DB is not refreshed between test runs. This is unrelated to Milestone M3 codebase (where `tests/test_inbox.py` uses dedicated fixtures and passes 100%).

---

## 4. Conclusion

**Final Verdict**: **`APPROVE`**  
Milestone M3 (AI Social Comment Inbox & Auto-Reply Poller) satisfies all functional, architectural, security, and quality requirements. The code is well-structured, follows Post-Pilot conventions, enforces monetization tiers, maintains multi-tenant isolation, and passes all 23 verification tests.

---

## 5. Verification Method

To independently verify this milestone:

```powershell
# 1. Run Milestone M3 Inbox test suite
pytest tests/test_inbox.py -v

# 2. Inspect Milestone M3 implementation files
# - modules/models.py
# - alembic/versions/0008_inbox.py
# - modules/meta_api.py
# - modules/meta_client.py
# - modules/reply_agent.py
# - modules/comment_poller.py
# - blueprints/cron.py
# - blueprints/inbox.py
# - templates/inbox.html
```

---

## Quality Review Summary

- **Verdict**: APPROVE
- **Findings**:
  - `modules/models.py`: Clean model design with parameterized SQL and strict user isolation.
  - `modules/meta_api.py` / `modules/meta_client.py`: Fully implements Facebook and Instagram Graph API comment operations with unified routing.
  - `modules/reply_agent.py`: Robust 5-class classification and 5-tone deterministic template fallback.
  - `blueprints/inbox.py`: Accurately enforces Starter vs Pro tier boundaries and cross-tenant isolation.
  - `blueprints/cron.py`: Protected with constant-time HMAC `CRON_SECRET` validation.
- **Verified Claims**:
  - `test_create_and_get_by_id` → PASSED
  - `test_deduplication_on_create` → PASSED
  - `test_list_and_count_with_filters` → PASSED
  - `test_mutations` → PASSED
  - `test_to_dict_serialization` → PASSED
  - `test_sentiment_classification_5_classes` → PASSED
  - `test_tone_fallback_matrix` → PASSED
  - `test_spam_reply_is_empty` → PASSED
  - `test_get_facebook_comments` → PASSED
  - `test_get_instagram_comments` → PASSED
  - `test_reply_to_comment_fb_and_ig` → PASSED
  - `test_hide_comment_fb_and_ig` → PASSED
  - `test_poll_user_comments_ingestion` → PASSED
  - `test_poll_all_active_users` → PASSED
  - `test_free_user_blocked_from_inbox` → PASSED
  - `test_starter_user_can_view_and_poll_but_cannot_reply` → PASSED
  - `test_pro_user_can_reply_regenerate_hide` → PASSED
  - `test_inbox_stats_endpoint` → PASSED
  - `test_on_demand_poll_now` → PASSED
  - `test_user_cannot_view_or_moderate_other_user_items` → PASSED
  - `test_cron_rejected_without_secret` → PASSED
  - `test_cron_rejected_with_invalid_secret` → PASSED
  - `test_cron_accepted_with_valid_hmac_secret` → PASSED
- **Coverage Gaps**: None.

---

## Adversarial Challenge Summary

- **Overall Risk Assessment**: LOW
- **Challenges Evaluated**:
  1. *Concurrent Ingestion Race Condition*: Unique constraint on `(platform, platform_comment_id)` ensures DB-level conflict prevention; handled gracefully in `poll_user_comments`.
  2. *Meta API Rate Limiting / Token Invalidation*: `poll_user_comments` uses safe dictionary key lookups (`.get('data', [])`) and try-except blocks that do not crash or 500 when Meta returns error responses.
  3. *Sentiment Boundary Conditions & Prompt Injection*: Priority-based regex heuristics classify spam and critical customer service complaints deterministically before LLM invocation.
  4. *Multi-Tenancy IDOR & Tier Escalation*: All endpoints enforce `@require_plan` and verify `WHERE id = ? AND user_id = ?`, returning 404 for unowned items.
  5. *Cron Header Spoofing*: Protected via `hmac.compare_digest` with fail-closed behavior when `CRON_SECRET` is unset.
