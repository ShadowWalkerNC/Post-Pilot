## 2026-08-19T18:18:43Z

You are test_writer_2 working in C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\.agents\test_writer_2\.
Project root: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot
Original request path: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\ORIGINAL_REQUEST.md
Project plan path: C:\Users\white\OneDrive\Documents\GitHub\Post-Pilot\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Task:
1. Author `TEST_INFRA.md` at project root detailing the 4-tier E2E testing methodology, feature inventory coverage matrix, test runner architecture, pass/fail semantics, and fixture design.
2. Implement the comprehensive E2E test suite in `tests/test_e2e_suite.py` adhering strictly to opaque-box, requirement-driven testing:
   - Tier 1 (Feature Coverage, >=5 tests per feature for R1, R2, R3, R4):
     * R1 Headless REST API (/v1/health, /v1/manifest, /v1/generate_post, /v1/publish_post, /v1/get_history, /v1/get_site_config, /v1/set_published, /api/specials, /api/events, /api/hours)
     * R2 MCP Server Tools (`get_repo_structure`, `read_file`, `audit_repo`, `write_file`, `list_open_issues`, `create_issue`, `list_recent_commits`)
     * R3 AI Comment Moderation & Auto-Reply Poller (/api/cron/publish, /api/cron/generate, /api/cron/health, cron secret auth)
     * R4 Public Embed Feed & Drop-in Widget (/api/embed/<slug>, user lookup by embed_slug & username, 404 on unknown slug, profile data, static/embed.js existence & structure)
   - Tier 2 (Boundary & Corner Cases, >=5 per feature area):
     * Missing Bearer token / unauthorized access (401)
     * Empty strings / missing required parameters (400)
     * Malformed dates (e.g. invalid YYYY-MM-DD or HH:MM)
     * Unauthenticated session endpoints
     * Unknown/missing ID updates and deletes (404)
     * Non-pending status update rejection (409)
   - Tier 3 (Cross-Feature Combinations):
     * Special creation via API -> verified in database and public embed response
     * Post publish via API -> verified in `/v1/get_history`
     * Cron secret verification across endpoints
     * API key creation -> key usage in Bearer token -> key revocation -> rejection
   - Tier 4 (Real-World Application Scenarios):
     * Food truck / restaurant morning setup: configure business profile, add daily specials, add holiday hours override, query public embed feed to verify customer visibility.
     * Lunch rush automation: generate AI post draft, publish post, verify history record, trigger cron publish runner.
     * Full business operational lifecycle spanning API keys, specials, events, hours, post publishing, and embed widget.
3. Run `pytest tests/test_e2e_suite.py -v` and `pytest tests/ -v` to ensure all tests pass with exit code 0.
4. Author `TEST_READY.md` at project root with runner command, tier breakdown, and coverage metrics.
5. Write your complete handoff report to `.agents/test_writer_2/handoff.md` and send a message back.
