# Post-Pilot — Full Product & Engineering Audit

> **Date:** 2026-08-08  
> **Roles applied:** Architect · Backend · Frontend/UX · Security · DevOps · QA · Product  
> **Goal:** Sellable SaaS for food trucks / restaurants / hospitality operators  
> **Companion docs:** `PLANNING.md` (strategy) · `TODO.md` (checklist) · this file (truth + waves)

---

## Executive verdict

The **product shape is right** for the ICP: write once → adapt → publish/schedule → specials/events/hours → Stripe tiers → Vercel cron.  
The **implementation contracts are broken**. Today it is not safe to take paid customers.

Do **not** rewrite the stack. Run a **contract-repair + honesty + phone-first** program in waves below.

---

## Strengths (keep)

| Area | Why keep |
|---|---|
| Vertical positioning | Food / hospitality workflows beat generic Buffer/Hootsuite messaging |
| Blueprint domain split | auth / api / billing / cron / pages / specials is clean |
| Fernet `platform_tokens` | Correct encryption model when key is stable |
| OpenAI master + platform adapt | Good “Option B” product loop |
| `UniversalPublisher` routing | Extend, don’t replace |
| Stripe surface area | Checkout / portal / webhook event set is correct |
| `plan_guard` + `billing.html` tiers | Free / $19 / $49 / $99 is coherent |
| Specials → Events → Hours → agent | Real retention engine for food businesses |
| Validator + XSS escape patterns | Solid foundations |
| Magic-link auth direction | Right for non-technical operators |

---

## Weaknesses (fix or replace)

### Architecture / backend (stop-ship)

1. `User.is_active` assignment crashes Flask-Login `UserMixin` — sessions broken  
2. `from app import get_db` but `app` has no `get_db` — specials/events/hours/embed/API DB paths fail  
3. Stripe webhooks call `update_subscription(tier=…, sub_status=…)` but method only accepts `plan=` — paid upgrades never stick  
4. `log_post` signature ≠ API callers; writes `post_queue` while schema/automation use `post_history`  
5. `save_business_profile` missing — onboarding/setup cannot persist what the agent reads  
6. Cron routes are POST-only; Vercel Cron sends GET → 405 in production  
7. Ephemeral Fernet key if `TOKEN_ENCRYPTION_KEY` unset — silent token loss on serverless  
8. Schema drift: Alembic (`subscription_tier`, `display_name`) vs code (`plan`, `full_name`) vs docs (`pp.posts` fiction)

### Security / billing

9. `/register?plan=agency` can upsert a paid plan without Stripe  
10. Entire `api_bp` + specials/events/hours CSRF-exempt with cookie sessions  
11. `/api/setup_tokens` accepts arbitrary OAuth tokens from the browser  
12. `check_post_limit` never wired; cron ignores plan gates  
13. `past_due` not enforced in `require_plan`  
14. Rate limiter installed with **zero** limits  
15. `.venv` still tracked (~13k files)

### UX / sellability

16. Login/register still show **password** fields; backend is magic-link only  
17. `magic_link_sent.html` extends missing `base.html`  
18. Landing pricing sells Growth $29 / Pro $79; live billing is $19/$49/$99  
19. Landing Free claims AI + 7 posts/week; product Free is 5 posts/mo, manual, AI gated  
20. Schedule extends `dashboard.html` which has **no** `{% block content %}`  
21. Dashboard is desktop-three-column; phone-first owners lose nav  
22. Fake “Live” / hardcoded upcoming posts destroy trust  
23. Brand split: Post-Pilot vs PostPilot Pro  
24. Overclaims (morning prompt, full TikTok auto, inbox) sold as live

### What to replace (not rebuild)

| Replace | With |
|---|---|
| Password UI | Email-only magic link |
| Landing fake tiers | Canonical Free/Starter/Pro/Agency |
| `post_queue` writes | `post_history` (canonical) |
| APScheduler mental model | Vercel Cron only |
| Railway/Render leftovers | Delete; Vercel-only |
| Raw token POST `/api/setup_tokens` | OAuth-only connect flow |
| Growth Stripe orphans | Already removed from maps; keep out |
| Demo hardcodes in dashboard | Live queries or honest empty states |

---

## Sellable product definition (final)

**Promise (honest):**  
“Update Facebook, Instagram, and your website from one place — specials, events, and hours included.”

**Day-1 job to be done:**  
Owner adds tomorrow’s special → AI drafts captions → preview → publish or schedule → done in under 2 minutes on a phone.

**Tier truth (canonical):**

| Tier | Price | Reality |
|---|---|---|
| Free | $0 | Manual publish, 5 posts/mo, 3 platforms, no agent |
| Starter | $19 ($15/yr equiv) | Agent, 30 posts, basic embed, inbox read (when built) |
| Pro | $49 | Unlimited posts, AI replies, full embed, API |
| Agency | $99 | Up to 5 locations (build before selling hard) |

**Do not sell as live until built:** morning prompt, location one-tap, inbox AI, full TikTok/YouTube/Google publish, multi-location agency UX.

---

## Execution waves (systematic)

Edit each file **once per wave**. Do not revisit lines until the next wave needs them.

### Wave A — Contract repair (P0 backend) ← **current**

1. `modules/user_manager.py` — User props, subscription fields, `update_subscription`, `log_post`→`post_history`, `save_business_profile`, post counts  
2. `app.py` — re-export `get_db`, prod cookie flags, TOKEN key guard coordination  
3. `modules/auth_manager.py` — refuse ephemeral key in production  
4. `blueprints/cron.py` — GET+POST  
5. `blueprints/auth.py` — never upsert paid plan; checkout redirect only  
6. `modules/plan_guard.py` — `past_due` gate + correct `url_for`  
7. `blueprints/api.py` — post limits, harden/disable `setup_tokens`, stable `get_db`

### Wave B — Conversion honesty (P0 UX)

8. `templates/login.html` / `register.html` — magic link only, Post-Pilot brand  
9. `templates/magic_link_sent.html` — standalone dark page  
10. `templates/index.html` — pricing + FAQ + legal URLs match product  
11. `templates/schedule.html` — standalone (no broken extends)  
12. Nav: add Schedule + Generate links where the shell allows

### Wave C — Ops hygiene

13. `git rm --cached .venv` (SEC-2)  
14. Delete `railway.toml` when confirmed unused  
15. Fix `tests/conftest.py` so the app boots  
16. DEPLOY webhook path `/webhooks/stripe` (docs already updated)

### Wave D — Activation / retention

17. Phone shell (bottom nav)  
18. Photo upload (not URL-only)  
19. Empty-state playbooks on schedule/generate  
20. Wire cron plan gates + agent activity log  
21. FB long-lived token exchange  
22. Narrow CSRF exemptions + JS tokens

### Wave E — Differentiation

23. Morning prompt + location one-tap  
24. Inbox  
25. Finish Google/TikTok publish quality  
26. Agency multi-location UX

---

## Success metrics (soft launch)

- Magic link → dashboard works on mobile  
- Stripe webhook activates Starter within 60s  
- Cron GET generate+publish returns 200 with secret  
- Free user blocked from agent; Starter can schedule a special  
- Landing price == billing price  
- Zero password fields in auth UI  
- No `.venv` in git index  

---

## Explicit non-goals (this quarter)

- Rewriting in Next.js / leaving Flask  
- Switching AI provider again  
- Building Agency white-label before Wave A–C are green  
- Competing on “all 6 platforms auto” marketing until Meta path is rock solid
