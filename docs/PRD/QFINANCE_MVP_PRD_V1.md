# QFinance — MVP Product Requirements Document (PRD) v1.0

**Status:** 🔒 LOCKED — all 23 Open Product Decisions resolved (see Section 51). Ready for Architecture phase.
**Owner:** Prakash Raj D (Founder)
**Document type:** Authoritative source of truth for QFinance MVP implementation
**Project root:** `/home/prd/Projects/QFinance`
**Source documents reconciled:**
1. "Private Investor Research Community — Upgraded Blueprint" (V2 business blueprint PDF)
2. "QFinance MVP — Product Definition" (SaaS technical/product breakdown)

This PRD supersedes both source documents wherever a conflict exists. Where a decision was made to resolve a conflict, it is called out explicitly in **Section 0 — Reconciliation Notes**. Anything not yet decidable is listed in **Section 51 — Open Product Decisions** and must NOT be silently assumed during implementation.

---

## 0. Reconciliation Notes (read first)

The two source documents agree on strategy (research-process-first, community-driven, compliance-aware, no stock tips) but disagree or are ambiguous on several product/technical points. This PRD locks the following resolutions:

| # | Conflict | Blueprint position | MVP tech spec position | **Resolution locked in this PRD** |
|---|---|---|---|---|
| R1 | Community platform | "Start simple: Discord/Circle/other suitable platform" for MVP | Build custom Community module (posts/comments/reactions) as the product itself | **Custom-built community module**, per explicit founder instruction to use Next.js + FastAPI + PostgreSQL as the MVP stack. Discord/Circle is rejected — QFinance is being built as a SaaS product, not a community-tool wrapper. |
| R2 | Pricing tiers at launch | Free / Core (₹499–999) / Pro (₹1,499–2,499) / Annual / Founding / Guild+ / Certification | Free / Core (₹799 illustrative) only; Guild+ explicitly deferred | **MVP ships Free + Core only.** Core price is a configurable value, default illustrative ₹799/month (inside blueprint's ₹499–999 band). Pro, Annual, Founding, Guild+, Certification are Phase 2/3. |
| R3 | Research Guilds | Central differentiator, guilds forming by Month 2 of launch roadmap | Explicitly "MVP Phase 2, not Day 1" | **Guilds are OUT of MVP**, confirmed by explicit founder instruction in this task. All guild-related schema/UI is Phase 2 backlog only. |
| R4 | Reputation/role progression | Contributor → Reviewer → Analyst → Fellow (non-monetary reputation tiers) | RBAC roles: SUPER_ADMIN, ADMIN, MODERATOR, REVIEWER, MEMBER, FREE_MEMBER (ANALYST/FELLOW later) | **MVP RBAC uses only the 6 locked roles.** REVIEWER is implemented as a real RBAC role (not just a badge), manually grantable by ADMIN in MVP (no automated reputation engine yet). ANALYST/FELLOW are Phase 2/3 progression roles layered on top of reputation, not RBAC roles, when introduced. |
| R5 | AI functionality | AI roadmap: MVP = founder-internal use only, human-reviewed | "Don't overbuild AI — don't make it the MVP's core value prop" | **No member-facing AI features in MVP.** Any AI usage is internal/manual (e.g., founder using AI tools outside the product to draft content). No AI endpoints in the MVP application itself. |
| R6 | Certification Track | Present in blueprint monetization & progression model | Not mentioned in tech spec MVP modules | **Out of MVP.** Phase 2/3 backlog. |
| R7 | Content moderation on flagged phrases | "These shouldn't automatically determine legality... trigger moderation/legal-review workflows" | Not detailed | **Locked: flagged-phrase detection is a moderation SIGNAL only, never a legal classifier. It routes content to human review; it never auto-blocks, auto-removes, or auto-labels content as unlawful.** |
| R8 | Market/financial data | Blueprint: avoid expensive real-time data infra initially, add later via licensed APIs | Tech spec: explicitly "Do not initially build expensive real-time market-data infrastructure" | **Aligned — no real-time market data in MVP.** Company pages carry static/manually-entered metadata only. |
| R9 | Compliance disclosures on research | Blueprint: source disclosure, conflict/position disclosure, safe-harbor checklist | Tech spec: same checklist items listed under "Compliance-by-Design" | **Aligned — merged into Research Workspace mandatory fields (Section 22/25).** |
| R10 | Search | Not detailed in blueprint beyond "later: research knowledge graph" | Tech spec: "PostgreSQL full-text search initially, don't deploy Elasticsearch until scale requires it" | **Locked: PostgreSQL full-text search (`tsvector`) for MVP.** |

Any requirement in this PRD that a reviewer disagrees with should be raised before implementation begins — this document is intended to remove ambiguity, not introduce new unstated assumptions.

---

## 1. Product Overview

QFinance is a private, subscription-based SaaS workspace where self-directed investors in India learn structured investment research, document their thinking, and improve through peer discussion — without receiving personalized stock tips, trading signals, or portfolio management.

The MVP is a **research workspace + private community + research library + membership system**, built as a modular monolith (Next.js frontend, FastAPI backend, PostgreSQL, Redis).

## 2. Product Vision

Build a high-trust, process-first environment where independent investors learn to research businesses, assess risk, and document repeatable investment theses — becoming the system of record for a member's own research judgment over time.

## 3. Problem Statement

Retail investors in India are exposed to large volumes of unstructured market "noise" (tip channels, finfluencer calls, unverified claims) but have few structured, accountable ways to build their own research discipline. Existing options are polarized: free, generic broker research with no community, or expensive/regulated advisory services with high minimums. There is a gap for a mid-priced, process-oriented, community-driven research workspace.

## 3A. MVP Product Boundary (Locked Product Requirement)

> **QFinance MVP is a research-learning and community SaaS. It does not execute trades, provide portfolio management, provide personalized investment advice, or operate a member-facing automated stock recommendation system. Paid securities-research functionality beyond the structured educational/community research workflow described in this PRD will not be launched until its regulatory classification and required compliance obligations have been reviewed by qualified Indian securities counsel (see OD-01).**

This statement is a **product requirement (BOUND-001)**, not a disclaimer bolted on afterward. It governs every module in this document:

| ID | Requirement | Priority |
|---|---|---|
| BOUND-001 | No MVP feature may execute trades, place orders, connect to a broker, manage a member's portfolio, or generate a personalized buy/sell/hold instruction for any individual member. | MUST |
| BOUND-002 | The product may launch and operate its non-paid/free tier, closed beta, and general research/community functionality prior to legal sign-off. **Accepting PAID members for Core** is gated on the workflow below. | MUST |
| BOUND-003 | The path to paid launch is: `Development → Internal testing → Closed non-paid beta → Legal/compliance review (OD-01) → Paid launch`. Paid billing (PAY-001) must not go live in production before OD-01 is resolved. | MUST |

## 4. Target Users / Personas

| Persona | Description | MVP relevance |
|---|---|---|
| **Intermediate self-directed investor** (primary) | Already invests, wants better research structure and valuation discipline | Core paying member |
| **Serious long-term investor** | Wants deep research + peer challenge | Core paying member, likely early REVIEWER candidate |
| **Beginner investor** | Building financial literacy | Free tier / entry funnel |
| **Finance student** | Wants practical company-analysis practice | Free or Core, price-sensitive |
| **Founder/Admin** (Prakash) | Builds content, moderates, runs the platform | SUPER_ADMIN / ADMIN role |
| **Active trader** (explicit non-target) | Wants short-term signals | Explicitly NOT served — product should not attract or retain this persona |

## 5. User Goals

- Learn a repeatable research methodology (Q-RESEARCH) rather than copy conclusions.
- Create, save, version, and publish company research and investment theses.
- Discuss research and market topics with a vetted, paying community.
- Track companies of interest via a personal watchlist.
- Build a visible research history/profile over time.
- (Admin) Moderate content, manage members and subscriptions, monitor platform health.

## 6. Product Principles

1. **Process over prediction** — the product structures *how* members research, never *what* to buy/sell.
2. **No personalized advice** — nothing in the MVP should read as a recommendation addressed to a specific member's portfolio.
3. **Evidence over excitement** — research submissions require sources; unsourced claims are discouraged by product design, not just policy.
4. **Risk before return** — every thesis structurally requires a counter-thesis/risk section; the form cannot be submitted without it.
5. **Transparency** — disclosure of position/conflict is a first-class, structured field, not a free-text afterthought.
6. **Archive, don't erase** — published research keeps version history; nothing quietly disappears once published (deletions/edits are auditable).
7. **Compliance by design, not compliance by disclaimer** — Terms & Conditions do not substitute for correct product behavior (see Section 32).
8. **Ship the smallest thing that tests the real hypothesis**: *will investors pay to participate in a structured research community?* Everything not needed to test that is deferred.

## 7. MVP Objectives

- O1: Launch a working private community + research workspace that a paying member can use end-to-end (register → pay → research → discuss → watchlist).
- O2: Prove members will create and engage with structured research, not just consume content passively.
- O3: Establish compliance-by-design patterns (disclosure fields, moderation workflow, audit log) from day one so the product does not need a compliance retrofit later.
- O4: Keep infrastructure lean (modular monolith, no premature microservices/real-time data/mobile apps).

## 8. MVP Success Criteria

(from blueprint Section 21, reconciled — used as-is, both sources agree)

- 50 registered users
- 20+ monthly active users
- 10+ paying users
- 70%+ of paying members perform at least one "meaningful research activity" per month, defined **[LOCKED — OD-09]** as: creating/updating a research record, completing a research section, adding a source, publishing research, or submitting a substantive review/comment on a research item. Likes and casual/non-research community comments do NOT count toward this metric.
- 60%+ of paying members renew after their first billing cycle
- Members voluntarily create or review research without prompting

The **critical conversion event is not payment** — it is a member completing their first meaningful research activity (creating or substantively engaging with a research item). Analytics must be able to measure this event distinctly from signup/payment events (see Section 38).

## 9. Functional Requirements

Functional requirements are grouped by module in Sections 13–30, each with unique IDs. Cross-cutting functional requirements:

| ID | Requirement | Priority |
|---|---|---|
| FUNC-001 | The system shall support three membership states affecting access: `FREE`, `CORE` (paid), and `SUSPENDED`. | MUST |
| FUNC-002 | All user-generated content (posts, comments, research, theses) shall be attributable to a single authenticated user account. | MUST |
| FUNC-003 | The system shall never auto-generate or auto-suggest a buy/sell/hold call, target price, or portfolio action for any user. | MUST |
| FUNC-004 | The system shall log an audit trail entry for all content moderation actions, role changes, and subscription state changes. | MUST |

## 10. Non-Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| NFR-001 | Backend implemented as a modular monolith in FastAPI (Python), not microservices. | MUST |
| NFR-002 | Frontend implemented in Next.js + TypeScript. | MUST |
| NFR-003 | Primary datastore is PostgreSQL. | MUST |
| NFR-004 | Redis used for caching and background job queueing. | MUST |
| NFR-005 | File/object storage abstracted behind an S3-compatible interface — **AWS S3, `ap-south-1` [LOCKED — OD-11]**. | MUST |
| NFR-006 | Search implemented using PostgreSQL full-text search (`tsvector`/`GIN` index); no external search engine in MVP. | MUST |
| NFR-007 | No mobile native applications in MVP; web must be responsive/usable on mobile browsers. | MUST |
| NFR-008 | System designed so Guild-related tables/features can be added in Phase 2 without breaking MVP schema (additive migrations only). | SHOULD |
| NFR-009 | All authenticated endpoints enforce RBAC checks server-side (never client-side only). | MUST |
| NFR-010 | Passwords stored using a modern salted hash (e.g., bcrypt/argon2); plaintext passwords never logged or stored. | MUST |

Detailed performance, security, accessibility and SEO requirements are in Sections 42–45.

## 11. Complete MVP Feature List

### MUST HAVE — MVP
- Registration, login, logout, password reset, email verification
- User profile (bio, experience level, interests)
- Free and Core membership tiers with payment-gated access control
- Community: posts, comments, reactions, reporting, moderation queue
- Research Library: browse/search company & industry research
- Company pages (static metadata, linked research/discussions, watchlist toggle)
- Research Workspace: create/edit/save-draft/publish research using Q-RESEARCH structure
- Thesis fields embedded in research (bull/base/bear, risks, counter-thesis, invalidation)
- Research versioning (edit history, "what changed")
- Source/citation capture on research
- Watchlist (add/remove companies, no market data)
- Notifications (in-app; email optional — see OD-12)
- Admin dashboard (users, memberships, payments, moderation, companies, audit log, core metrics)
- RBAC with the 6 locked roles
- Audit logging for moderation/role/subscription events
- Compliance-by-design fields on research submission (sources, date, assumptions, risks, counter-thesis, conflict/position disclosure)
- Payment integration for Core subscription — **Razorpay [LOCKED — OD-10]**

### SHOULD HAVE — MVP if low complexity
- Email notifications (digest or per-event) — depends on transactional email provider being wired
- Basic member directory (name, badge/role, join date — no DMs in MVP)
- CSV export of a member's own research (portability, low compliance risk)

### PHASE 2
- Research Guilds (pods, weekly cycles, peer review workflow, guild rooms)
- Reputation/progression tiers beyond RBAC roles (Analyst, Fellow) and automated reputation scoring
- Certification Track
- Member-facing AI ("what changed?" briefings, AI research assistant)
- Pro tier, Annual plans, Founding member offer, Guild+ add-on
- Direct messaging between members
- Partner/B2B integrations (brokers, fintech apps)
- Advanced analytics/member intelligence dashboard

### PHASE 3 / LATER
- Full AI research copilot embedded in workspace
- Research knowledge graph
- Licensed real-time market data integration
- Mobile applications
- Elasticsearch/OpenSearch-based search
- Regulated professional research/advisory offering (contingent on legal registration)

### OUT OF SCOPE (MVP and indefinitely unless business model changes)
- Trading / broker integration / order execution
- Portfolio management or execution on a member's behalf
- Personalized buy/sell recommendations of any kind
- Automated stock-call or signal engine
- Options strategy engine, crypto trading, social copy-trading
- Real-time stock terminal

## 12. Detailed User Journeys

### J1 — New free member (primary funnel)
Landing page → Register → Verify email → Onboarding (profile + rules acknowledgment) → Free dashboard → Browse public/free research → Prompted to upgrade → Payment → Core member → Post in community → Create first research draft.

### J2 — Core member creates and publishes research
Login → Research Workspace → "New Research" → Select company (existing or add new) → Fill Q-RESEARCH structured sections → Add sources → Complete compliance disclosure block (position/conflict) → Save as draft → Continue editing → Publish → Research appears in Research Library, versioned as v1 → Later edit creates v2 with change note.

### J3 — Member reports inappropriate content
Member views a post/comment/research item → Clicks "Report" → Selects reason → Submits → Item enters Moderation Queue → MODERATOR/ADMIN reviews → Approves, edits, restricts, or removes → Audit log entry created → Reporting member optionally notified of outcome.

### J4 — Admin reviews new signups and payment health
Admin logs in → Admin Dashboard → Views Users, Memberships, Payments widgets → Reviews Moderation Queue → Reviews Audit Log → Reviews core metrics (Total Users, Paid Members, MRR, Churn, Research Created).

### J5 — Free member hits a paywall
Free member attempts to open Community, Research Workspace, or full Research Library item → System shows a **contextual** upgrade prompt (e.g., "Full research history is available to Core members") with plan comparison → Member proceeds to payment or dismisses → State persisted so prompt frequency is reasonable.

**[LOCKED — OD-13]** Upgrade prompts are contextual and explanatory, not aggressive popups shown on every interaction. A dismissed prompt is not re-shown for the same gated action within the same session at minimum (exact re-prompt cadence is a UX-design detail for the Architecture/UI phase, not re-opened as a product ambiguity).

### J6 — Payment failure / subscription lapse
Core member's renewal payment fails → System retries per payment provider policy → Member notified in-app and (if wired) by email → After grace period, membership reverts to `FREE` state (access downgraded, content NOT deleted) → Member can re-subscribe at any time to restore Core access to existing content.

## 13. Authentication Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| AUTH-001 | Users can register with email + password. | MUST | Given a valid unused email and a password meeting policy, when a user submits registration, then an account is created in an unverified state and a verification email is sent. |
| AUTH-002 | Users must verify their email before accessing Community or Research Workspace features. | MUST | Given an unverified account, when the user attempts to open the Community or Research Workspace, then the system blocks access and prompts email verification. |
| AUTH-003 | Users can log in with email + password. | MUST | Given valid credentials, when a user submits the login form, then a session/token is issued and the user is redirected to their dashboard. |
| AUTH-004 | Users can log out. | MUST | Given an authenticated session, when the user selects logout, then the session/token is invalidated and subsequent protected requests are rejected. |
| AUTH-005 | Users can request a password reset via email. | MUST | Given a registered email, when the user requests a reset, then a time-limited reset link is emailed and old links/tokens are invalidated once used. |
| AUTH-006 | **[LOCKED — OD-03]** Password policy: minimum 12 characters, passphrases allowed, no forced uppercase/symbol/digit composition rules. Passwords hashed with Argon2id. | MUST | Given a password under 12 characters, when submitted at registration or reset, then the system rejects it with a message stating the 12-character minimum; a 12+ character passphrase with no special characters is accepted. |
| AUTH-007 | Failed login attempts are rate-limited / throttled (login throttling required per OD-03). | MUST | Given repeated failed login attempts from the same account/IP within a window, when the threshold is exceeded, then further attempts are throttled or temporarily blocked. |
| AUTH-008 | **[LOCKED — OD-04]** Authentication uses a secure, HttpOnly, server-side session/cookie architecture. Auth tokens are never stored in `localStorage`/`sessionStorage`. If JWTs are used internally, access tokens are short-lived (~15 min) and refresh tokens (~30 days) support rotation and revocation — exact mechanism finalized in the Architecture document. | MUST | Given a successful login, when inspecting browser storage, then no auth token is present in localStorage/sessionStorage; the session is carried via a secure HttpOnly cookie. |
| AUTH-009 | Breached-password protection (e.g., checking against known-breach lists) is implemented where practical. | SHOULD | Given a password matching a known breached-password list, when submitted at registration, then the user is warned and encouraged (not forced) to choose a different password. |

## 14. User Profile Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PROF-001 | Profile includes: name, username, bio, experience level, investment interests, joined date, membership tier, research contribution count, badges/role indicator. | MUST | Given a logged-in user, when they view their profile, then all listed fields are displayed, with empty fields shown as empty/prompt-to-complete rather than errors. |
| PROF-002 | Users can edit their own name, username, bio, experience level, and interests. | MUST | Given an authenticated user, when they submit valid profile edits, then the profile is updated and reflected immediately. |
| PROF-003 | Username must be unique. | MUST | Given a username already in use, when a user attempts to set it, then the system rejects the change with a clear error. |
| PROF-004 | The system shall NOT collect financial account details, PAN/bank details, or brokerage credentials as part of the MVP profile. | MUST | Given the profile edit form, when reviewed, then no fields request bank, brokerage, or trading-account information. |
| PROF-006 | **[LOCKED — OD-21]** Profile is **text-only in MVP** — no avatar/profile-image upload. Profile fields are limited to: name, username, bio, experience level, investment interests (matching Section 14 exactly). Avatar upload is Phase 2. | MUST | Given the profile edit page, when reviewed, then no image-upload control is present. |
| PROF-005 | Other members can view a public view of a member's profile (name, username, bio, badges, public research contributions) subject to the Community requirements (Section 16). | SHOULD | Given a logged-in Core member, when they view another member's public profile, then non-private fields are visible and private fields (e.g., email) are not. |

## 15. Membership / Subscription Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| MEM-001 | Two MVP tiers exist: `FREE` and `CORE` (paid, monthly recurring). | MUST | Given the pricing/plans page, when viewed, then exactly two purchasable/selectable tiers are shown (Pro/Guild+/Annual/Founding are not present in MVP). |
| MEM-002 | **[LOCKED — OD-22]** Core tier launch price is **₹799/month**, treated as a founding MVP price hypothesis, not a permanent price. Price remains a configurable system value so it can be revised (e.g., to ₹999/₹1,499) once retention/conversion/CAC data exists. | MUST | Given an admin with pricing permissions, when they update the Core price, then new subscriptions use the updated price and existing active subscriptions are unaffected until their renewal. |
| MEM-003 | **[LOCKED — OD-02]** Core membership gates: private Community, full Research Workspace, complete Research Library, member research, research discussions, Watchlist, member dashboard, live/private sessions, member directory. | MUST | Given a FREE member, when they attempt to access any Core-gated feature, then they are shown an upgrade prompt and denied access server-side (not just hidden in UI). |
| MEM-004 | **[LOCKED — OD-02]** Free tier includes: public educational articles/content, selected research *examples* (curated, not the full library), limited/read-only community access, public company & research previews, founder content, newsletter, basic profile. | MUST | Given a FREE member, when they browse the platform, then only content explicitly marked public/example is fully viewable; Core-only items show a paywall preview per LIB-003. |
| MEM-005 | Subscription lifecycle states: `active`, `past_due`, `canceled`, `expired`. | MUST | Given a subscription record, when its state changes, then the member's effective access level updates accordingly within one billing cycle check cycle. |
| MEM-006 | **[LOCKED — OD-06]** Failed payment triggers a **7-day grace period** before downgrade to FREE. Flow: payment fails → automatic retry → member keeps Core access → reminder notification → retry → after 7 days with no successful payment → downgrade to FREE (content retained, not deleted). | MUST | Given a `past_due` subscription, when 7 days elapse without a successful payment or retry, then the member's tier reverts to FREE and their content is retained, not deleted; if payment succeeds within the 7 days, access continues uninterrupted. |
| MEM-007 | **[LOCKED — OD-07]** Members can cancel their own subscription at any time. Cancellation means no future renewal; Core access continues until the end of the current paid period. Refunds are NOT automatic; the initial policy is "refunds are handled per the published refund policy and applicable law," with the actual policy finalized before paid launch (legal/accounting input required — see OD-07 status in Section 51). | MUST | Given an active Core member, when they cancel, then the subscription is marked `canceled`, no further charge occurs, and access continues until the current paid period ends. |

## 16. Community Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| COMM-001 | Community is organized into channels: Announcements, General Discussion, Research Discussion, Market Discussion, Learning, Help/Questions, Off Topic. | MUST | Given the Community section, when a Core member navigates it, then all listed channels are visible and postable-to (Announcements restricted to ADMIN/MODERATOR post rights). |
| COMM-002 | Only Core members (and elevated roles) can post/comment; FREE members can view public channels only (if any are public) or see the paywall. | MUST | Given a FREE member, when they attempt to post, then the action is blocked with an upgrade prompt. |
| COMM-003 | Members can create posts with text content in a channel. | MUST | Given an authenticated Core member in a channel, when they submit a valid post, then it appears in that channel's feed immediately. |
| COMM-004 | Members can comment/reply on posts. | MUST | Given an existing post, when a Core member submits a comment, then it is attached to the post and visible to other members. |
| COMM-005 | Members can react to posts/comments (e.g., like). | SHOULD | Given a post, when a member reacts, then the reaction count updates and duplicate reactions from the same user are prevented. |
| COMM-006 | Members can bookmark/save posts. | SHOULD | Given a post, when a member bookmarks it, then it appears in their personal saved list. |
| COMM-007 | Members can report a post or comment. | MUST | Given any post/comment, when a member submits a report with a reason, then a moderation-queue entry is created (see MOD-001). |
| COMM-008 | Post/comment authors can edit or delete their own content within a reasonable window; edits are marked as edited. | SHOULD | Given a post authored by the current user, when they edit it, then the post displays an "edited" indicator and the edit is timestamped. |

## 17. Posts / Comments / Reactions Requirements
(Detailed requirements captured under COMM-003 through COMM-008 above; this section defines data-level rules.)

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PCR-001 | Every post/comment stores: author, channel (posts only, nullable if the post is research-linked — see OD-14), **nullable `research_id`**, content, created_at, updated_at, edited flag, status (`visible`, `hidden`, `removed`). | MUST | Given any post or comment record, when inspected, then all listed fields are present and status defaults to `visible`; a research-discussion post has `research_id` set and a general community post has it `NULL`. |
| PCR-002 | Removed content is soft-deleted (status changed), never hard-deleted, to preserve audit trail. | MUST | Given a MODERATOR removes a post, when the removal is executed, then the row persists in the database with status `removed` and is excluded from normal feeds. |
| PCR-003 | Reaction types are limited to a small fixed set in MVP (e.g., single "like" reaction). | SHOULD | Given the reaction UI, when inspected, then only the approved reaction type(s) are selectable. |

## 18. Moderation Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| MOD-001 | Reported content creates a Moderation Queue entry with reporter, reason, target content reference, timestamp. | MUST | Given a report submission, when processed, then a queue entry with all listed fields is created and visible to MODERATOR/ADMIN roles. |
| MOD-002 | MODERATOR/ADMIN can take one of: Approve (dismiss report), Edit, Restrict (hide from public, visible to author), Remove, Suspend member. | MUST | Given a queue entry, when a MODERATOR selects an action, then the content/member state updates accordingly and an audit log entry is created. |
| MOD-003 | **[LOCKED — OD-08]** Flagged phrases/patterns (e.g., "guaranteed return," "sure shot," "target price," "100% return," "multibagger," "no loss") are stored in an **admin-configurable `moderation_rules` table** (fields: phrase, severity, enabled, action, created_by, updated_at) rather than hardcoded. Matches are a moderation SIGNAL only — content is flagged for human review, NEVER automatically blocked, altered, deleted, or labeled unlawful. | MUST | Given a post/research submission containing a phrase present and enabled in `moderation_rules`, when submitted, then the content is published/saved normally AND a moderation-queue entry is auto-created for human review; an ADMIN can add/disable a rule without a code deployment. |
| MOD-004 | Suspended members lose posting/commenting ability but retain read access appropriate to their tier. | MUST | Given a suspended member, when they attempt to post, then the action is blocked with a message explaining the suspension. |
| MOD-005 | All moderation actions are logged to the audit trail (see Section 31). | MUST | Given any moderation action, when executed, then an immutable audit log entry records actor, action, target, timestamp, and reason. |

## 19. Research Library Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| LIB-001 | Research Library organizes published research by Company and by Industry. | MUST | Given the Research Library, when a user browses, then they can filter/navigate by company and by industry. |
| LIB-002 | Each research item displays: title, author, company, industry, created date, updated date, status, tags, source count, version number. | MUST | Given a research item in the library, when viewed, then all listed metadata fields are shown. |
| LIB-003 | FREE members see a paywalled preview (title, summary, author) of Core-only research items. | MUST | Given a FREE member, when they open a Core-only research item, then full content is hidden and an upgrade prompt is shown. |
| LIB-004 | Members can search the Research Library by keyword (title, company name, tags) using PostgreSQL full-text search. | MUST | Given a search query, when submitted, then matching research items ranked by relevance are returned within the performance target in NFR (Section 43). |
| LIB-005 | **[LOCKED — OD-14]** Members can comment/discuss on a published research item by **reusing the Community posts/comments system**, not a separate discussion engine. Research-linked posts are ordinary `posts` rows with a nullable `research_id` foreign key set; general community posts have `research_id = NULL`. | MUST | Given a published research item, when a Core member adds a discussion comment on it, then a `posts`/`comments` row is created with `research_id` set to that item's ID and is visible attached to that item on the Research Library page. |

## 20. Company Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| CO-001 | A Company record stores: name, sector/industry, market (e.g., NSE/BSE), website, description; no live price/market data. | MUST | Given a company record, when viewed, then only static metadata fields are shown, with no real-time price or ticker feed. |
| CO-002 | **[LOCKED — OD-23]** Companies can be created by members when submitting research on a company not yet in the system, subject to basic validation/dedup. **MVP scope is exchange-listed companies only** (NSE/BSE or other recognized exchange); private/unlisted companies are out of scope for MVP and rejected at company-creation validation with a message explaining listed-company scope. | MUST | Given a research submission for a new company, when the member enters company details for a listed company, then a new Company record is created and linked, with duplicate-name warnings if a close match exists; given an attempt to add an unlisted/private company, then creation is blocked with an explanatory message. |
| CO-003 | Company page displays linked research count, member theses count, related discussion count, and a watchlist toggle. | MUST | Given a company page, when viewed, then counts of related research/theses/discussions are shown accurately and the current user's watchlist state is reflected. |
| CO-004 | ADMIN can edit/merge/deduplicate company records. | SHOULD | Given two duplicate company records, when an ADMIN merges them, then all research/watchlist references are re-pointed to the surviving record and the duplicate is archived, not deleted. |

## 21. Research Workspace Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| RES-001 | Core members can create a new Research item selecting: Company, Research Type, Industry. | MUST | Given a Core member starts "New Research," when they select company/type/industry, then a draft research record is created in `draft` status. |
| RES-002 | Research follows the Q-RESEARCH structured sections (Section 22) as required form fields, not a single free-text box. | MUST | Given the research editor, when inspected, then each Q-RESEARCH stage is a distinct, individually-saved field/section. |
| RES-003 | Research can be saved as a draft at any point (incomplete fields allowed). | MUST | Given a partially completed research form, when the member clicks "Save Draft," then the record persists with `draft` status and no publish-time validation is enforced. |
| RES-004 | Publishing a research item requires: Thesis, Risks, Counter-thesis, at least one Source, Research Date, and the compliance disclosure block (Section 25) to be completed. | MUST | Given a draft missing any required field, when the member attempts to publish, then publishing is blocked and the missing fields are listed. |
| RES-005 | Published research is visible in the Research Library per membership tier rules (LIB-003). | MUST | Given a successful publish action, when completed, then the item's status changes to `published` and it appears in the Research Library. |
| RES-006 | Editing a published research item creates a new version rather than silently overwriting (Section 24). | MUST | Given a published research item, when the author edits and re-saves, then a new version record is created, the prior version remains accessible, and a "what changed" note is required. |

## 22. Q-RESEARCH Workflow

The Research Workspace implements the blueprint's Q-RESEARCH framework as the structured editor sections. Each stage below is a required data section on the Research entity (not merely a UI label):

| Stage | Field name | Purpose |
|---|---|---|
| Q — Quality | `business_quality` | Is this a good business? |
| R — Reality | `financial_snapshot` | What do the financials actually say? |
| E — Economics | `business_model` | How does the company make money? |
| S — Strength | `competitive_position` | Moat / competitive analysis |
| E — Estimate | `valuation_range` | Valuation range with explicit assumptions |
| A — Asymmetry | `bull_base_bear` | Bull / base / bear cases |
| R — Risk | `risk_register` | What can permanently impair capital |
| C — Catalyst | `catalysts` | What could change the market's view, and when |
| H — Hypothesis | `invalidation_conditions` | What would prove the thesis wrong |

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| QRES-001 | Each Q-RESEARCH stage is stored as a distinct field on the research record. | MUST | Given a research record in the database, when inspected, then all nine Q-RESEARCH stage fields exist as separate columns/sub-documents. |
| QRES-002 | The editor UI presents stages in the fixed Q-R-E-S-E-A-R-C-H order with progress indication. | SHOULD | Given the research editor, when opened, then stages are shown in the documented order with a completion indicator per stage. |
| QRES-003 | `bull_base_bear` requires content in bear case specifically (not just bull) before publish. | MUST | Given a draft where only the bull case is filled, when the member attempts to publish, then validation blocks publish and flags the missing bear case. |

## 23. Thesis Requirements

In MVP, "Thesis" is not a separate top-level entity from Research — it is the structured Q-RESEARCH research record itself (per RES-002/QRES-001). This resolves an ambiguity between the two source documents, where the tech spec implies a separate lightweight "Thesis" object and the blueprint treats "Thesis Lab" as a pillar name for the same underlying research content.

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| THESIS-001 | A member's "Continue Research" / dashboard widget references their in-progress Research (draft) items, not a separate Thesis table. | MUST | Given a member dashboard, when viewed, then "Continue Research" lists the member's draft research items. |
| THESIS-002 | Published research items are the unit that appears in the Research Library, Company pages, and profile "research contributions" count. | MUST | Given a published research item, when counted, then it increments the author's research contribution count exactly once regardless of subsequent versions. |

## 24. Research Versioning Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| VER-001 | Every publish or post-publish edit creates an immutable version snapshot. | MUST | Given a published research item edited twice, when version history is viewed, then three snapshots exist (v1 original publish, v2, v3) each independently viewable. |
| VER-002 | Each version stores a required "what changed / why changed" note authored by the editor. | MUST | Given an edit to a published item, when the member attempts to save, then they must provide a non-empty change note before the new version is created. |
| VER-003 | Version history is publicly viewable alongside the research item (subject to the item's tier gating). | MUST | Given a research item with 3 versions, when a viewer with sufficient access opens it, then they can view the current version and browse prior versions with their change notes and dates. |
| VER-004 | The current published version is what displays by default; prior versions are clearly marked as historical. | MUST | Given a research item, when loaded, then the latest version renders by default and older versions carry a visible "historical version" label. |

## 25. Research Source / Citation Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| SRC-001 | Research requires at least one source entry to publish (URL, document reference, or filing citation with a label). | MUST | Given a draft with zero sources, when publish is attempted, then the system blocks publishing with a "at least one source required" message. |
| SRC-002 | Each source entry stores: label/description, URL or reference text, and (optionally) the specific claim it supports. | MUST | Given a source entry, when saved, then label and reference fields are both persisted; empty labels are rejected. |
| SRC-003 | Research submission includes a mandatory **compliance disclosure block**: conflict disclosure (yes/no + detail if yes), position disclosure (yes/no + detail if yes), research date. | MUST | Given the publish action, when the disclosure block is incomplete (conflict/position not explicitly answered), then publish is blocked. |
| SRC-004 | "No position / no conflict" is a valid, explicit, first-class answer (not an inferred default from leaving the field blank). | MUST | Given the disclosure block, when a member selects "No" for conflict and position, then the item can publish with those values recorded as explicit answers, distinct from an unanswered state. |

## 26. Watchlist Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| WL-001 | Core members can add/remove a company to/from their personal watchlist. | MUST | Given a company page, when a Core member clicks "Add to Watchlist," then the company appears in their watchlist and the button state toggles to "Remove." |
| WL-002 | Watchlist view lists companies with links to related research/discussion counts, no market data. | MUST | Given the watchlist view, when opened, then each entry shows company name and related-content counts only. |
| WL-003 | Watchlist is private to the member by default. | SHOULD | Given another member's profile, when viewed, then their watchlist contents are not exposed unless the viewing member owns it. |

## 27. Notification Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| NOTIF-001 | In-app notifications generated for: comment on your post/research, reaction on your post, report resolved, moderation action on your content, subscription state change. | MUST | Given a triggering event (e.g., a comment on the member's post), when it occurs, then an in-app notification record is created for the relevant member. |
| NOTIF-002 | Members can view a notification list and mark notifications as read. | MUST | Given unread notifications, when the member opens the notification panel, then unread items are visually distinguished and can be marked read individually or in bulk. |
| NOTIF-003 | Email notifications are SHOULD-HAVE, contingent on a transactional email provider being integrated (see OD-12). | SHOULD | Given email notifications are enabled, when a triggering event occurs, then a corresponding email is sent to the member's verified address. |

## 28. Admin Dashboard Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| ADMIN-001 | Admin dashboard sections: Users, Memberships, Payments, Posts, Comments, Research, Reports, Moderation, Companies, Industries, Content, System Settings, Audit Log. | MUST | Given an ADMIN/SUPER_ADMIN login, when they open the dashboard, then all listed sections are present and navigable. |
| ADMIN-002 | **[LOCKED — OD-15]** Metrics displayed: Total Users, Active Users, Paid Members, MRR, New Members, Churn, **Research Created**, **Research Updated**, **Research Discussions**, Posts, Comments, Reports. **"Research Reviewed" is explicitly NOT shown in MVP** — since Guild-based peer review doesn't exist yet, showing a "reviewed" count built from ordinary comments would misrepresent formal peer review as having occurred. This metric is reintroduced correctly in Phase 2 once Guild peer review ships. | MUST | Given the metrics panel, when loaded, then each listed metric displays a current computed value with its computation window (e.g., MRR "as of today," Churn "trailing 30 days"), and no metric labeled "Research Reviewed" is present anywhere in the MVP admin UI. |
| ADMIN-007 | **[LOCKED — OD-19]** Metrics are computed via **direct real-time database queries** for MVP scale; no analytics warehouse or complex ETL pipeline is built. Expensive-to-compute metrics may use scheduled background aggregation (Redis/worker) only if a specific metric proves too slow as a direct query — this is an exception, not the default. | MUST | Given MVP-scale data (per Section 8 growth scenarios), when the metrics panel loads, then values are computed via direct query at request time unless a specific metric has been documented as using scheduled aggregation. |
| ADMIN-003 | ADMIN can change a user's role among the 6 MVP roles. | MUST | Given an ADMIN viewing a user record, when they change the role, then the change takes effect immediately and is recorded in the audit log. |
| ADMIN-004 | ADMIN can suspend/reinstate a member account. | MUST | Given a member account, when an ADMIN suspends it, then the member cannot log in to post/comment/create research (read access per FREE tier remains unless SUPER_ADMIN fully disables login), and the action is audit-logged. |
| ADMIN-005 | ADMIN can view and search the audit log. | MUST | Given the audit log view, when an ADMIN searches by actor, action type, or date range, then matching entries are returned. |
| ADMIN-006 | SUPER_ADMIN-only actions: managing other ADMIN accounts, system settings, pricing changes. | MUST | Given an ADMIN (not SUPER_ADMIN) attempting to modify another ADMIN's role or system pricing, then the action is denied with a permissions error. |

## 29. Payment / Subscription Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PAY-001 | **[LOCKED — OD-10]** Members can subscribe to Core via **Razorpay** as the MVP payment gateway (supports UPI, cards, netbanking, recurring billing, webhooks). Razorpay is accessed only through a `PaymentService` abstraction so an additional/alternate provider (e.g., Stripe) can be added later without touching calling code. Per BOUND-003, paid billing does not go live in production before OD-01 legal review is resolved. | MUST | Given a FREE member on the pricing page, when they complete checkout successfully via Razorpay, then their membership tier updates to CORE and a payment record is created; given the codebase, when `PaymentService` is inspected, then no calling code references the Razorpay SDK directly. |
| PAY-002 | Payment records store: amount, currency, status, gateway reference ID, subscription period, timestamp. | MUST | Given a completed payment, when inspected in Admin, then all listed fields are present and match the gateway's transaction. |
| PAY-003 | Failed/declined payments are recorded and do not silently grant access. | MUST | Given a declined payment attempt, when it occurs, then no membership upgrade happens and the failure is visible to the member with a retry option. |
| PAY-004 | Recurring billing automatically attempts renewal per Razorpay's subscription mechanism; failed renewal follows the 7-day grace period (MEM-006). | MUST | Given an active Core subscription reaching its renewal date, when renewal is due, then Razorpay attempts the charge and the result updates the subscription state per MEM-005/MEM-006. |
| PAY-005 | **[LOCKED — OD-16]** An **implementation-ready billing architecture** is built from Day 1: a `billing`/`invoices` table (invoice_id, customer, amount, tax, currency, payment_status, invoice_date, billing_period, payment_gateway_reference) plus `BillingService`, `TaxService`, and `InvoiceService` abstractions. Tax logic is centralized in `TaxService`, not hardcoded across the application. The **exact GST/HSN-SAC treatment and invoice format remain pending accountant/tax-professional confirmation before paid launch** — this requirement locks the architecture, not the tax rate/logic itself. | MUST | Given the codebase, when reviewed, then tax computation exists only inside `TaxService`, not duplicated inline elsewhere; given a completed payment, when an invoice is generated, then it is produced via `InvoiceService` and stored in the `invoices` table with all listed fields. |
| PAY-006 | **[LOCKED — OD-07]** Refunds are not automatic. Initial refund policy displayed to members: "Refunds are handled according to the published refund policy and applicable law." The definitive refund policy is finalized with legal/accounting input before paid launch (tracked as part of OD-07). | MUST | Given a cancellation request, when processed, then no refund is automatically issued; the member sees the standing refund-policy statement, and any refund is a manual/reviewed action until the definitive policy is published. |

## 30. RBAC and Permission Matrix

MVP roles (locked, no others): `SUPER_ADMIN`, `ADMIN`, `MODERATOR`, `REVIEWER`, `MEMBER` (Core), `FREE_MEMBER`.

| Capability | FREE_MEMBER | MEMBER (Core) | REVIEWER | MODERATOR | ADMIN | SUPER_ADMIN |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| View public/free content | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| View Core-gated content | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Post/comment in Community | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create/publish Research | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Comment on others' research with elevated visibility ("reviewer comment") | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Add/remove Watchlist items | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Access Moderation Queue | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Take moderation action (edit/restrict/remove/suspend) | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Manage Companies (create/edit/merge) | ❌ | Create only | Create only | ✅ | ✅ | ✅ |
| View Admin Dashboard | ❌ | ❌ | ❌ | Partial (moderation only) | ✅ | ✅ |
| Change member roles (up to MODERATOR/REVIEWER) | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| Change/create ADMIN accounts | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Edit system settings / pricing | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| View Audit Log | ❌ | ❌ | ❌ | Partial (own actions) | ✅ | ✅ |

Note on REVIEWER role (per Reconciliation R4): in MVP, the "elevated visibility reviewer comment" is a UI distinction only (e.g., a labeled badge on their comment) — it does NOT constitute a peer-review workflow gate (that is Phase 2 Guild peer review). REVIEWER role assignment in MVP is manual, by ADMIN, based on judgment — there is no automated 90-day reputation calculation in MVP (deferred; see Phase 2 backlog).

**[LOCKED — OD-05]** Roles are **not mutually exclusive**. A single user's account can simultaneously carry `MEMBER` (Core) status plus `REVIEWER` and/or `MODERATOR` role grants — e.g., a user can be `MEMBER + REVIEWER + MODERATOR` at once. RBAC is implemented as an additive set of role grants per user, not a single enum field, so this overlap is possible without a schema change later.

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| RBAC-001 | All 6 roles are enforced server-side on every protected endpoint. | MUST | Given a request from a role lacking a capability per the matrix, when the endpoint is called directly (bypassing UI), then the server returns 403 Forbidden. |
| RBAC-002 | Role changes take effect on the user's next request (no re-login required beyond normal token refresh). | SHOULD | Given a role change by an ADMIN, when the affected user makes their next request within their token's validity, then the new permissions apply. |
| RBAC-003 | A user may hold multiple role grants simultaneously (e.g., MEMBER + REVIEWER + MODERATOR); the data model stores roles as a set, not a single value. | MUST | Given a user granted both REVIEWER and MODERATOR, when their permissions are evaluated, then capabilities from both roles apply concurrently. |

## 31. Audit Logging Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| AUDIT-001 | Audit log records: actor user ID, action type, target entity type/ID, timestamp, before/after state summary (where applicable), reason/note if provided. | MUST | Given any auditable action, when it completes, then a log entry with all listed fields is written before the action's success response is returned to the actor. |
| AUDIT-002 | Auditable actions include (minimum): moderation actions, role changes, subscription state changes, company merges, research removal, member suspension. | MUST | Given each listed action type, when performed in a test, then a corresponding audit entry is verifiable in the log. |
| AUDIT-003 | Audit log is append-only; no update/delete capability exposed via any application interface. | MUST | Given an audit log entry, when any user (including SUPER_ADMIN) attempts to edit or delete it through the application, then no such capability exists in the UI or API. |

## 32. Compliance-by-Design Requirements

**This section, and this product, do not constitute legal compliance by themselves.** The controls below reduce risk and create the right structural habits, but classification under SEBI's Investment Adviser or Research Analyst regulations (or any other applicable law) must be assessed by a qualified Indian securities lawyer/compliance professional before accepting paid members for anything resembling personalized advice or paid securities research. This assessment is a **blocking business task**, tracked as OD-01, and is not satisfied by any engineering work in this PRD.

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| CMPL-001 | Every published research item captures: source disclosure, research date, assumptions (via valuation_range field), risks, counter-thesis, conflict disclosure, position disclosure. | MUST | Given a published research item, when inspected, then all seven listed elements are present and non-empty (explicit "No" is non-empty for disclosure fields). |
| CMPL-002 | The system never generates or displays a specific target price or "buy/sell by [date]" instruction anywhere in the product. | MUST | Given any research or post content rendering, when reviewed, then no system-generated field labeled as a target price/timing call exists (member free-text cannot be fully prevented from mentioning valuation scenarios, which is permitted per the blueprint's "safe harbor" distinction between a valuation range and a target-price call). |
| CMPL-003 | Flagged-phrase content triggers human moderation review, never automatic legal/compliance determination (see MOD-003). | MUST | Same acceptance criterion as MOD-003. |
| CMPL-004 | Community rules and the Member Charter (blueprint Appendix C) are presented and require acknowledgment at onboarding before a member can post. | MUST | Given a new member's first attempt to post, when they have not yet acknowledged the Member Charter, then they are prompted to acknowledge it before the post is accepted. |
| CMPL-005 | The product surfaces a persistent, non-dismissible-on-first-view risk disclosure at signup and at the point of first payment. | MUST | Given the registration flow and the checkout flow, when either is completed, then the user must affirmatively acknowledge the risk disclosure before proceeding. |

## 33. Content Moderation Requirements

(Merged into Section 18 — Moderation Requirements. Cross-reference: MOD-001 through MOD-005.)

## 34. Data / Privacy Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PRIV-001 | The system collects only the minimum personal data needed for MVP functionality (name, email, profile fields, payment metadata from the gateway — not raw card data). | MUST | Given the database schema, when reviewed, then no raw payment card data is stored (card data remains with the PCI-compliant gateway). |
| PRIV-002 | A Privacy Policy is presented and linked from registration and footer. | MUST | Given the registration page, when viewed, then a link to the Privacy Policy is present and accessible before account creation. |
| PRIV-003 | **[LOCKED — OD-17]** Account deletion requests use a **soft-delete / anonymization architecture**: the user record is marked deleted and personal identifying fields are anonymized; content required for platform integrity (published research others rely on, audit log entries per AUDIT-003) is retained per the operational/legal record requirement rather than hard-deleted. The exact retention period for anonymized/operational records is pending legal/privacy review before finalization. | MUST | Given a member's account-deletion request, when processed, then their personal profile fields are anonymized, their login is disabled, and any published research/audit entries they authored remain in the system attributed to an anonymized identity rather than being deleted. |
| PRIV-004 | **[LOCKED — OD-18]** Architecture prefers **India-region hosting** (e.g., AWS `ap-south-1`) as the MVP default deployment choice. This is a product/infrastructure preference, not a claim that India data residency is legally mandated — the actual legal requirement remains subject to confirmation by counsel and must not be assumed either way during implementation. | MUST | Given the infrastructure/deployment configuration, when reviewed, then the primary region is `ap-south-1` (or equivalent India region); given any product or marketing copy, when reviewed, then it does not claim data residency as a compliance guarantee without legal sign-off. |

## 35. Error / Edge-Case Behavior

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| ERR-001 | Duplicate company name on research creation surfaces a "possible duplicate" warning rather than silently creating a duplicate. | MUST | Given an existing company "Reliance Industries," when a member types a close-match name, then a suggestion to select the existing company is shown before a new one is created. |
| ERR-002 | Concurrent edits to the same draft research item are handled with a last-write-wins policy plus a warning if the record changed since the editor loaded it. | SHOULD | Given two sessions editing the same draft, when the second session saves after the first, then a warning is shown that the content may have changed. |
| ERR-003 | Payment webhook failures/retries are handled idempotently (no double-crediting of subscription periods). | MUST | Given a payment gateway webhook delivered twice for the same transaction ID, when processed, then the subscription period is extended only once. |
| ERR-004 | Deleted/merged companies do not break existing research links. | MUST | Given a company merge (CO-004), when completed, then all previously linked research items resolve to the surviving company record without broken links. |

## 36. Empty / Loading / Error States

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| STATE-001 | Every list view (Research Library, Community feed, Watchlist, Notifications, Admin tables) has a defined empty state with guidance text and a relevant call-to-action. | MUST | Given a list view with zero items, when loaded, then an empty-state message and CTA (e.g., "Create your first research item") is shown instead of a blank area. |
| STATE-002 | Every async data view has a defined loading state (skeleton/spinner). | MUST | Given a page that fetches data asynchronously, when data is loading, then a loading indicator is shown, not a blank or broken layout. |
| STATE-003 | Every form/action has a defined error state with a user-readable message (not raw exception text). | MUST | Given a failed API call triggered by a user action, when the failure is returned, then a human-readable error message is displayed and raw stack traces/exception text are never shown to the user. |

## 37. Search Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| SEARCH-001 | Search covers Research Library (title, company name, tags) and Company names, using PostgreSQL full-text search. | MUST | Given a search query matching a research title or company name, when submitted, then relevant results are returned ranked by text-search relevance. |
| SEARCH-002 | Search respects membership tier gating (FREE members see paywalled previews in results, not full content). | MUST | Given a FREE member's search results including a Core-only item, when displayed, then that result shows a preview/paywall indicator, not full content. |
| SEARCH-003 | Search results return within the performance target defined in NFR (Section 43). | MUST | See PERF-002. |

## 38. Analytics / Event Tracking Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| ANLY-001 | The system tracks distinct events: `signup`, `email_verified`, `payment_completed`, `research_draft_created`, `research_published`, `research_commented`, `post_created`, `watchlist_added`, `login`. | MUST | Given each listed user action, when performed, then a corresponding analytics event with user ID and timestamp is recorded. |
| ANLY-002 | **[LOCKED — OD-09]** "Meaningful research activity" is computed per member per calendar month as: at least one of {research draft created/updated, research section completed, source added, research published, substantive comment/review on a research item}. Reactions ("likes") and general (non-research) community comments are explicitly excluded from this metric. | MUST | Given a member who only liked posts and commented in General Discussion during a month, when evaluated, then they are classified as NOT having performed a meaningful research activity that month; given a member who added a source to a draft, when evaluated, then they ARE classified as having done so. |
| ANLY-003 | Admin metrics (Section 28) are computed from these tracked events plus core entity tables, on a defined refresh cadence (real-time query vs. scheduled batch — see OD-19). | MUST | Given the Admin metrics panel, when loaded, then displayed values are consistent with the underlying event/entity data as of the documented refresh cadence. |

## 39. MVP Database Entities

Phase 1 (MVP) tables, per the reconciled tech spec list (Guild-related and Thesis-as-separate-entity tables removed per R3/R23 reconciliation):

```
users
profiles
plans
subscriptions
payments
invoices                 -- [LOCKED, OD-16] billing/tax architecture, Day 1

posts                    -- includes nullable research_id FK [LOCKED, OD-14]
comments
reactions
reports

moderation_rules         -- [LOCKED, OD-08] admin-configurable flagged-phrase rules

companies                -- listed companies only [LOCKED, OD-23]
research                 -- includes embedded Q-RESEARCH fields + compliance disclosure block
research_versions
research_sources
research_tags

watchlists
watchlist_items

notifications

audit_logs
```

**[LOCKED — OD-20]** Explicitly deferred to Phase 2 (not created in MVP migrations): `theses`, `thesis_updates` (superseded by `research`/`research_versions` per Section 23), `guilds`, `guild_members`, `guild_cycles`, `guild_reviews`, **`courses`, `lessons`, `resources` (Learning Hub — confirmed Phase 2, not MVP)**, `organizations` (B2B — Phase 2+).

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| DB-001 | Schema uses additive-only migrations so Phase 2 tables (guilds, courses, etc.) can be added without breaking MVP tables/relationships. | SHOULD | Given the Phase 1 schema, when a Phase 2 migration adds `guilds`/`guild_members`, then no existing Phase 1 table requires a breaking change to accommodate it. |
| DB-002 | `research` and `research_versions` are separate tables; `research` holds the current pointer/state, `research_versions` holds immutable snapshots. | MUST | Given a research item, when queried, then its current version content matches the latest row in `research_versions` for that research ID. |

## 40. High-Level API Requirements

| ID | Requirement | Priority |
|---|---|---|
| API-001 | RESTful JSON API exposed by the FastAPI backend, versioned (e.g., `/api/v1/...`). | MUST |
| API-002 | All mutating endpoints require authentication except registration, login, password reset request. | MUST |
| API-003 | All endpoints enforce RBAC per Section 30 server-side, independent of frontend routing. | MUST |
| API-004 | Payment endpoints handle gateway webhooks separately from user-facing endpoints, with signature verification. | MUST |
| API-005 | API errors return a consistent structured error format (code, message, field-level detail where applicable). | MUST |

Full endpoint-level specification is an Architecture-phase deliverable, not this PRD (see Recommended Next Step).

## 41. Integration Requirements

| ID | Requirement | Priority | Notes |
|---|---|---|---|
| INT-001 | **[LOCKED — OD-10]** Payment gateway: **Razorpay**, behind a `PaymentService` abstraction. | MUST | Supports recurring subscriptions, webhooks, UPI/cards/netbanking. Abstraction allows a second provider later without refactoring callers. |
| INT-002 | **[LOCKED — OD-12]** Transactional email provider: **Resend**, behind an `EmailService` abstraction, covering verification, password reset, payment events, membership emails, and notifications. | MUST (for AUTH-001/AUTH-005) | Email verification and password reset are MUST-HAVE MVP; general notification emails remain SHOULD-HAVE (NOTIF-003) but the provider is now locked so they can ship if time allows. |
| INT-003 | **[LOCKED — OD-11 / OD-21]** S3-compatible object storage: **AWS S3**, `ap-south-1` (Mumbai) region preferred as the default deployment target, behind an `ObjectStorageService` abstraction. **No avatar/profile-image upload in MVP (OD-21 — text-only profile fields)**, so object storage in MVP is provisioned for future use and any MVP-scope file needs (if none arise, this remains a SHOULD-HAVE, low-urgency integration). India-region hosting is a product preference here, not a claim of legal requirement — see OD-18. | SHOULD | Provider locked as AWS S3; legal data-residency obligation remains open per OD-18. |
| INT-004 | No integrations with brokers, trading platforms, or market-data vendors in MVP. | OUT OF SCOPE | Per R8/blueprint Section 15 and BOUND-001. |

## 42. Security Requirements

| ID | Requirement | Priority |
|---|---|---|
| SEC-001 | All traffic served over HTTPS/TLS. | MUST |
| SEC-002 | Passwords hashed with bcrypt or argon2; never logged. | MUST |
| SEC-003 | RBAC enforced server-side on every protected endpoint (see RBAC-001). | MUST |
| SEC-004 | Input validation/sanitization on all user-submitted content to prevent XSS/injection. | MUST |
| SEC-005 | Rate limiting on authentication and payment endpoints. | SHOULD |
| SEC-006 | Payment card data never touches QFinance servers directly (handled by PCI-compliant gateway). | MUST |
| SEC-007 | Admin/SUPER_ADMIN actions require re-authentication or step-up verification for sensitive operations (e.g., role escalation, pricing change). | SHOULD |
| SEC-008 | Regular dependency/vulnerability scanning as part of CI (implementation detail for Architecture phase). | SHOULD |

## 43. Performance Requirements

| ID | Requirement | Priority |
|---|---|---|
| PERF-001 | Page load (server-rendered initial content) under ~2.5s on a typical broadband connection for MVP scale (target: <500 paid members per Section 9 scenarios). | SHOULD |
| PERF-002 | Search queries return within ~1s at MVP data scale. | SHOULD |
| PERF-003 | Admin metrics panel loads within ~3s (batch-computed metrics acceptable per OD-19). | SHOULD |

Formal load targets should be revisited once real usage data exists; MVP-scale numbers above are directional, not contractual.

## 44. Accessibility Requirements

| ID | Requirement | Priority |
|---|---|---|
| A11Y-001 | Core flows (registration, login, research creation, community posting) are keyboard-navigable. | SHOULD |
| A11Y-002 | Sufficient color contrast per WCAG AA for text content. | SHOULD |
| A11Y-003 | Form fields have associated labels for screen readers. | SHOULD |

Full WCAG AA conformance audit is not a hard MVP gate but should not be architecturally precluded.

## 45. SEO Requirements for Public Pages

| ID | Requirement | Priority |
|---|---|---|
| SEO-001 | Public pages (landing, pricing, about, public research previews) have unique title tags and meta descriptions. | SHOULD |
| SEO-002 | Public pages generate a sitemap.xml and respect robots.txt (gated/private content excluded from indexing). | SHOULD |
| SEO-003 | Server-side rendering (Next.js) used for public pages to ensure crawlability. | SHOULD |

## 46. Out-of-Scope Items

Consolidated from Section 11 and founder instruction — items the MVP will explicitly NOT include:

- Trading, broker integration, portfolio execution
- Personalized investment recommendations or automated stock calls
- Real-time stock/market-data terminal
- Options strategy engine, crypto trading, social copy-trading
- Complex/member-facing AI agents
- Native mobile applications
- Microservices architecture
- Large-scale data warehouse
- More than 2 membership tiers (Free/Core only)
- Certification system
- Marketplace functionality
- Research Guilds and guild-based peer review
- Direct messaging between members

## 47. Phase 2 Backlog

- Research Guilds: pods (6–10 members), weekly research cycles, structured peer review, Guild Rooms, Reviewer/pod-lead model, guild-health metrics
- Automated reputation/progression system (Contributor → Reviewer → Analyst → Fellow) replacing manual REVIEWER assignment
- Certification Track (Research Fundamentals → Valuation → Thesis Defense, badge)
- Learning Hub (Courses, Lessons, Resources) — **confirmed Phase 2** (OD-20 locked)
- Avatar/profile-image upload — **confirmed Phase 2** (OD-21 locked)
- Pro tier, Annual plans, Founding member offer, Guild+ add-on billing
- Member-facing AI: "What changed?" briefings linked to source documents, archive search assistant
- Direct messaging between members
- Partner integrations (brokers, fintech apps) per blueprint Section 14
- Advanced/member-intelligence analytics dashboard
- Company deduplication/data-quality tooling beyond basic merge

## 48. Phase 3 Backlog

- Full AI research copilot embedded in the workspace (labeled draft/assistant output only, never community-endorsed)
- Research knowledge graph
- Licensed real-time market/financial data integration
- Native mobile applications
- Elasticsearch/OpenSearch-based search at scale
- Regulated professional research/advisory offering (contingent on SEBI registration and legal sign-off)
- B2B/organizational licensing of the research workflow

## 49. Acceptance Criteria for Every MVP Module

Each module's representative, testable acceptance criteria are embedded directly in its requirements table above (Sections 13–30). Summary of module-level "Definition of Ready to Ship" gates:

| Module | Ships when... |
|---|---|
| Auth | AUTH-001 through AUTH-006 pass; AUTH-007/008 implemented if in scope for launch |
| Profile | PROF-001 through PROF-004 pass |
| Membership | MEM-001 through MEM-007 pass; payment gateway integration live |
| Community | COMM-001 through COMM-008 pass; MOD-001/002 pass for reported content |
| Moderation | MOD-001 through MOD-005 pass |
| Research Library | LIB-001 through LIB-004 pass |
| Company | CO-001 through CO-003 pass |
| Research Workspace | RES-001 through RES-006, QRES-001 through QRES-003, SRC-001 through SRC-004 pass |
| Versioning | VER-001 through VER-004 pass |
| Watchlist | WL-001, WL-002 pass |
| Notifications | NOTIF-001, NOTIF-002 pass |
| Admin Dashboard | ADMIN-001 through ADMIN-007 pass |
| RBAC | RBAC-001 pass for all 6 roles across all gated actions |
| Audit Log | AUDIT-001 through AUDIT-003 pass |
| Compliance | CMPL-001 through CMPL-005 pass, AND legal/compliance professional review (OD-01) completed before public paid launch |

## 50. Definition of Done

A feature/module is "Done" for MVP purposes when:

1. All MUST-HAVE requirement IDs for that module are implemented and their acceptance criteria pass in a test environment.
2. RBAC enforcement is verified server-side, not assumed from UI hiding.
3. Relevant audit log entries are verified to be created where applicable.
4. Empty/loading/error states are implemented for any new list/form view (Section 36).
5. No feature flagged OUT OF SCOPE, PHASE 2, or PHASE 3 has been silently implemented instead of deferred.
6. Any assumption not explicitly resolved in this PRD has been raised as an Open Product Decision (Section 51) rather than decided silently in code.
7. Founder (Prakash) has reviewed and approved the feature against this PRD before it is considered launch-ready.
8. For anything touching compliance-sensitive surfaces (research publishing, disclosures, moderation), the behavior matches Section 32 exactly — deviations require an explicit PRD amendment, not an ad hoc code decision.

---

## 51. LOCKED PRODUCT DECISIONS (formerly Open Product Decisions)

All 23 decisions below have been reviewed by the founder and are now **LOCKED** for MVP scope and design. The corresponding requirement IDs elsewhere in this PRD have been updated to reflect each decision and are marked `[LOCKED — OD-xx]` inline. Items marked `*` in the Status column are **product-level decisions locked now**, while a **legal/accounting/provider implementation detail remains subject to professional confirmation before paid launch** — this distinction is preserved rather than glossed over.

| ID | Decision | Locked Resolution | Status |
|---|---|---|---|
| OD-01 | SEBI/legal classification review | **BLOCKING FOR PAID LAUNCH.** Development, internal testing, and a closed non-paid beta may proceed now. Legal/compliance review by India-qualified securities counsel must occur, and sign-off obtained, before any paid Core billing goes live in production (see Section 3A — BOUND-003). This is not satisfied by any engineering work and must not be marked "done" by development activity. | 🔴 BLOCKING (paid launch only) |
| OD-02 | Free vs. Core content boundary | FREE: public educational articles, selected research *examples*, limited/read-only community, public company/research previews, founder content, newsletter. CORE: full Research Library, full Research Workspace, private community, member research/discussions, watchlists, member dashboard, live/private sessions. Applied to MEM-003/MEM-004. | 🔒 LOCKED |
| OD-03 | Password policy | Minimum 12 characters, passphrases allowed, no forced complexity composition. Argon2id hashing, rate limiting/login throttling, breached-password check where practical. Applied to AUTH-006/AUTH-007/AUTH-009. | 🔒 LOCKED |
| OD-04 | Session/token architecture | Secure, HttpOnly, server-side cookie-based session architecture; no tokens in localStorage/sessionStorage. If JWT is used internally: ~15 min access / ~30 day refresh with rotation/revocation. Exact implementation detail finalized in Architecture doc. Applied to AUTH-008. | 🔒 LOCKED (impl. detail → Architecture phase) |
| OD-05 | MODERATOR/REVIEWER role overlap | Roles are **not mutually exclusive** — a user can hold MEMBER + REVIEWER + MODERATOR simultaneously. RBAC modeled as an additive role-grant set. Applied to Section 30 note + RBAC-003. | 🔒 LOCKED |
| OD-06 | Failed-payment grace period | **7 days.** Fail → retry → access retained → reminder → retry → downgrade to FREE at day 7 if unresolved. Applied to MEM-006. | 🔒 LOCKED |
| OD-07 | Refund/cancellation policy | Cancel anytime; no future renewal; access continues to end of paid period. No automatic refunds; standing policy statement shown until legal/accounting finalizes the definitive refund policy before paid launch. Applied to MEM-007/PAY-006. | 🔒 LOCKED* (refund specifics pending legal/accounting) |
| OD-08 | Flagged-phrase list | Stored in an admin-configurable `moderation_rules` table (phrase, severity, enabled, action, created_by, updated_at); matches are a review signal only, never automatic removal/legal classification. Applied to MOD-003 + `moderation_rules` table (Section 39). | 🔒 LOCKED |
| OD-09 | "Meaningful research activity" definition | Per member per month: at least one of {research draft created/updated, section completed, source added, research published, substantive research review/comment}. Likes and general community comments excluded. Applied to Section 8 + ANLY-002. | 🔒 LOCKED |
| OD-10 | Payment gateway | **Razorpay**, behind a `PaymentService` abstraction (future providers addable without refactor). Applied to PAY-001/INT-001. | 🔒 LOCKED* (provider locked; billing go-live still gated by OD-01/BOUND-003) |
| OD-11 | Object storage provider | **AWS S3**, `ap-south-1` (Mumbai) preferred region, behind an `ObjectStorageService` abstraction. India residency is a preference here, not a confirmed legal requirement (see OD-18). Applied to INT-003. | 🔒 LOCKED* (residency legal status still open) |
| OD-12 | Transactional email provider | **Resend**, behind an `EmailService` abstraction. Covers verification, reset, payment events, membership emails, notifications. Applied to INT-002. | 🔒 LOCKED |
| OD-13 | Upgrade-prompt UX | Contextual, explanatory prompts (e.g., "Full research history is available to Core members"), not aggressive popups on every click. Applied to J5 / new note in Section 12. | 🔒 LOCKED (exact re-prompt cadence deferred to UI/UX spec) |
| OD-14 | Research-item discussion architecture | **Reuses the Community posts/comments system** via a nullable `research_id` FK on `posts`, rather than a separate discussion engine. Applied to LIB-005, PCR-001, Section 39 schema. | 🔒 LOCKED |
| OD-15 | "Research Reviewed" admin metric | **Removed from MVP entirely** (not shown, not approximated via comment counts) to avoid a misleading vanity metric; reintroduced correctly in Phase 2 once Guild peer review exists. Applied to ADMIN-002. | 🔒 LOCKED |
| OD-16 | GST/tax-invoicing | Implementation-ready billing architecture built Day 1 (`invoices` table + `BillingService`/`TaxService`/`InvoiceService` abstractions, tax logic centralized). Exact GST/HSN-SAC treatment and invoice format still pending accountant/tax-professional confirmation before paid launch. Applied to PAY-005. | 🔒 LOCKED* (architecture locked; tax specifics pending) |
| OD-17 | Deleted-account data retention | Soft-delete/anonymization architecture: personal fields anonymized, login disabled; operationally/legally-required records (published research, audit entries) retained under an anonymized identity. Exact retention period pending legal/privacy review. Applied to PRIV-003. | 🔒 LOCKED* (architecture locked; retention period pending) |
| OD-18 | India data residency | Architecture defaults to India-region hosting (`ap-south-1`) as a product/infrastructure preference. This is explicitly NOT asserted as a legal requirement pending confirmation by counsel. Applied to PRIV-004. | 🔒 LOCKED* (hosting preference locked; legal requirement status remains open) |
| OD-19 | Admin metrics computation | Direct real-time database queries by default; scheduled background aggregation only as a documented exception for specific slow metrics. No analytics warehouse in MVP. Applied to ADMIN-007. | 🔒 LOCKED |
| OD-20 | Learning Hub scope | **Confirmed Phase 2.** Not part of MVP. Educational content is published through the Community/Research Library instead. Applied to Section 39, Section 47. | 🔒 LOCKED |
| OD-21 | Avatar/profile image | **No avatar upload in MVP** — text-only profile fields (name, username, bio, experience level, interests). Phase 2. Applied to PROF-006, Section 47. | 🔒 LOCKED |
| OD-22 | Core launch price | **₹799/month**, treated explicitly as a founding MVP price hypothesis subject to revision once retention/conversion/CAC data exists — not a permanent price. Applied to MEM-002. | 🔒 LOCKED |
| OD-23 | Private/unlisted companies | **Excluded from MVP** — exchange-listed companies only (NSE/BSE or other recognized exchange). Company creation validation rejects unlisted-company attempts with an explanatory message. Applied to CO-002. | 🔒 LOCKED |

### Decisions still requiring professional (non-engineering) action before paid launch

These are locked at the *product/architecture* level in this PRD, but still require a named non-engineering action before Core billing can go live, per BOUND-003:

- **OD-01** — Legal/compliance review of SEBI Investment Adviser / Research Analyst applicability. **Hard blocker.**
- **OD-07 / OD-16** — Final refund policy wording and GST/tax invoice treatment, from legal/accounting.
- **OD-17** — Final data-retention period for deleted-account records, from legal/privacy review.
- **OD-18** — Confirmation of whether India data residency is a legal requirement (currently a hosting *preference*, not a compliance claim).

None of these four may be silently marked "resolved" by engineering work; they require the named professional's explicit input, tracked outside this PRD (e.g., as founder action items ahead of the paid-launch gate).

---

*QFinance MVP PRD v1.0 — 🔒 LOCKED. All 23 Open Product Decisions resolved per founder review on 2026-08-28. Ready to proceed to `QFINANCE_ARCHITECTURE_V1.md`.*
