# QFinance Architecture V2

**Status:** 🟢 ACTIVE — supersedes QFINANCE_ARCHITECTURE_V1.md's module map for the new domains; V1's core principles (modular monolith, server-side RBAC, provider abstraction, additive-only migrations) are unchanged and carried forward, not rewritten.

## 1. System Shape (unchanged)
Still a modular monolith: one FastAPI service, one Next.js frontend, one PostgreSQL, one Redis. No new services introduced for this restructure.

## 2. Module Map (delta from V1)

| Module | Status | Notes |
|---|---|---|
| `auth`, `users`, `audit`, `analytics` | KEEP | Unchanged |
| `companies` | KEEP | Now also referenced by `journal` entries, not just `research` |
| `research` | ADAPT | Public-library concept retired (PRD V2 §4.3); adds `publish_to_community` bridge into `community` |
| `community` | ADAPT | Adds `post_type`, `Comment.parent_comment_id` (self-referential, nullable) |
| `moderation`, `membership`, `billing` | KEEP | Unchanged this phase; `billing` stays gated (`CORE_BILLING_ENABLED=False`) |
| `journal` | **NEW** | Private-only, no cross-module read access from `community` |
| `ratings` | **NEW** | Depends on `community` (validates target post is `post_type='thesis'`) |
| `contributions` | **NEW (Phase 5/P1)** | Depends on `community`, `ratings`; owns `contributions`, `credit_ledger` |
| `portfolio` | **NEW** | Owns `broker_connections`, holdings/positions cache; depends on `auth` |

## 3. Broker Abstraction (Portfolio)

```
app/integrations/brokers/
    base.py          # BrokerAdapter protocol: connect(), fetch_holdings(), fetch_positions()
    zerodha.py        # ZerodhaAdapter(BrokerAdapter) — Kite Connect only implementation
```

`portfolio/service.py` calls only the `BrokerAdapter` protocol, never `zerodha.py` directly by name for business logic — mirrors the existing `PaymentService`/`EmailService` abstraction pattern already established for Razorpay/Resend. Adding a second broker later means adding a second adapter file, not touching `portfolio/service.py`.

**Kite Connect integration boundary (read-only, MVP):**
- Login flow: redirect to Kite Connect's login URL with the app's `api_key`; Kite redirects back with a `request_token`; server exchanges `request_token` + `api_secret` for an `access_token` via Kite's session API — standard Kite Connect flow, not invented.
- `access_token` is short-lived per Kite's own semantics (expires daily) and is stored server-side only (`broker_connections.access_token`, never returned to the client).
- Holdings/positions are fetched live from Kite on request — no scheduled sync job in MVP (avoids "premature infrastructure," consistent with V1 Architecture Principle 8).
- **Credentials:** `ZERODHA_API_KEY`/`ZERODHA_API_SECRET` are configuration values (env vars), never hard-coded, never committed. If unset, the connect flow returns a clear `BROKER_NOT_CONFIGURED` error rather than failing unpredictably — mirrors the existing `RAZORPAY_KEY_ID`-unset dev-safe pattern already used in `billing`.

## 4. Community Threading

`comments.parent_comment_id -> comments.id` (nullable FK, `ON DELETE RESTRICT` per existing convention). A comment's visibility is still governed by its own `status` field (visible/restricted/removed) exactly as V1 designed — thread depth does not change the moderation model, only the display/nesting structure. Recursive authorization (a reply's visibility gate) is identical to a top-level comment's — inherits from the parent **post**, not the parent comment, consistent with V1's existing "same visibility as parent post" rule (now transitively true for any depth).

## 5. Research → Community Bridge

```
research.published (existing, unchanged)
        │
        ▼
POST /research/{id}/publish-to-community   (NEW)
        │
        ▼
community.posts row created:
    post_type = 'thesis'
    research_id = <the research item's id>   (existing nullable FK, reused)
    content = <author-supplied summary, NOT the full Q-RESEARCH body>
```

This reuses `posts.research_id` (already present in the V1 schema for research-discussion linking) rather than adding a new column — the same FK now serves two related purposes: linking discussion to a research item, and marking a post as a thesis publication of that item. `post_type='thesis'` is what actually distinguishes "this is a thesis post" from V1's original "any post can reference a research discussion" usage; both can coexist since a thesis post's own comment section *is* that research item's discussion.

## 6. Ratings

`ratings` module, `Rating` model, unique constraint on `(user_id, post_id)`, `CHECK (post_type check happens at the application layer, not a DB CHECK, since it requires a join to `posts.post_type`). One row per rater per thesis; update-in-place for re-rating, delete for removing. Average/count computed via `SELECT AVG(score), COUNT(*)` at read time — no materialized column in MVP (Architecture Principle 8, avoid premature optimization).

## 7. Contribution & Credits (Phase 5/P1)

```
contributions (append-only, like `events`)
    user_id, source_type ('thesis_published'|'engagement_received'|'rating_received'),
    source_entity_id, points, created_at
        │
        ▼ (deterministic sum per billing period)
credit_ledger
    user_id, amount_paise, reason, contribution_id (FK), created_at
        │
        ▼ (read-time calculation, not a stored discount)
membership.service.get_my_membership() extended to also return
    `available_credit_paise` and `effective_next_period_price_paise`
```

No credit is ever applied to `billing.payments`/Razorpay directly — this is a pure entitlement-calculation layer sitting in front of the existing, unchanged `membership`/`billing` modules. Self-engagement (liking/rating/commenting on one's own content) is filtered out at the point contributions are recorded, not after the fact.

## 8. Migration Discipline (unchanged from V1)
All of the above is additive-only: new tables (`journal_entries`, `broker_connections`, `ratings`, `contributions`, `credit_ledger`), new nullable columns (`posts.post_type` with a default, `comments.parent_comment_id`). No existing V1 table is dropped or renamed.
