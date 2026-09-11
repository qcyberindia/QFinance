# QFinance MVP PRD V2

**Status:** 🟢 ACTIVE — supersedes QFINANCE_MVP_PRD_V1.md for product direction.
**V1 status:** Historical record of the original research-community-only MVP. Not deleted, not edited. Where V2 conflicts with V1, V2 governs going forward; V1 remains the record of what was originally built and why.

---

## 1. What Changed

QFinance is no longer *only* a structured research + community workspace. It is now an **investor workspace + investment community**, where personal investment activity (portfolio, journal, research) feeds into a public community loop that rewards useful contribution with credits toward Premium.

**Core product loop:**
```
Portfolio → Journal → My Research (Thesis) → Community → Engagement →
Reach → Contribution Credits → Premium benefit
```

## 2. Information Architecture

1. **Portfolio** — read-only view of the member's Zerodha holdings/positions
2. **Investment Journal** — private notes: decisions, reasoning, observations
3. **My Research** — the member's own research workspace (was: public Research Library)
4. **Community** — public posts, threaded discussion, likes, thesis ratings
5. **Saved** — private bookmarks of Community content
6. **User Profile** — public identity + contribution/reputation
7. **Credits / Premium** — contribution ledger and Premium discount

## 3. Private vs. Public (first-class distinction, not an afterthought)

| PRIVATE (owner-only) | PUBLIC |
|---|---|
| Journal entries | Community posts (all types) |
| Research drafts | Published theses |
| Broker connection/credentials, raw portfolio holdings | Comments/replies |
| — | Thesis ratings (aggregate) |
| — | Public profile info, contribution/reputation |

A published thesis is a **deliberate, explicit act** (Publish to Community) — nothing private ever appears in a public surface implicitly.

## 4. Domain-by-Domain Scope (MVP only)

### 4.1 Portfolio
- Broker abstraction (`BrokerIntegration` interface) — **Zerodha only** implemented in MVP; interface must not hard-code Zerodha specifics into calling code.
- Connect/disconnect a Zerodha account (Kite Connect login flow).
- Fetch holdings, and positions where the Kite API supports it, on demand (no background polling in MVP).
- Store connection state + access token server-side, never exposed to the client, never logged.
- No trade execution, no order placement — **read-only**, matching V1's BOUND-001 spirit (still no personalized buy/sell instruction, still no execution).

### 4.2 Investment Journal
- CRUD on private entries: free-text content, optional entry type (decision/reasoning/observation/note), optional company association, timestamps.
- Never queryable or joinable by any Community-facing endpoint.
- No versioning requirement (unlike Research) — journaling is lightweight by design.

### 4.3 My Research
- Everything V1's Research module already does (Q-RESEARCH structure, sources, versioning, draft/publish, access control) is **reused as-is** for the private workspace.
- New: a `publish_to_community` action that creates a linked Community post (type=`thesis`) referencing the research item, rather than duplicating its content. The research item remains the source of truth; the Community post is a pointer + a snapshot summary for feed display.
- **Retired from V1:** the public Research Library (browse-all-published-research, independent of Community) is superseded — publishing now always means "publish to Community." `access_tier`/paywall-preview concepts from V1 are deferred; Premium gating in V2 is expressed through Credits/Premium (§7), not a separate research paywall. This is a genuine, deliberate scope retirement, not an oversight — flagged in Architecture V2 and work_memory.md.

### 4.4 Community
- Reuse posts/comments/reactions/bookmarks wholesale.
- **New:** `post_type` (`general`, `thesis`, `question`, `discussion`) replacing/extending V1's fixed-channel model — a post has a type, and may optionally still reference a channel for organization, but type is the primary MVP dimension the feed and ratings care about.
- **New:** threaded comments — `parent_comment_id` (nullable, self-referential) so replies-to-replies work, arbitrary depth in the data model (frontend may cap render depth).
- Moderation, visibility, ownership rules from V1 apply unchanged to all post types and to comments regardless of thread depth.

### 4.5 Thesis Rating
- 1–5 integer rating, one active rating per (user, thesis-post) pair, updatable, removable.
- Only valid on posts with `post_type='thesis'`.
- Author cannot rate their own thesis.
- Aggregate: average + count, computed on read (no MVP requirement for a materialized/cached aggregate).

### 4.6 Saved
- Reuses V1's `Bookmark` model/endpoints as-is — a post is a post regardless of `post_type`, so no new table is needed to "save a thesis" vs "save a general post."

### 4.7 User Profile
- Public profile aggregates: display name, username, bio, published Community posts, published theses, contribution/reputation summary (§4.8/Phase 5).
- Never surfaces: journal, research drafts, broker connection state, raw portfolio data.

### 4.8 Contribution & Credits (Phase 5 / P1 — not P0)
- A `contribution` record per rewarded event (thesis published, engagement received, rating received).
- A simple, documented, deterministic formula (no ML) converts contribution into a credit ledger entry.
- Credits reduce the *next* month's Premium price via a discount calculation — **not** a real-money billing change; `CORE_BILLING_ENABLED`/Razorpay production credentials remain untouched and gated exactly as in V1.
- Abuse guard: self-engagement (liking/rating/commenting on your own content) does not generate contribution.

## 5. Explicitly Out of Scope for V2 MVP
- Market Intelligence (unchanged from V1's exclusion)
- Any broker other than Zerodha
- ML-based ranking or recommendation
- Real-money Premium billing changes from credits
- Trade execution / order placement of any kind
- Portfolio analytics beyond what Kite's API returns directly

## 6. Compliance Posture (carried forward from V1, still binding)
BOUND-001 (no trades, no personalized buy/sell/hold instruction, no automated signals) applies with equal force to Portfolio and Community/Thesis Rating — a thesis rating is peer feedback on a member's published reasoning, not an instruction to any other member, and must not be presented as one.
