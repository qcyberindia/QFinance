# QFinance API Specification V2

**Status:** 🟢 ACTIVE — additive/adaptive delta on QFINANCE_API_SPECIFICATION_V1.md. All V1 `auth`/`companies`/`membership`/`billing`/`moderation` endpoints are unchanged and still governed by V1's spec text unless listed below. This document only specifies what's new or changed for the V2 restructure — kept intentionally implementation-terse per the "urgent delivery" instruction, not a full V1-style prose spec.

## 1. Journal (`/journal`) — all endpoints require Authenticated (own data only, no staff override, no public access)

| # | Endpoint | Auth | Notes |
|---|---|---|---|
| J.1 | `POST /journal` | Authenticated | `{content, entry_type, company_id?}` → 201 |
| J.2 | `GET /journal` | Authenticated | Own entries only, paginated, newest first |
| J.3 | `GET /journal/{id}` | Authenticated + owner | 404 if not owner (no 403 — don't reveal existence, matching V1's §7.1.2 precedent) |
| J.4 | `PATCH /journal/{id}` | Authenticated + owner | Partial update |
| J.5 | `DELETE /journal/{id}` | Authenticated + owner | Soft-delete |

## 2. My Research — delta on V1 §7
- V1's `GET /research/library` and `GET /research/search` (public browse) are **retired** — PRD V2 §4.3. Routes may remain mounted returning an empty/deprecated response during migration, or be removed; actual disposition decided at implementation time and recorded in work_memory.md, not silently dropped without a trace.
- **New:** `POST /research/{id}/publish-to-community` — Authenticated + owner + research must be `status='published'` → creates a `community.posts` row (`post_type='thesis'`, `research_id={id}`), body: `{summary}` (becomes the post's `content`). Returns the created post.
- All other V1 §7 endpoints (create/patch/sources/publish/versions/access-tier) are unchanged.

## 3. Community — delta on V1 §4
- `POST /community/channels/{channel}/posts` and the schema now accept `post_type` (default `general`) alongside existing fields.
- **New:** `POST /community/comments/{comment_id}/replies` — same auth/validation as `POST /community/posts/{post_id}/comments`, creates a comment with `parent_comment_id={comment_id}` (inherits `post_id` from the parent).
- `GET /community/posts/{post_id}/comments` response items now include `parent_comment_id` and (optionally, client-side-assembled) nested `replies`; the API itself may return a flat list with `parent_comment_id` and let the client build the tree (simpler server, matches "keep it simple" instruction) rather than a deeply-nested response payload.
- All moderation/visibility/RBAC rules from V1 §4/§5 apply unchanged, recursively, to replies.

## 4. Ratings (`/community/posts/{post_id}/rating`)

| # | Endpoint | Auth | Notes |
|---|---|---|---|
| R.1 | `POST /community/posts/{post_id}/rating` | requires MEMBER | `{score: 1-5}`. 400 `POST_NOT_RATEABLE` if `post_type != 'thesis'`. 403 `CANNOT_RATE_OWN_THESIS` if caller is the author. Upsert semantics (create or update in one call). |
| R.2 | `DELETE /community/posts/{post_id}/rating` | requires MEMBER + owner of the rating | Removes caller's own rating |
| R.3 | `GET /community/posts/{post_id}/rating-summary` | Authenticated | `{average, count}` |

## 5. Saved — unchanged
V1 §4.4 (`/community/bookmarks`) reused as-is (PRD V2 §4.6) — no new endpoints.

## 6. Profile (`/profile`)

| # | Endpoint | Auth | Notes |
|---|---|---|---|
| P.1 | `GET /profile/{username}` | Public (no auth required) | Returns display name, bio, published posts (paginated), published theses, contribution summary (0s until Phase 5 ships). Never includes journal/drafts/broker/portfolio data — enforced by the serializer never accepting those fields as input, not by a runtime filter that could be forgotten. |

## 7. Portfolio (`/portfolio`)

| # | Endpoint | Auth | Notes |
|---|---|---|---|
| PF.1 | `GET /portfolio/zerodha/connect` | Authenticated + Verified | Returns the Kite Connect login redirect URL. 503 `BROKER_NOT_CONFIGURED` if `ZERODHA_API_KEY` unset. |
| PF.2 | `GET /portfolio/zerodha/callback` | Authenticated + Verified | Handles Kite's redirect (`request_token` query param), exchanges for `access_token`, stores `broker_connections` row. |
| PF.3 | `DELETE /portfolio/zerodha` | Authenticated + owner | Disconnects — clears stored token, sets `status='disconnected'`. |
| PF.4 | `GET /portfolio` | Authenticated + owner | Live-fetches holdings (+ positions where available) from Kite via the connected token; 404 `BROKER_NOT_CONNECTED` if no active connection. |

## 8. Credits / Premium (Phase 5/P1)

| # | Endpoint | Auth | Notes |
|---|---|---|---|
| C.1 | `GET /credits/me` | Authenticated | `{balance_paise, entries: [{amount_paise, reason, created_at}], ...}` paginated history |
| C.2 | `GET /membership/me` (V1, extended) | Authenticated | Adds `available_credit_paise`, `effective_next_period_price_paise` fields — additive, doesn't break V1 consumers |

## 9. Error Codes Introduced
`POST_NOT_RATEABLE`, `CANNOT_RATE_OWN_THESIS`, `BROKER_NOT_CONFIGURED`, `BROKER_NOT_CONNECTED`, `BROKER_AUTH_FAILED` — all follow V1's existing `{error: {code, message}}` envelope, no new envelope shape.
