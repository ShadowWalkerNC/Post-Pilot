# Merge conflict notes — `cursor/security-fixes-c1-c6-2720` ← `origin/main`

Fetched `origin/main` (includes #13 Wave A/B). All conflicts resolved.

## Resolutions for previously conflicting intents

### 1. `blueprints/__init__.py` — CSRF exemptions

**Applied:** Exempt only M2M + public embed (`v1`, stripe webhook, cron, `embed_bp`).
Session APIs stay CSRF-protected via `static/js/csrf.js` (C1).

### 2. `blueprints/api.py` — `api_setup_tokens`

**Applied:** main’s always-`410 Gone` (OAuth-only). Security tests updated.

## Resolved (simple)

| File | Resolution |
|------|------------|
| `CHANGELOG.md` | Kept both Docs/Fixed (main) and Security/Tests (this PR) |
| `TODO.md` | Kept security checklist + main’s Phase 5 go-live structure |
| `app.py` | HttpOnly/SameSite always; Secure in prod |
| `blueprints/api.py` (get_db only) | Dropped redundant local imports; top-level `from modules.database import get_db` wins |
| `blueprints/cron.py` | Generic `"Internal error"` body (no exception leak) |
| `modules/auth_manager.py` | Combined `_is_production()` helper + main’s `sys.exit` messages |
| `templates/schedule.html` | Main nav + CSRF include; dropped main’s stray `Schedule — Post-Pilot` text glitch |
| `blueprints/__pycache__/*` | Kept deleted (C4 / matches main untrack) |

## Also note

PR #11 (`cursor/security-audit-2720`, docs-only) also conflicts with main on overlapping docs (`TODO.md` etc.). Resolve #12 first, then rebase/close #11 or cherry-pick `docs/SECURITY_AUDIT.md` onto main.
