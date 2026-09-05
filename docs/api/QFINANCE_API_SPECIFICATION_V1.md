# QFinance — API Specification V1

**Status:** 🔒 LOCKED — final cross-document verification completed 2026-08-31 under founder-authorized autonomous execution (`work_memory.md` §28A/§30). No blocking contradiction found against the PRD, Architecture V1, or Database Schema V1.
**Depends on:** `docs/PRD/QFINANCE_MVP_PRD_V1.md` (🔒 LOCKED), `docs/architecture/QFINANCE_ARCHITECTURE_V1.md` (🔒 APPROVED, §4/§7–§13), `docs/database/QFINANCE_DATABASE_SCHEMA_V1.md` (🔒 APPROVED), `work_memory.md`
**Document type:** Endpoint-level REST API contract (paths, methods, request/response shapes, auth/RBAC, status codes), derived strictly from the three approved artifacts above
**Project root:** `/home/prd/Projects/QFinance`

**Scope discipline (per the same standing process as the prior two artifacts):** This document introduces **no new product features and no new architectural decisions**. Every endpoint below implements a requirement already locked in the PRD, using the module boundaries already fixed in Architecture §4.2 and the tables/columns already fixed in Database Schema V1. Where Architecture explicitly deferred a detail to "the API-spec phase" (the `subscriptions`-row-creation-sequencing question, Architecture §17 Remaining Technical Question #5), this document resolves it at the implementation-sequencing level only — not as a new product or architecture decision. This is a **design document**, not running code — no FastAPI route files are created, no server is started, nothing here has been executed.

---

## 0. Conventions

### 0.1 Base path and versioning
All endpoints are mounted under `/api/v1` (API-001). No unversioned routes exist. A breaking change to any endpoint in this document would require a new `/api/v2` prefix, not an in-place change — this document does not need to specify that process further since no v2 work exists yet.

### 0.2 Authentication
Per Architecture AD-03/§7: authentication is a secure, HttpOnly, `Secure`, `SameSite=Lax` session cookie (`qf_session`), opaque token, session data held server-side in Redis. Every endpoint below is tagged:
- **Public** — no session required.
- **Authenticated** — valid `qf_session` required; any of the 6 roles.
- **Authenticated + Verified** — valid session AND `users.email_verified_at IS NOT NULL` (AUTH-002).
- **Role-gated** — valid session AND the caller's `profiles.role_grants` includes a specific capability, per the Architecture §8 / PRD §30 matrix (spelled out per-endpoint below, never left implicit).

CSRF (Architecture §13/AD-14): every mutating request (`POST`/`PUT`/`PATCH`/`DELETE`) other than `/webhooks/*` must include header `X-CSRF-Token` matching the `csrf_token` cookie, or the request is rejected `403 CSRF_MISMATCH` before any other processing. This applies uniformly and is not repeated per-endpoint below — assume it on every mutating endpoint except where explicitly marked CSRF-exempt (webhooks only).

### 0.3 Error format (API-005)
Every error response, from every endpoint, uses the single structured shape defined in Architecture §12/`core/errors.py`:

```json
{
  "error": {
    "code": "RESEARCH_PUBLISH_MISSING_FIELDS",
    "message": "This research item cannot be published yet.",
    "fields": { "bear_case": "required before publish", "sources": "at least one source required" }
  }
}
```

`code` is a stable, machine-readable string (used by the frontend for conditional UI, not just display). `message` is human-readable (STATE-003 — never a raw exception). `fields` is present only for validation-style errors and omitted otherwise. This document lists the primary `code` values per endpoint where a specific failure mode is a named PRD/Architecture requirement (e.g., publish-validation, webhook idempotency); generic 401/403/404/500 cases reuse standard codes (`UNAUTHENTICATED`, `FORBIDDEN`, `NOT_FOUND`, `INTERNAL_ERROR`) not re-listed per endpoint.

### 0.4 Pagination
List endpoints use cursor-free offset pagination for MVP simplicity (Principle 8 — no premature infra): query params `?page=1&page_size=20` (default `page_size=20`, max `100`), response envelope:

```json
{ "items": [ ... ], "page": 1, "page_size": 20, "total": 137 }
```

Not specified per-endpoint below except where a list endpoint exists; assume this envelope for every `GET` returning a collection.

### 0.5 Standard response codes (not repeated per-endpoint unless a specific meaning is added)
`200` success (read/update), `201` created, `204` no content (delete/void action), `400` validation error, `401` unauthenticated, `403` forbidden (RBAC or CSRF), `404` not found (or not visible to caller — MVP does not distinguish 404-vs-403-for-privacy beyond what's noted per-endpoint), `409` conflict (e.g., duplicate), `422` unprocessable (business-rule validation, e.g., empty change note), `429` rate-limited.

### 0.6 RBAC notation
Each endpoint states the minimum role/capability required, using the exact role names from PRD §30: `FREE_MEMBER`, `MEMBER` (Core), `REVIEWER`, `MODERATOR`, `ADMIN`, `SUPER_ADMIN`. Since roles are additive (OD-05/RBAC-003), "requires MEMBER" means "any role set that includes MEMBER, or any higher/overlapping role that Architecture §8's capability table also grants this to" — the capability table, not a role hierarchy, is authoritative; this document names the *capability*, not just a role, wherever the PRD §30 matrix draws a distinction (e.g., moderation actions require the `moderation.take_action` capability, held by MODERATOR/ADMIN/SUPER_ADMIN, not by REVIEWER).

---

## 1. `auth` module — AUTH-001–009

| # | Method & Path | Auth | Request | Response | Notes / Requirement IDs |
|---|---|---|---|---|---|
| 1.1 | `POST /auth/register` | Public | `{ email, password, name, username }` | `201 { user_id }` | Creates `users` (unverified) + `profiles` (`role_grants=['FREE_MEMBER']`) in one transaction; triggers `EmailService` verification email; emits `events` row `signup` (Architecture §21.2). AUTH-001. Error `EMAIL_ALREADY_REGISTERED` (409), `USERNAME_TAKEN` (409), `PASSWORD_TOO_SHORT` (400, min 12 chars, OD-03). |
| 1.2 | `POST /auth/verify-email` | Public | `{ token }` | `200 { verified: true }` | Sets `users.email_verified_at`; emits `email_verified` event. Error `TOKEN_INVALID_OR_EXPIRED` (400). AUTH-002. |
| 1.3 | `POST /auth/login` | Public | `{ email, password }` | `200 { user: {...} }` + sets `qf_session` + `csrf_token` cookies | Creates Redis session (AD-03); updates `users.last_login_at`; emits `login` event. Rate-limited (AUTH-007, Redis sliding window). Error `INVALID_CREDENTIALS` (401, deliberately not distinguishing wrong-email vs wrong-password), `ACCOUNT_SUSPENDED` (403), `TOO_MANY_ATTEMPTS` (429). |
| 1.4 | `POST /auth/logout` | Authenticated | — | `204` | Invalidates the Redis session; clears both cookies. AUTH-004. |
| 1.5 | `POST /auth/password-reset/request` | Public | `{ email }` | `200 { sent: true }` (always 200, never reveals whether the email exists) | Emails a time-limited reset link via `EmailService`. AUTH-005. |
| 1.6 | `POST /auth/password-reset/confirm` | Public | `{ token, new_password }` | `200 { reset: true }` | Invalidates the token after use; invalidates all existing sessions for that user (forces re-login everywhere — a deliberate security default, consistent with AD-03's revocation-friendly design). Error `TOKEN_INVALID_OR_EXPIRED` (400), `PASSWORD_TOO_SHORT` (400). AUTH-005/006. |
| 1.7 | `GET /auth/session` | Authenticated | — | `200 { user_id, email, roles, effective_tier }` | Lightweight "who am I" check the frontend uses on app-shell load; also the mechanism the frontend route guard (Architecture §4.3) uses before rendering an authenticated route. Not a PRD-numbered requirement on its own — a direct, minimal implementation of AUTH-008's session-cookie model, not a new feature. |

**Password breach check (AUTH-009, SHOULD):** implemented as a non-blocking warning surfaced in the `1.1`/`1.6` response body (`{"warnings": {"password": "This password has appeared in known data breaches"}}`) when the optional k-anonymity check (Architecture §7) is enabled — never blocks registration/reset, consistent with AUTH-009 being SHOULD, not MUST, and "warns, does not block" per Architecture's own wording.

---

## 2. `users` module — PROF-001–006, AD-10 (member directory)

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 2.1 | `GET /users/me` | Authenticated | — | `200 { name, username, bio, experience_level, interests, joined_at, effective_tier, role_grants, research_contribution_count, badges }` | PROF-001. `research_contribution_count` computed as `COUNT(research WHERE author_id = me AND status='published')` (THESIS-002 — counted once regardless of version count). |
| 2.2 | `PATCH /users/me` | Authenticated | `{ name?, username?, bio?, experience_level?, interests? }` | `200 { ...updated profile }` | PROF-002. No `avatar_url` field exists anywhere in this contract — PROF-006/OD-21. Error `USERNAME_TAKEN` (409). |
| 2.3 | `GET /users/{username}` | Authenticated + Verified | — | `200 { name, username, bio, badges, public_research_count, joined_at }` | Public-profile view (PROF-005) — no email, no private fields. `404` if the user is anonymized/deleted (no leak of anonymized-user existence beyond generic not-found). |
| 2.4 | `GET /users/directory` | Authenticated + Verified, **requires MEMBER (Core)** | `?page=&page_size=` | `200 { items: [{ username, name, badge, joined_at }], page, page_size, total }` | AD-10 — Core-gated per MEM-003; no new table, derived read from `users`/`profiles`/`subscriptions`. Excludes suspended/anonymized members. `badge` is the current-role-derived label (AD-12 pattern reused here: directory badge, like the REVIEWER comment badge, always reflects *current* `role_grants`, never a frozen historical value). |

---

## 3. `membership` + `billing` modules — MEM-001–007, PAY-001–006, OD-06/07/10/16/22

### 3.1 Plans and current membership

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 3.1.1 | `GET /membership/plans` | Public | — | `200 [{ code: "FREE", price_paise: 0 }, { code: "CORE", price_paise: 79900, currency: "INR", billing_interval: "monthly" }]` | MEM-001/002. Exactly 2 rows, always — enforced by `plans.code` CHECK constraint at the DB layer (Database Schema §3), this endpoint just reads it. |
| 3.1.2 | `GET /membership/me` | Authenticated | — | `200 { plan_code, status, current_period_end, grace_period_ends_at, canceled_at }` | Reads the user's current `subscriptions` row (or synthesizes `{plan_code: "FREE", status: "active"}` if none exists — a user with no subscription row is implicitly FREE, not an error state). MEM-005. |

### 3.2 Checkout and webhook

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 3.2.1 | `POST /membership/checkout` | Authenticated + Verified | `{}` | `200 { razorpay_order_id, razorpay_key_id, amount_paise }` | PAY-001. Calls `PaymentService.create_subscription()` (Architecture §4.4) — this route never imports the Razorpay SDK directly. **Resolves Architecture §17 Remaining Technical Question #5:** a `subscriptions` row is created here, in `status='past_due'`-equivalent pending state — concretely, a new enum value is **not** added to the existing `subscriptions.status` CHECK (which per Database Schema §4 is fixed to `active/past_due/canceled/expired`); instead, the pending pre-payment state is held in Redis (short-TTL, keyed by `razorpay_order_id`) until the webhook (3.2.2) confirms payment, at which point the real `subscriptions` row is created for the first time, already `status='active'`. This keeps the DB's `subscriptions` table meaning exactly "confirmed billing history," never "attempted-but-unconfirmed" — a stricter, simpler invariant than adding a `pending` status would have been, and requires no Database Schema V1 amendment. **Per BOUND-003, this endpoint must not be enabled in production until OD-01 legal review is resolved** — implemented as a feature flag (`CORE_BILLING_ENABLED`, Architecture §13 secrets/config pattern) checked at the top of this handler, returning `503 BILLING_NOT_YET_AVAILABLE` while flagged off. |
| 3.2.2 | `POST /webhooks/razorpay` | **CSRF-exempt**, signature-verified only | Razorpay webhook payload | `200 {}` (Razorpay's expected ack) | PAY-002/003/004, ERR-003. Verifies via `PaymentService.verify_webhook_signature()` before touching the DB — an invalid signature returns `400` and writes nothing. On a valid `payment.captured` event: single transaction creates/updates `subscriptions` (`status='active'`, `current_period_start/end`), inserts `payments` (UNIQUE `gateway_reference_id` — a replayed webhook for the same transaction is a no-op due to the unique constraint, satisfying ERR-003 idempotency exactly as Database Schema §5 specifies), inserts `invoices` via `InvoiceService`/`TaxService` (PAY-005/OD-16), emits `payment_completed` event (Architecture §21.2/21.13). On `payment.failed`: inserts a `payments` row with `status='failed'`, no subscription/invoice change (PAY-003 — failure never silently grants access). |

### 3.3 Cancellation and grace-period downgrade

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 3.3.1 | `POST /membership/cancel` | Authenticated, own subscription only | `{}` | `200 { canceled: true, access_until: "..." }` | MEM-007. Sets `subscriptions.status='canceled'`, `canceled_at=now()`; leaves `current_period_end` untouched — access computed at read time (Architecture §9), no immediate revocation job. |
| — | *(no endpoint — internal scheduled job)* `jobs.grace_period_downgrade` | System (Architecture §9, AD-07 Redis-backed worker, daily) | — | — | MEM-006/OD-06. Finds `subscriptions WHERE status='past_due' AND grace_period_ends_at < now()`, sets `status='expired'`, downgrades effective tier to FREE; content is never deleted (no cascading delete path exists in this module). Not an HTTP endpoint — listed here for completeness since it implements a MUST-HAVE requirement with no other API surface. |

### 3.4 Invoices

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 3.4.1 | `GET /membership/invoices` | Authenticated, own invoices only | `?page=&page_size=` | `200 { items: [{ invoice_date, amount_paise, tax_paise, billing_period, payment_status }], ... }` | Reads `invoices WHERE user_id = me`. No PDF generation in MVP — the PRD doesn't require an invoice document, only the billing-architecture data (PAY-005); a downloadable invoice PDF is a reasonable Phase 2 addition, not built here. |

---

## 4. `community` module — COMM-001–008, PCR-001–003, COMM-006/AD-09

### 4.1 Posts and channels

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 4.1.1 | `GET /community/channels/{channel}/posts` | Authenticated + Verified, **requires MEMBER** for non-Announcements; **Authenticated only** (any tier) may `GET` `announcements` (read-only public-ish channel — PRD COMM-001 doesn't gate *reading* Announcements to Core, only posting rights differ) | `?page=&page_size=` | `200 { items: [{ id, author, content, created_at, is_edited, reaction_count, comment_count }], ... }` | Only `status='visible'` posts returned (Section 10.1). `channel` path param validated against the 7-value CHECK set (Database Schema §12). |
| 4.1.2 | `POST /community/channels/{channel}/posts` | **requires MEMBER**; **Announcements channel additionally requires MODERATOR or ADMIN** (COMM-001: "Announcements restricted to ADMIN/MODERATOR post rights") | `{ content }` | `201 { id, ... }` | COMM-003. Runs flagged-phrase matching against `moderation_rules` (MOD-003) — a match creates an auto-generated `reports`-queue-equivalent entry (Architecture §10) but never blocks the post. Emits `post_created` event. **First-post gate (CMPL-004):** if the caller has no `compliance_acknowledgments` row with `acknowledgment_type='member_charter'` for the current document version (Database Schema §8A, Architecture AD-16), the request is rejected `403 CHARTER_NOT_ACKNOWLEDGED` with a pointer to `4.5.1` below. |
| 4.1.3 | `PATCH /community/posts/{id}` | Author only | `{ content }` | `200 { ...updated }` | COMM-008. Sets `is_edited=true`. |
| 4.1.4 | `DELETE /community/posts/{id}` | Author only (self soft-delete) | — | `204` | PCR-002 — sets `status='removed'`, never a hard delete; writes a `moderation_actions` row with `moderator_id = author_id` to distinguish self-delete from moderator-initiated removal per Architecture §10.1's explicit note, and an `audit_logs` entry. |
| 4.1.5 | `GET /research/{research_id}/discussion` | Authenticated + Verified, tier rules per LIB-003 | `?page=&page_size=` | `200 { items: [...] }` (same post shape as 4.1.1) | LIB-005/OD-14 — reads `posts WHERE research_id = :id`, not a separate discussion table. |
| 4.1.6 | `POST /research/{research_id}/discussion` | **requires MEMBER** | `{ content }` | `201 { id, ... }` | LIB-005/OD-14 — creates a `posts` row with `research_id` set, `channel=NULL` (satisfies the `ck_posts_channel_or_research` constraint, Database Schema §12). Emits `post_created` AND, since a top-level research-discussion post from someone other than the author functions as commentary, also emits `research_commented` **only when created via the comment endpoint (§4.2.2) below**, not this top-level-post endpoint — see 21.2's precise rule: `research_commented` fires on `comments` creation targeting a research-linked post, not on the post itself. This distinction is preserved exactly as Architecture §21.2 specifies. |

### 4.2 Comments

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 4.2.1 | `GET /community/posts/{post_id}/comments` | Same visibility as the parent post | `?page=&page_size=` | `200 { items: [{ id, author, content, created_at, is_edited }], ... }` | COMM-004. |
| 4.2.2 | `POST /community/posts/{post_id}/comments` | **requires MEMBER** | `{ content }` | `201 { id, ... }` | COMM-004. Flagged-phrase matching applies here too (MOD-003). Emits `research_commented` **if and only if** the parent post's `research_id IS NOT NULL` (Architecture §21.2's exact rule) — otherwise no analytics event is emitted for this comment beyond none (general comments are not separately tracked, per ANLY-001's list not including a generic "comment_created" event). |
| 4.2.3 | `PATCH /community/comments/{id}` | Author only | `{ content }` | `200 { ... }` | COMM-008. |
| 4.2.4 | `DELETE /community/comments/{id}` | Author only | — | `204` | PCR-002 soft-delete, same pattern as 4.1.4. |

### 4.3 Reactions

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 4.3.1 | `POST /community/{target_type}/{target_id}/reactions` | **requires MEMBER** | `{ reaction_type: "like" }` | `201 { id }` | COMM-005. `target_type` restricted to `post`/`comment` (Database Schema §14 CHECK). Duplicate reaction attempt returns `409 ALREADY_REACTED` (backed by the `ux_reactions_unique` constraint — the DB is the actual enforcement, this is just the resulting API behavior). Service layer validates `target_id` exists and matches `target_type` before insert, per Architecture AD-13's required application-level check. **No event emitted** — reactions are deliberately untracked in `events` (Architecture §21.2). |
| 4.3.2 | `DELETE /community/{target_type}/{target_id}/reactions` | Own reaction only | — | `204` | Un-like. |

### 4.4 Bookmarks (COMM-006/AD-09)

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 4.4.1 | `POST /community/bookmarks` | **requires MEMBER** | `{ post_id }` | `201 { id }` | Backed by `ux_bookmarks_user_post` unique constraint; duplicate returns `409`. Posts only, per AD-9's explicit MVP scope (no comment/research bookmarking). |
| 4.4.2 | `DELETE /community/bookmarks/{post_id}` | Own bookmark only | — | `204` | |
| 4.4.3 | `GET /community/bookmarks` | **requires MEMBER**, own only | `?page=&page_size=` | `200 { items: [{ post_id, post_summary, bookmarked_at }], ... }` | Ordered by `created_at DESC` per the `ix_bookmarks_user_created` index. |

### 4.5 Onboarding / compliance acknowledgment (CMPL-004/005)

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 4.5.1 | `POST /users/me/acknowledge-charter` | Authenticated | `{}` | `200 { acknowledged_at }` | CMPL-004 — Member Charter acknowledgment gate before first post (referenced by 4.1.2). Inserts a `compliance_acknowledgments` row (`acknowledgment_type='member_charter'`, `document_version` read from current server config) — Database Schema §8A, Architecture AD-16. |
| 4.5.2 | `POST /users/me/acknowledge-risk-disclosure` | Authenticated | `{ context: "signup" \| "first_payment" }` | `200 { acknowledged_at }` | CMPL-005 — called once at registration completion and once again at `3.2.1` checkout initiation; both are required (PRD: "at signup and at the point of first payment"). Inserts a `compliance_acknowledgments` row per call (`acknowledgment_type='risk_disclosure'`) — multiple rows per user are expected and correct (one per required occasion), per Database Schema §8A. |

---

## 5. `moderation` module — MOD-001–005, CMPL-002/003, moderation_rules/moderation_actions

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 5.1 | `POST /moderation/reports` | **requires MEMBER** | `{ target_type: "post"\|"comment"\|"research", target_id, reason }` | `201 { id }` | MOD-001, COMM-007. Creates a `reports` row, `status='open'`. |
| 5.2 | `GET /moderation/queue` | **requires MODERATOR/ADMIN/SUPER_ADMIN** (`moderation.view_queue` capability) | `?status=open&page=&page_size=` | `200 { items: [{ id, reporter, target_type, target_id, reason, created_at }], ... }` | MOD-001. Default filter `status='open'`. |
| 5.3 | `POST /moderation/queue/{report_id}/action` | **requires MODERATOR/ADMIN/SUPER_ADMIN** (`moderation.take_action` capability — explicitly not held by REVIEWER, per PRD §30 matrix) | `{ action: "approve"\|"edit"\|"restrict"\|"remove"\|"reinstate", reason?, edit_content? }` | `200 { moderation_action_id, new_state }` | MOD-002. Implements the exact transactional flow from Architecture §10.1: single DB transaction updates target `status`/`moderation_status`, inserts `moderation_actions` row (`report_id` set), updates `reports.resolution_action/resolved_by/resolved_at/status='resolved'`, writes `audit_logs` entry — all four or none. Error `INVALID_ACTION_FOR_TARGET_TYPE` (400) if e.g. `action='suspend_member'` is sent with `target_type='post'`. |
| 5.4 | `POST /moderation/members/{user_id}/suspend` | **requires MODERATOR/ADMIN/SUPER_ADMIN** | `{ reason }` | `200 { ... }` | MOD-004/ADMIN-004. Sets `users.status='suspended'`; writes `moderation_actions` (`target_type='member'`, `action='suspend_member'`) + `audit_logs`. Suspended members retain read access per their tier (MOD-004) — this endpoint does not touch `subscriptions`. |
| 5.5 | `POST /moderation/members/{user_id}/reinstate` | **requires MODERATOR/ADMIN/SUPER_ADMIN** | `{}` | `200 { ... }` | Reverse of 5.4 — `action='reinstate_member'`. |
| 5.6 | `GET /moderation/actions?target_type=&target_id=` | **requires MODERATOR/ADMIN/SUPER_ADMIN** | — | `200 { items: [...] }` | Moderation history for a given content/member (`ix_moderation_actions_target` index). Read-only view over the append-only `moderation_actions` table — no write path other than 5.3–5.5. |
| 5.7 | `GET /moderation/rules` | **requires ADMIN/SUPER_ADMIN** | — | `200 [{ id, phrase, severity, enabled }]` | OD-08. |
| 5.8 | `POST /moderation/rules` | **requires ADMIN/SUPER_ADMIN** | `{ phrase, severity }` | `201 { id }` | `action` is never accepted as a request field — always server-set to `'flag_for_review'`, matching the DB's own hard CHECK constraint (Database Schema §18/AD-05) so there is no code path, not even a malformed request, that could set anything else. |
| 5.9 | `PATCH /moderation/rules/{id}` | **requires ADMIN/SUPER_ADMIN** | `{ enabled?, severity? }` | `200 { ... }` | Enable/disable without a code deploy — the entire point of OD-08. `phrase`/`action` are immutable after creation in this MVP contract (not a PRD requirement either way; kept minimal per Principle 8 — editing a rule's *text* is equivalent to disable-old/create-new, avoiding ambiguity about whether historical flags should be reinterpreted). |
| 5.10 | `DELETE /moderation/rules/{id}` | **requires ADMIN/SUPER_ADMIN** | — | `204` | Hard delete acceptable here — `moderation_rules` is configuration, not user content or audit trail, so it's outside the soft-delete/append-only discipline that governs `posts`/`research`/`audit_logs`/`moderation_actions`/`events`. |

---

## 6. `companies` module — CO-001–004, OD-23, ERR-001

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 6.1 | `GET /companies` | Authenticated + Verified | `?q=&page=&page_size=` | `200 { items: [{ id, name, exchange, sector, industry }], ... }` | `q` uses the `pg_trgm`/`GIN` name index (Architecture §5.3). |
| 6.2 | `GET /companies/{id}` | Authenticated + Verified | — | `200 { id, name, exchange, sector, industry, website, description, research_count, discussion_count, watchlisted_by_me }` | CO-003. `research_count`/`discussion_count` computed from `research`/`posts` at read time (no denormalized counter columns exist in Database Schema V1 — direct `COUNT()` queries are acceptable at MVP scale per Architecture §16.1's performance framing). |
| 6.3 | `POST /companies` | **requires MEMBER** (also invocable inline from `7.1` research creation) | `{ name, exchange, sector?, industry?, website?, description? }` | `201 { id }` | CO-002/OD-23. `exchange` restricted to `NSE`/`BSE`/`OTHER_RECOGNIZED` (Database Schema CHECK) — any other value returns `400 UNLISTED_COMPANY_NOT_SUPPORTED` with PRD-CO-002's exact explanatory message. Near-duplicate name (via `pg_trgm` similarity threshold) returns `409 POSSIBLE_DUPLICATE_COMPANY { suggested: [{id, name}] }` rather than silently creating a duplicate (ERR-001) — the caller may re-submit with `{ confirm_duplicate: true }` to proceed anyway (a genuinely distinct company can share a similar name). |
| 6.4 | `POST /companies/{id}/merge` | **requires ADMIN/SUPER_ADMIN** | `{ merge_into_id }` | `200 { ... }` | CO-004/ERR-004. Sets `is_merged_into` on the losing record (archived, not deleted); re-points `research.company_id` and `watchlist_items.company_id` to the surviving record in one transaction, so no existing research/watchlist link breaks (ERR-004). Writes `audit_logs` (AUDIT-002 explicitly lists company merges as an auditable action). |

---

## 7. `research` module — RES-001–006, QRES-001–003, VER-001–004, SRC-001–004, AD-06

### 7.1 Create / edit / draft

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 7.1.1 | `POST /research` | **requires MEMBER** | `{ company_id, research_type, industry?, title?, summary? }` | `201 { id, status: "draft", title, summary }` | RES-001. `current_version=0`. `title`/`summary` are `NOT NULL` at the DB layer (Database Schema §8, Architecture AD-16); if omitted here, the service layer fills a placeholder (`"Untitled research"` / an empty-but-non-null placeholder) so draft creation is never blocked — the author is expected to replace these before publish. Emits `research_draft_created` event. |
| 7.1.2 | `GET /research/{id}` | Author, or any Authenticated+Verified user if `status='published' AND moderation_status='active'` (subject to LIB-003/MEM-004 tier gating below), or MODERATOR+/ADMIN+ regardless of moderation_status | — | `200 { ...all Q-RESEARCH fields, sources: [...], tags: [...], current_version, access_tier, disclosure: {...} }` | Serializer applies the following tier-gating rule, in order, once the item is otherwise eligible for viewing (`status='published' AND moderation_status='active'` — `access_tier` never overrides or bypasses this eligibility check): **(1)** if `research.access_tier = 'free_example'` (Database Schema §8, Architecture AD-18), the caller receives the **full permitted research representation regardless of their membership tier** — this is the concrete implementation of MEM-004's "selected research examples (curated, not the full library)"; **(2)** otherwise (`access_tier = 'core'`, the default), the existing LIB-003 rule applies: a CORE/MEMBER caller receives the full representation, and a FREE caller receives `{ preview: true, title, author, summary, access_tier: 'core' }` instead of full fields. This is not a single unconditional FREE-preview rule for all published research — `access_tier` is checked first, and only `'core'` items fall through to the paywalled-preview behavior. |
| 7.1.3 | `PATCH /research/{id}` | Author only, only while `status='draft'` for pre-publish edits | `{ title?, summary?, business_quality?, financial_snapshot?, business_model?, competitive_position?, valuation_range?, bull_case?, base_case?, bear_case?, risk_register?, catalysts?, invalidation_conditions?, research_date?, conflict_disclosed?, conflict_detail?, position_disclosed?, position_detail? }` | `200 { ...updated }` | RES-002/003, QRES-001/002 — each field independently saveable (partial `PATCH` body accepted; the frontend's debounced per-section autosave described in Architecture §10 calls this repeatedly with just the changed section). Emits `research_draft_updated`, and additionally `research_section_completed` **per field** that transitions from NULL/empty to non-empty in this call (Architecture §21.1's precise trigger condition) — a single `PATCH` touching 3 fields for the first time can emit up to 3 `research_section_completed` events plus 1 `research_draft_updated` event. `conflict_disclosed`/`position_disclosed` accept explicit `true`/`false`, never inferred from omission (SRC-004) — omitting the key in the JSON body leaves the column `NULL` (unanswered), sending the key with value `false` explicitly records "No" as an answered state; the API layer treats these as meaningfully different, matching the DB column's own tri-state design (Database Schema §8). |
| 7.1.4 | `PATCH /research/{id}` (on an already-published item) | Author only | Same body shape as 7.1.3 | `200 { status: "published", current_version, ...updated }` on success; `422 { error: { code: "CHANGE_NOTE_REQUIRED" } }` if `change_note` missing; `422 { error: { code: "RESEARCH_PUBLISH_MISSING_FIELDS", fields: {...} } }` if the post-edit state fails publish validation | RES-006/VER-002, **Architecture AD-17 (Amendment 2026-08-29).** Editing a published item requires `change_note` in the same request. **This endpoint now runs the identical full publish-validation gate as `7.3.1`** (`bear_case` non-empty, ≥1 source, `conflict_disclosed`/`position_disclosed` both answered, `title`/`summary` non-placeholder) against the *proposed post-edit state*, before committing anything. On success: atomically (a) applies the field changes to the `research` row, (b) increments `current_version`, (c) inserts a `research_versions` snapshot row with the provided `change_note`. **On validation failure: nothing is written — the currently-published version, including all its fields, is left completely unchanged; no partial update, no version increment, no snapshot row.** This closes a prior gap where an author could blank a required field (e.g., `bear_case`) on a live published item without re-validation — see 7.3.1 for the shared validation-detail contract. |

### 7.2 Sources

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 7.2.1 | `POST /research/{id}/sources` | Author only | `{ label, reference, supports_claim? }` | `201 { id }` | SRC-001/002. Empty `label` rejected `400`. Emits `research_source_added`. |
| 7.2.2 | `DELETE /research/{id}/sources/{source_id}` | Author only, draft items only (sources on a published item's *current* version are edited via a full re-publish with a new source list, not deleted out from under a live version — keeps `research_versions.snapshot` internally consistent) | — | `204` | |
| 7.2.3 | `GET /research/{id}/sources` | Same visibility as `7.1.2` | — | `200 [{ id, label, reference, supports_claim }]` | |

### 7.3 Publishing and versioning

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 7.3.1 | `POST /research/{id}/publish` | Author only | `{ change_note? }` (`change_note` required only if `current_version > 0`, i.e., this is a re-publish, not the first publish — VER-002 requires a change note per version, but the very first version has nothing to describe a "change" *from*, so the first-publish call accepts an optional `change_note` and defaults it to `"Initial publication"` if omitted) | `200 { status: "published", current_version }` | RES-004/005/006, QRES-003, SRC-001/003. **This is the single endpoint that runs full publish-time validation** (Architecture AD-04 — service-layer only, never a DB constraint; `7.1.4` reuses this exact same check per AD-17): checks `title`/`summary` are non-placeholder (Architecture AD-16), `bear_case` non-empty (QRES-003), at least one `research_sources` row exists (SRC-001), `conflict_disclosed`/`position_disclosed` are both non-NULL (SRC-003), `research_date` is set. Any failure returns `422 RESEARCH_PUBLISH_MISSING_FIELDS` with a `fields` map naming every missing requirement at once (not just the first one found) — so the author sees the complete checklist in one round trip. On success: sets `status='published'`, `published_at` (first publish only), increments `current_version`, inserts the `research_versions` snapshot (JSONB of every field at this moment, per Database Schema §9), emits `research_published` event. |
| 7.3.2 | `GET /research/{id}/versions` | Same visibility as `7.1.2` | `?page=&page_size=` | `200 { items: [{ version_number, change_note, edited_by, created_at }], ... }` | VER-003. Ordered `version_number DESC`. |
| 7.3.3 | `GET /research/{id}/versions/{version_number}` | Same visibility as `7.1.2` | — | `200 { version_number, snapshot: {...full field set...}, change_note, edited_by, created_at, is_current: false }` | VER-004 — `is_current` computed by comparing to `research.current_version`; the current version is also reachable via `7.1.2` directly (which always shows the live row, not a version snapshot, though they're equal for the current version by construction). |

### 7.4 Library, browse, search, export

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 7.4.1 | `GET /research/library?company_id=&industry=&page=&page_size=` | Authenticated + Verified | — | `200 { items: [{ id, title, summary, author, company, industry, created_at, updated_at, status_label, tags, source_count, current_version, access_tier }], ... }` | LIB-001/002. Only `status='published' AND moderation_status='active'` items included. Per-item tier-gating applies the same `access_tier`-first rule as `7.1.2`: `free_example` items return full permitted fields to every caller regardless of tier (MEM-004); `core` items apply the LIB-003 paywalled-preview rule for FREE callers, full content for CORE/MEMBER callers. `title`/`summary` are the real stored `research` columns (Architecture AD-16) — no derived/synthetic field. |
| 7.4.2 | `GET /research/search?q=&page=&page_size=` | Authenticated + Verified | — | `200 { items: [...] }` (same shape as 7.4.1, including `access_tier`) | LIB-004/SEARCH-001/002/003. PostgreSQL `tsvector`/`GIN` query (Architecture §5.3/§11) against `research`'s FTS index (Architecture AD-16 amendment) and `research_tags`/`companies.name`. Tier-gating applied identically to library browsing — SEARCH-002 explicitly requires this, not a separate rule — including the same `access_tier`-first check as `7.1.2`/`7.4.1`: a `free_example` item is never hidden or previewed-only for a FREE caller in search results either, since search must not present a more restrictive view of an item than direct library browsing does. |
| 7.4.3 | `GET /research/export.csv` | **requires MEMBER**, self-only | — | `200` `text/csv` streamed download | AD-11 — Section 11 SHOULD-HAVE. Query scoped to `research.author_id = current_user.id`, joined with `research_tags`/`companies`, streamed synchronously (no background job, per AD-11's explicit MVP decision). Columns: title/company/status/created_at/updated_at/tags/current_version. |

### 7.5 Access classification (Founder Decision #2, AD-19)

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 7.5.1 | `PATCH /research/{id}/access-tier` | **requires ADMIN/SUPER_ADMIN only** — not the research item's author, not REVIEWER, not MODERATOR, regardless of any other relationship to the item (Architecture AD-19, Section 6A) | `{ access_tier: "core" \| "free_example" }` | `200 { id, access_tier }` | Updates **only** `research.access_tier` — does not read, validate, or modify `status`, `moderation_status`, `current_version`, or any other field; does not trigger publish validation (AD-04/AD-17 do not apply, since this is not a publish or content-edit action); does not create a `research_versions` snapshot (the classification is not part of the versioned content). Writes a single `audit_logs` row in the same transaction as the `research` update (`actor_id` = caller, `action_type = "research.access_tier_changed"`, `target_entity_type = "research"`, `target_entity_id` = the research id, `before_state = { access_tier: <old> }`, `after_state = { access_tier: <new> }`) — Database Schema §22, Architecture AD-19; no new table. AUTHOR/REVIEWER/MODERATOR callers receive the standard `403 FORBIDDEN` (Architecture §12/API-005 error contract, same as any other RBAC-denied endpoint in this document — no special-cased error behavior is introduced). An author attempting this on their own research receives the identical `403` — authorship confers no exception. `access_tier` values outside `core`/`free_example` are rejected `400 { error: { code: "INVALID_ACCESS_TIER" } }` before any DB write is attempted (defense-in-depth alongside the DB's own CHECK constraint, Database Schema §8, consistent with how `6.3`/`5.8` pre-validate CHECK-constrained fields elsewhere in this document rather than relying on the DB error alone). No effect on `7.1.2`/`7.4.1`/`7.4.2`'s tier-gating logic beyond the field value itself changing — those endpoints already read `access_tier` live (Amendment 2026-08-29), so a change here is visible on the caller's very next read, with no cache invalidation concern since none of those endpoints cache `access_tier`. |

---

## 8. `watchlist` module — WL-001–003

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 8.1 | `GET /watchlist` | **requires MEMBER**, own only | `?page=&page_size=` | `200 { items: [{ company_id, company_name, research_count, discussion_count, added_at }], ... }` | WL-002 — no market data, ever, anywhere in this response (BOUND-001/CO-001 alignment). |
| 8.2 | `POST /watchlist/items` | **requires MEMBER** | `{ company_id }` | `201 { id }` | WL-001. Lazily creates the caller's `watchlists` row on first use if one doesn't yet exist (a user has at most one `watchlists` row, per the `UNIQUE` constraint on `watchlists.user_id`, Database Schema §19). Duplicate add returns `409` (backed by `ux_watchlist_items_watchlist_company`). |
| 8.3 | `DELETE /watchlist/items/{company_id}` | Own watchlist only | — | `204` | WL-001. |

WL-003 (private by default) is not a separate endpoint — it's the *absence* of any endpoint exposing another user's watchlist; `2.3`'s public profile response deliberately excludes watchlist data, satisfying WL-003 by omission rather than by an explicit privacy flag.

---

## 9. `notifications` module — NOTIF-001–003

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 9.1 | `GET /notifications` | Authenticated, own only | `?unread_only=&page=&page_size=` | `200 { items: [{ id, type, payload, read_at, created_at }], unread_count, ... }` | NOTIF-002. |
| 9.2 | `POST /notifications/{id}/read` | Own only | `{}` | `200 { read_at }` | |
| 9.3 | `POST /notifications/read-all` | Authenticated | `{}` | `200 { marked: <count> }` | "mark read individually or in bulk" per NOTIF-002's acceptance criterion. |

Notification *creation* has no dedicated public endpoint — every notification is server-generated as a side effect of another module's action (a comment on your post, a reaction, a report resolution, a moderation action on your content, a subscription state change — the exact NOTIF-001 trigger list), written inside that action's own transaction, the same pattern already used for `audit_logs`/`events`. Email delivery (NOTIF-003, SHOULD) is a side effect dispatched via the `arq` job queue (AD-07) after the in-app notification row is committed — not part of the synchronous request path, so a slow/unavailable `EmailService` never delays the triggering action's response.

---

## 10. `admin` module — ADMIN-001–007

All endpoints below require, at minimum, **ADMIN or SUPER_ADMIN**, except where a narrower MODERATOR-partial-access note is given (matching PRD §30's "Partial (moderation only)" cell for MODERATOR's Admin Dashboard access).

| # | Method & Path | Auth | Request | Response | Notes |
|---|---|---|---|---|---|
| 10.1 | `GET /admin/metrics` | **ADMIN/SUPER_ADMIN** | `?window=30d` (default) | `200 { total_users, active_users, paid_members, mrr_paise, new_members, churn_pct, research_created, research_updated, research_discussions, posts, comments, reports }` | ADMIN-002/007. Computed via direct real-time queries (OD-19) per Architecture §21.11's exact per-metric source mapping: point-in-time counts from `users`/`subscriptions`; time-windowed counts from `events` (Architecture §21.10 pattern 2); MRR from `subscriptions`/`plans`. **No `research_reviewed` field exists in this response — deliberately, per OD-15/ADMIN-002.** |
| 10.2 | `GET /admin/users?status=&role=&page=&page_size=` | **ADMIN/SUPER_ADMIN** | — | `200 { items: [{ id, email, name, username, roles, status, joined_at }], ... }` | ADMIN-001. |
| 10.3 | `PATCH /admin/users/{id}/role` | **ADMIN/SUPER_ADMIN**; changing to/from `ADMIN` or `SUPER_ADMIN` itself requires **SUPER_ADMIN** (ADMIN-006 — "managing other ADMIN accounts" is SUPER_ADMIN-only) | `{ role_grants: [...] }` | `200 { role_grants }` | ADMIN-003. Full replacement of the `role_grants` array (additive-set model, OD-05) — request body is the complete new set, not an add/remove delta, to avoid ambiguity about ordering of concurrent role edits. Writes `audit_logs` (AUDIT-002 lists role changes explicitly). |
| 10.4 | `GET /admin/memberships?status=&page=&page_size=` | **ADMIN/SUPER_ADMIN** | — | `200 { items: [{ user, plan_code, status, current_period_end }], ... }` | ADMIN-001. |
| 10.5 | `GET /admin/payments?status=&page=&page_size=` | **ADMIN/SUPER_ADMIN** | — | `200 { items: [{ user, amount_paise, status, gateway_reference_id, created_at }], ... }` | ADMIN-001. |
| 10.6 | `GET /admin/companies?page=&page_size=` | **ADMIN/SUPER_ADMIN**; `MODERATOR` may `GET` (content-adjacent, not user/payment data) | — | `200 { items: [...] }` | ADMIN-001; write actions are `6.3`/`6.4` above, not duplicated here. |
| 10.7 | `GET /admin/audit-log?actor_id=&action_type=&target_entity_type=&date_from=&date_to=&page=&page_size=` | **ADMIN/SUPER_ADMIN full access; MODERATOR sees only entries where `actor_id = self`** (PRD §30: MODERATOR's Audit Log access is "Partial (own actions)") | — | `200 { items: [{ actor, action_type, target_entity_type, target_entity_id, reason, created_at }], ... }` | ADMIN-005. Read-only over the append-only `audit_logs` table — no write/edit/delete endpoint exists anywhere in this contract, satisfying AUDIT-003 by simply never building one. |
| 10.8 | `PATCH /admin/settings/pricing` | **SUPER_ADMIN only** | `{ plan_code: "CORE", price_paise }` | `200 { ... }` | ADMIN-006/MEM-002. Updates `plans.price_paise`; existing active `subscriptions` are explicitly untouched (MEM-002's acceptance criterion — only *new* subscriptions use the new price). Requires step-up re-authentication (SEC-007) — implemented as a required `{ password }` field in the same request body, re-verified server-side before the price change is applied. |
| 10.9 | `PATCH /admin/settings/billing-flags` | **SUPER_ADMIN only** | `{ core_billing_enabled: boolean }` | `200 { ... }` | The `CORE_BILLING_ENABLED` flag referenced in `3.2.1` — this is the operational control for BOUND-003's paid-launch gate (flip only after OD-01 legal sign-off; the API itself has no way to know legal review happened, so this remains a manual, deliberate founder/SUPER_ADMIN action, not something any automated process ever sets). Also requires step-up re-auth (SEC-007), same pattern as 10.8, given its direct bearing on the OD-01 compliance gate. |

Companies/research/community/moderation admin *content* actions (Section 28's "Posts, Comments, Research, Reports, Moderation, Content" dashboard sections) are deliberately **not** duplicated as separate `/admin/*` endpoints where a module-owned endpoint already exists with equivalent RBAC — e.g., an ADMIN removes a post via `5.3` (moderation action endpoint), not a second `/admin/posts/{id}/remove`. This avoids two different code paths for the same state transition, consistent with Architecture §10.1's single-transactional-flow design. The Admin Dashboard's "Posts"/"Comments"/"Research" *list/read* views reuse `4.1.1`/`4.2.1`/`7.4.1` with elevated RBAC allowing visibility into `restricted`/`removed` items that those endpoints normally exclude (an `?include_moderated=true` query flag, ADMIN/SUPER_ADMIN/MODERATOR only, added to each of those three read endpoints for this purpose — noted here rather than repeated three times above).

---

## 11. `search` module — SEARCH-001–003

No standalone `search` endpoints beyond `7.4.2` (`GET /research/search`) and `6.1`'s `?q=` company search — Architecture §4.2 notes the `search` module "owns no tables, queries `research`/`companies` via `tsvector`," so there is no separate `/search` top-level route; search is a query mode on the two content types that are actually searchable in MVP (LIB-004 scopes search explicitly to "title, company name, tags"), not a unified cross-entity search surface.

---

## 12. Open Questions Surfaced While Deriving This Spec

Per the same discipline as the prior two documents: this section names genuine implementation-sequencing questions this spec had to resolve or flag, distinguishing "resolved here, non-architectural" from "a real gap that needs founder input."

1. **Resolved here (§3.2.1):** the `subscriptions`-row-creation-sequencing question Architecture §17 explicitly deferred to this phase — resolved via a short-TTL Redis pending-checkout record rather than a new `subscriptions.status` enum value, so Database Schema V1 needs no amendment.
2. **RESOLVED (Amendment, 2026-08-29, post-founder-review):** CMPL-004 (Member Charter acknowledgment) and CMPL-005 (risk disclosure acknowledgment) storage location. Originally flagged here as a genuine gap — neither Architecture V1 nor Database Schema V1 defined where the acknowledgment timestamp is stored. **Founder decision: a dedicated `compliance_acknowledgments` table (Database Schema §8A, Architecture AD-16), not two columns on `profiles`**, since a bare timestamp can't record *which version* of the Charter/disclosure was acknowledged. `§4.1.2`/`§4.5.1`/`§4.5.2` above now reference this table directly.
3. **Admin content-moderation visibility flag (`?include_moderated=true`, end of §10):** a minor, additive query-parameter addition to three existing read endpoints, not a new endpoint or table — flagged for visibility rather than silently folded in, since it's the one place this spec adds a parameter not explicitly enumerated in Architecture V1's endpoint-agnostic description.
4. **CSV export streaming vs. buffering (§7.4.3):** Architecture AD-11 says "streams it as a file download" — this spec assumes a standard FastAPI `StreamingResponse` over `text/csv`; no decision needed beyond what AD-11 already made, noted only for implementation-phase clarity.
5. **RESOLVED (Amendment, 2026-08-29, post-founder-review):** `research.title`/`research.summary` had no defined source in Database Schema V1 despite `§7.1.2`/`§7.4.1`'s preview responses assuming they existed. **Founder decision: stored, author-provided, `NOT NULL` columns** (Database Schema §8, Architecture AD-16), not derived from company name + research type. `§7.1.1`/`§7.1.3`/`§7.4.1`/`§7.4.2` above now reference the real columns; the earlier `title_or_company_name` synthetic field is removed.
6. **RESOLVED (Amendment, 2026-08-29, post-founder-review):** `§7.1.4` (editing a published research item) previously required only a `change_note`, with no re-validation of publish-time requirements — a genuine compliance-relevant gap (a published item's `bear_case`/disclosure fields could be blanked without re-checking CMPL-001). **Founder decision: `§7.1.4` now runs the identical full publish-validation gate as `§7.3.1`** (Architecture AD-17); a failed validation leaves the currently-published version completely untouched, no partial write.
7. **Fixed, non-product:** §4.1.6's broken cross-reference ("comment endpoint (4.1.8)", which doesn't exist) corrected to the actual comment endpoint, `§4.2.2`.
8. **RESOLVED (Founder Decision #1, 2026-08-29):** Research access classification (curated FREE-accessible examples vs. ordinary Core-only research per MEM-004 vs. LIB-003). Originally flagged as a genuine gap during founder review — no field anywhere provided an authoritative way to distinguish the two. **Founder decision: `research.access_tier`** (`TEXT NOT NULL DEFAULT 'core' CHECK (access_tier IN ('core', 'free_example'))`, Database Schema §8, Architecture AD-18). `§7.1.2`, `§7.4.1`, and `§7.4.2` above now serialize and check this field as the first step of tier-gating, before falling through to the existing LIB-003 preview rule for `'core'` items.
9. **RESOLVED (Founder Decision #2, 2026-08-29):** Who is authorized to set/change `research.access_tier` — explicitly left open by Founder Decision #1/AD-18. **Founder decision: ADMIN/SUPER_ADMIN only** (Architecture AD-19, Section 6A) — not the author (even of their own research), not REVIEWER, not MODERATOR. Implemented as `§7.5.1 PATCH /research/{id}/access-tier`, above. Audited via the existing `audit_logs` table — Database Schema V1 was checked and confirmed to require no schema change (that document's Amendment Log row 3). No new role was created; SUPER_ADMIN inherits the capability under the existing additive RBAC model, consistent with every other ADMIN-level capability in this document (e.g., `6.4`, `10.3`, `10.8`).

None of the above reopens any of the 23 locked OD decisions, any BOUND-00x boundary, or any Architecture Decision (AD-01–AD-19). Items 2, 5, 6, 8, and 9 required founder decisions and have now received them (2026-08-29) — Architecture V1 and Database Schema V1 were amended (or, for item 9, explicitly checked and found not to need amendment) in lockstep before this document was updated, so all three artifacts are mutually consistent as of this revision.

---

## 13. Verification Against Architecture V1, Database Schema V1, and the Locked PRD

- **Every PRD MUST-HAVE functional area (§13–41)** has at least one corresponding endpoint above, cross-checked against the Architecture §19 Traceability Matrix module-by-module: `auth` (§1), `users` (§2), `membership`/`billing` (§3), `community` (§4), `moderation` (§5), `companies` (§6), `research` (§7), `watchlist` (§8), `notifications` (§9), `admin` (§10), `search` (§11 — via `7.4.2`/`6.1`).
- **No Phase 2/3 endpoint exists anywhere above** — no Guild endpoints, no Learning Hub endpoints, no avatar-upload endpoint, no member-facing AI endpoint, no DM endpoint, no real-time market-data endpoint, no mobile-specific endpoint. Checked directly against PRD §46–48.
- **Every external provider is called only through its Architecture §4.4 abstraction** — `3.2.1`/`3.2.2` reference `PaymentService` only; no endpoint description names the Razorpay SDK, Resend SDK, or S3 SDK directly.
- **RBAC is stated explicitly per endpoint**, never left to "assume the obvious role" — every row in every table above names its minimum role/capability, matching PRD §30's matrix, cross-checked against Architecture §8's capability-table design (REVIEWER explicitly excluded from `moderation.take_action` at `5.3`, matching PRD §30's ❌ for REVIEWER on that row).
- **CSRF/error-format/pagination conventions (§0)** apply uniformly rather than being redecided per-endpoint, consistent with Architecture §12/§13's centralized (`core/errors.py`, `require_csrf` dependency) design — this spec does not introduce a second error shape or a second pagination scheme anywhere.
- **Compliance boundary (BOUND-001–003) respected structurally:** `3.2.1`'s `CORE_BILLING_ENABLED` flag is the concrete API-layer implementation of BOUND-003's paid-launch gate; no endpoint anywhere generates a target price, buy/sell instruction, or personalized recommendation (CMPL-002) — `7.1.3`'s `valuation_range` field is free-text author input, never a system-computed number.
- **This document is design-only:** no FastAPI route file was created, no server was started, no request was actually made against anything.

---

*QFinance API Specification V1 — 🔒 LOCKED 2026-08-31. Amendment applied 2026-08-29 resolving §12 items 2/5/6 (`compliance_acknowledgments`, `research.title`/`summary`, and §7.1.4 published-edit revalidation). Second amendment applied 2026-08-29 (Founder Decision #1, §12 item 8) resolving `research.access_tier` serialization in §7.1.2/§7.4.1/§7.4.2. Third amendment applied 2026-08-29 (Founder Decision #2, §12 item 9) adding §7.5.1 `PATCH /research/{id}/access-tier` (ADMIN/SUPER_ADMIN only, audited via existing `audit_logs`, no new role). Final cross-document verification performed 2026-08-31 (§13 above): re-read against the actual current content of the PRD, Architecture V1 (including all three amendments), and Database Schema V1; no contradiction found; all three documents confirmed mutually consistent as of this revision. Founder authorized proceeding directly to UI/UX Specification and implementation without a further intermediate approval step (`work_memory.md` §28A/§30).*
