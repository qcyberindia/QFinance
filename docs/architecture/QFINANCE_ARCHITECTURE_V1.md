# QFinance — Architecture V1

**Status:** 🔒 APPROVED — founder approval confirmed 2026-08-29 (explicit chat confirmation: "i approve it go further"). **Amended 2026-08-29 (Amendment 1, post-approval)** — see revision note below. **Amended again 2026-08-29 (Amendment 2, post-approval): AD-18, `research.access_tier`.** **Amended a third time 2026-08-29 (Amendment 3, post-approval, Founder Decision #2): AD-19, authorization rule for `access_tier` changes (ADMIN/SUPER_ADMIN only).**
**Revision note:** This document has been through two correction passes following formal verification (see `work_memory.md` Decision Log), plus two post-approval amendments. Pass 1 (2026-08-28) addressed: moderation action/content-status modeling, bookmarks, member directory, CSV export, REVIEWER badge semantics, channel constraint, polymorphic-target trade-off documentation, and CSRF mechanism (Sections 19–20). Pass 2 (2026-08-28) resolved the one remaining HIGH finding: analytics/event-tracking architecture for ANLY-001–003 (Section 21, AD-15, Section 22). **Amendment 1 (2026-08-29, post-approval)** resolved three gaps surfaced while deriving API Specification V1: `research.title`/`research.summary` had no defined source despite the API assuming they existed (AD-16); CMPL-004/005 acknowledgment storage was undefined (AD-16, new `compliance_acknowledgments` table); published-research edits could bypass publish-validation (AD-17). **Amendment 2 (2026-08-29, post-approval, Founder Decision #1)** added `research.access_tier` (AD-18) — an authoritative classification distinguishing MEM-004's curated "free example" research items from ordinary Core-only research, a gap identified during API Specification V1 review that neither Architecture, Database Schema, nor API Specification V1 previously addressed. Zero HIGH/CRITICAL findings remain outstanding.
**Depends on:** `docs/PRD/QFINANCE_MVP_PRD_V1.md` (🔒 LOCKED v1.0), `work_memory.md`
**Document type:** Implementation-ready technical architecture for the QFinance MVP
**Project root:** `/home/prd/Projects/QFinance`

This document translates the locked PRD into a concrete technical design. It does not reopen any of the 23 locked Open Product Decisions (OD-01–OD-23) or the MVP Product Boundary (BOUND-001–003). Where the PRD leaves an implementation detail open (e.g., OD-04 session mechanism, OD-13 re-prompt cadence), this document resolves it at the architecture level only — never at the product level.

**Compliance notice (read before anything else):** This architecture implements compliance-by-design controls (audit logging, disclosure fields, moderation workflow, RBAC, data retention scaffolding). These controls reduce risk and create the correct structural habits. **They do not, by themselves, constitute legal compliance** under SEBI Investment Adviser/Research Analyst regulations or any other applicable law. Paid billing remains gated on OD-01 (professional Indian securities/legal review) regardless of how complete this architecture or its implementation is.

---

## 1. System Architecture

QFinance MVP is a **modular monolith**: one deployable backend service (FastAPI) with clearly bounded internal modules, one deployable frontend service (Next.js), one PostgreSQL database, and one Redis instance. There are no microservices, no service mesh, and no independent per-module databases in MVP.

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser (Web)                        │
└───────────────────────────┬────────────────────────────────┘
                              │ HTTPS
┌───────────────────────────▼────────────────────────────────┐
│  Next.js (TypeScript) — SSR public pages, CSR app shell       │
│  Deployed as a single frontend service                        │
└───────────────────────────┬────────────────────────────────┘
                              │ REST/JSON over HTTPS (/api/v1)
┌───────────────────────────▼────────────────────────────────┐
│  FastAPI — Modular Monolith (single deployable)                │
│  ┌───────────┬───────────┬───────────┬───────────┐            │
│  │ auth      │ community │ research  │ billing    │  ...       │
│  │ module    │ module    │ module    │ module     │            │
│  └───────────┴───────────┴───────────┴───────────┘            │
│  Cross-cutting: RBAC, audit, validation, error handling        │
└──────┬───────────────────┬───────────────────┬───────────────┘
        │                    │                    │
┌───────▼───────┐   ┌────────▼────────┐   ┌───────▼────────┐
│ PostgreSQL     │   │ Redis            │   │ External APIs   │
│ (primary DB,   │   │ (cache, job      │   │ Razorpay, Resend│
│  full-text     │   │  queue, session  │   │ AWS S3          │
│  search)       │   │  support)        │   │ (via abstractions)│
└───────────────┘   └─────────────────┘   └────────────────┘
```

Key properties:
- Single Postgres database, single schema, module boundaries enforced in code (Python package structure), not by separate databases.
- Redis is used for caching, background job queueing (e.g., email sending, webhook processing retries), and optionally rate-limiting counters — never as a primary datastore.
- External providers (Razorpay, Resend, AWS S3) are never called directly from route handlers or domain logic; all access goes through a service abstraction (Section 4.4).
- Deployment target defaults to AWS `ap-south-1` (Mumbai) as an infrastructure *preference* (OD-18), not asserted as a legal data-residency requirement.

## 2. Architecture Principles

These principles govern every subsequent decision in this document, in priority order (per founder instruction):

1. **Simplicity** — the smallest architecture that satisfies the locked PRD. No speculative infrastructure for Phase 2/3 features.
2. **Security** — server-side enforcement of every access-control decision; never trust the client.
3. **Maintainability** — clear module boundaries, one obvious place for each concern, minimal cross-module coupling.
4. **Testability** — business logic is separable from framework/route code and from provider SDKs, so it can be unit-tested without hitting Postgres/Redis/external APIs.
5. **Clear module boundaries** — each PRD functional area maps to one backend module; modules communicate through explicit interfaces, not by reaching into each other's tables directly wherever avoidable.
6. **Provider abstraction** — Razorpay, Resend, and AWS S3 are swappable behind `PaymentService`, `EmailService`, `ObjectStorageService` respectively, per PRD INT-001/002/003.
7. **Future extensibility** — schema and module boundaries are additive-friendly for Phase 2 (Guilds, Learning Hub, avatar upload, reputation engine) without breaking MVP tables (DB-001).
8. **Avoidance of premature infrastructure** — no analytics warehouse, no Elasticsearch, no microservices, no Kubernetes requirement, no multi-region setup in MVP.

## 3. Technology Stack

Locked per PRD Sections 10 and 41 — not reopened here, only made concrete:

| Layer | Technology | Notes |
|---|---|---|
| Frontend framework | Next.js (App Router) + TypeScript | SSR for public/SEO pages (SEO-003), CSR app shell for authenticated app |
| Backend framework | FastAPI (Python 3.12+) | Async-first, Pydantic v2 for validation |
| ORM | SQLAlchemy 2.x (async) + Alembic | Alembic manages migrations (not created in this phase) |
| Database | PostgreSQL 16+ | Primary datastore, `tsvector`/`GIN` for search |
| Cache / queue | Redis 7+ | Caching, background jobs (via a lightweight worker, e.g., `arq` or `RQ` — decision in Section 8.7), session-adjacent rate-limit counters |
| Auth | Server-side session via secure HttpOnly cookie; Argon2id password hashing | Per OD-03/OD-04 |
| Payments | Razorpay, behind `PaymentService` | OD-10 |
| Transactional email | Resend, behind `EmailService` | OD-12 |
| Object storage | AWS S3 (`ap-south-1` preferred), behind `ObjectStorageService` | OD-11/OD-18, provisioned but low-usage in MVP (no avatar upload) |
| Search | PostgreSQL full-text search (`tsvector`, `GIN` index) | NFR-006, no external search engine |
| Containerization | Docker + Docker Compose (dev/staging) | Section 8.8 |
| CI | GitHub Actions (or equivalent) | Lint, type-check, test, build, dependency scan |

No additional technology (message broker, GraphQL layer, separate analytics DB, etc.) is introduced without an explicit architecture amendment justified against Principle 8.

## 4. Backend Architecture (FastAPI Modular Monolith)

### 4.1 Monorepo Structure

```
/home/prd/Projects/QFinance
├── apps/
│   ├── web/                    # Next.js frontend
│   └── api/                    # FastAPI backend
│       ├── app/
│       │   ├── main.py                # FastAPI app factory, router mounting
│       │   ├── core/                  # cross-cutting: config, security, db session, errors
│       │   │   ├── config.py
│       │   │   ├── security.py        # password hashing, session/cookie helpers
│       │   │   ├── db.py              # SQLAlchemy engine/session
│       │   │   ├── deps.py            # shared FastAPI dependencies (current_user, rbac guards)
│       │   │   ├── errors.py          # structured error format (API-005)
│       │   │   └── audit.py           # audit log writer used by all modules
│       │   ├── modules/
│       │   │   ├── auth/              # AUTH-*, session issuance/verification
│       │   │   ├── users/             # PROF-*
│       │   │   ├── membership/        # MEM-*, plans, subscription state
│       │   │   ├── billing/           # PAY-*, invoices, BillingService/TaxService/InvoiceService
│       │   │   ├── community/         # COMM-*, PCR-*
│       │   │   ├── moderation/        # MOD-*, moderation_rules
│       │   │   ├── research/          # RES-*, QRES-*, VER-*, SRC-*
│       │   │   ├── companies/         # CO-*
│       │   │   ├── watchlist/         # WL-*
│       │   │   ├── notifications/     # NOTIF-*
│       │   │   ├── admin/             # ADMIN-*
│       │   │   ├── audit/             # AUDIT-* (read/query side; write side lives in core/audit.py)
│       │   │   └── search/            # SEARCH-*
│       │   ├── integrations/          # provider adapters, NOT called directly by modules
│       │   │   ├── payment_service.py     # PaymentService → Razorpay adapter
│       │   │   ├── email_service.py       # EmailService → Resend adapter
│       │   │   └── object_storage_service.py  # ObjectStorageService → S3 adapter
│       │   ├── jobs/                  # background job definitions (email sending, webhook retries)
│       │   └── api/
│       │       └── v1/                # route registration per module, versioned (API-001)
│       ├── tests/
│       ├── alembic/                   # migration environment (empty until DB design phase)
│       ├── pyproject.toml
│       └── Dockerfile
├── docs/
│   ├── PRD/
│   └── architecture/
├── work_memory.md
└── docker-compose.yml                 # local dev: api, web, postgres, redis
```

Each `modules/<name>/` package follows a consistent internal shape: `models.py` (SQLAlchemy models owned by this module), `schemas.py` (Pydantic request/response models), `service.py` (business logic, framework-agnostic where practical), `router.py` (FastAPI route definitions, thin — delegates to `service.py`), `permissions.py` (module-specific RBAC checks beyond the generic role guard).

### 4.2 Domain/Module Boundaries

| Module | Owns (tables) | Depends on |
|---|---|---|
| `auth` | `users` (auth-relevant columns), sessions (Redis-backed, not a table) | `core.security` |
| `users` | `profiles`, `compliance_acknowledgments` | `auth` |
| `membership` | `plans`, `subscriptions` | `billing`, `users` |
| `billing` | `payments`, `invoices` | `membership`, `integrations.payment_service` |
| `community` | `posts`, `comments`, `reactions`, `reports`, `bookmarks` | `research` (nullable `research_id` FK only), `moderation` |
| `moderation` | `moderation_rules`, `moderation_actions` | `community`, `research`, `users`, `audit` |
| `research` | `research`, `research_versions`, `research_sources`, `research_tags` | `companies`, `users` |
| `companies` | `companies` | — |
| `watchlist` | `watchlists`, `watchlist_items` | `companies`, `users` |
| `notifications` | `notifications` | consumed by all modules that trigger events |
| `admin` | (no owned tables — reads across modules) | all modules (read-only aggregation) |
| `audit` | `audit_logs` | write path exposed via `core/audit.py`, used by all modules |
| `search` | (no owned tables — queries `research`, `companies` via `tsvector`) | `research`, `companies` |
| `analytics` | `events` | consumed by `admin`; written to by every module that emits a tracked event (`auth`, `membership`/`billing`, `research`, `community`) |

Modules interact through their `service.py` public functions, not by importing another module's SQLAlchemy models directly, **except** where the PRD explicitly locks a shared-table design (e.g., OD-14: `community.posts.research_id` is a first-class nullable FK to `research.research`, since research-item discussion intentionally reuses the Community system rather than building a separate discussion engine).

### 4.3 Frontend Architecture (Next.js)

- **App Router**, TypeScript throughout.
- Public/SEO-sensitive routes (landing, pricing, about, public research previews) are server-rendered per SEO-003.
- Authenticated app routes (dashboard, research workspace, community, admin) are rendered behind auth middleware that checks the HttpOnly session cookie server-side before rendering (never relies on a client-side "is logged in" flag alone for access control — the API remains the actual enforcement point per RBAC-001/API-003).
- API calls from the frontend go through a thin typed API client (`apps/web/lib/api-client.ts`) that always sends credentials (`credentials: 'include'`) so the HttpOnly session cookie is attached; no auth token is ever read/written by frontend JS (AUTH-008).
- State: server data fetched via Next.js server components/fetch where possible; client-side interactivity (forms, research editor, community feed) uses React state/local component state — no global client-side store is introduced unless a specific UX need justifies it (Principle 8).
- Frontend never encodes business rules (e.g., publish-validation, RBAC capability checks) as the source of truth — UI-side checks are a UX convenience only; the API is authoritative (mirrors RBAC-001's "never client-side only").

### 4.4 Integration / Provider Abstraction Layer

Per PRD INT-001/002/003 and explicit instruction, no module calls a provider SDK directly.

```python
# integrations/payment_service.py (conceptual shape, not final implementation)
class PaymentService(Protocol):
    async def create_subscription(self, customer, plan) -> SubscriptionHandle: ...
    async def cancel_subscription(self, subscription_id) -> None: ...
    async def verify_webhook_signature(self, payload, signature) -> bool: ...

class RazorpayPaymentService(PaymentService):
    ...  # only file that imports the Razorpay SDK
```

The same pattern applies to `EmailService` (Resend) and `ObjectStorageService` (S3). Business logic in `membership`, `billing`, `notifications`, and any future avatar-upload module (Phase 2) depends only on the `Protocol`/interface, never the concrete adapter class, so a second provider can be added later without touching calling code (explicit PRD requirement under PAY-001 and INT-003).

`BillingService`, `TaxService`, and `InvoiceService` (PAY-005/OD-16) are internal domain services (not provider adapters) living in `modules/billing/service.py`, structured so all tax computation is centralized in `TaxService` and never duplicated inline elsewhere in the codebase — this is a **testable acceptance criterion**, not just a guideline.

## 5. PostgreSQL Architecture

### 5.1 General Conventions (apply to every table below)

- Primary keys: `UUID` (generated `gen_random_uuid()` via `pgcrypto`, or app-generated UUIDv7 for time-sortability — decision deferred to implementation, noted in Section 17 Open Questions).
- Every table has `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` and `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (updated via trigger or ORM `onupdate`).
- Soft-deletable entities (per PRIV-003, PCR-002, CO-004) carry `deleted_at TIMESTAMPTZ NULL` — a row with `deleted_at IS NOT NULL` is excluded from normal application queries but retained for audit/integrity. Hard deletes are not used for user-generated content or audit-relevant records anywhere in MVP.
- Foreign keys default to `ON DELETE RESTRICT` unless a specific soft-delete/anonymization flow requires otherwise (explicitly noted per table).
- All monetary values stored as integer minor units (paise) to avoid floating-point currency bugs, with currency stored alongside (`amount_paise INTEGER`, `currency CHAR(3) DEFAULT 'INR'`).
- Additive-only migrations (DB-001): Phase 2 tables (`guilds`, `courses`, etc.) are never designed into MVP tables now, only left room for via nullable/absent FKs.

### 5.2 Entity-Relationship Overview

```
users ──1:1── profiles
users ──1:N── subscriptions ──N:1── plans
subscriptions ──1:N── payments
subscriptions ──1:N── invoices
users ──1:N── posts ──N:1── (nullable) research
posts ──1:N── comments
posts/comments ──1:N── reactions
posts/comments ──1:N── reports
users ──1:N── research ──1:N── research_versions
research ──1:N── research_sources
research ──N:M── research_tags (via join, or array column — see 5.3)
research ──N:1── companies
users ──1:N── watchlists ──1:N── watchlist_items ──N:1── companies
users ──1:N── notifications
users ──1:N── audit_logs (as actor)
users ──1:N── bookmarks ──N:1── posts
users ──1:N── compliance_acknowledgments
users ──1:N── moderation_actions (as moderator, polymorphic target: posts/comments/research/users)
reports ──1:N── moderation_actions (nullable, an action may be proactive/report-less)
moderation_rules (standalone, referenced by moderation workflow logic, not FK'd from content)
users ──1:N── events (append-only behavioral/analytics log, polymorphic entity reference)
```

### 5.3 Complete MVP Table Specification

#### `users`
Purpose: authentication identity and account state.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| email | CITEXT | UNIQUE, NOT NULL |
| password_hash | TEXT | NOT NULL (Argon2id, OD-03) |
| email_verified_at | TIMESTAMPTZ | NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('active','suspended','deleted')), DEFAULT 'active' |
| is_anonymized | BOOLEAN | NOT NULL DEFAULT false (PRIV-003) |
| last_login_at | TIMESTAMPTZ | NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |
| deleted_at | TIMESTAMPTZ | NULL (soft-delete/anonymization flow, PRIV-003) |

Indexes: UNIQUE on `email` (partial: `WHERE deleted_at IS NULL` to allow email reuse after anonymization, pending legal confirmation of retention rules under OD-17).

#### `profiles`
Purpose: text-only user-facing profile (PROF-001–006).

| Column | Type | Constraints |
|---|---|---|
| user_id | UUID | PK, FK → users.id, ON DELETE CASCADE |
| name | TEXT | NOT NULL |
| username | CITEXT | UNIQUE, NOT NULL |
| bio | TEXT | NULL |
| experience_level | TEXT | NULL, CHECK (experience_level IN ('beginner','intermediate','advanced')) |
| interests | TEXT[] | NULL |
| role_grants | TEXT[] | NOT NULL DEFAULT '{FREE_MEMBER}' — additive RBAC set (OD-05/RBAC-003); values constrained at application layer to the 6 locked roles |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

No `avatar_url` column exists in MVP — explicitly excluded per OD-21/PROF-006. Adding it later is an additive migration (nullable column), not a breaking change.

Note on roles: `role_grants` is modeled as a Postgres `TEXT[]` for MVP simplicity (Principle 8: avoid premature infra like a separate `user_roles` join table) while still satisfying "roles as an additive set, not a single enum" (OD-05). A normalized `user_roles` join table is a documented future migration path if role-based queries become complex (Section 15).

#### `plans`
Purpose: membership tiers (MEM-001).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| code | TEXT | UNIQUE, NOT NULL, CHECK (code IN ('FREE','CORE')) — exactly 2 tiers, MEM-001 |
| price_paise | INTEGER | NOT NULL DEFAULT 0 |
| currency | CHAR(3) | NOT NULL DEFAULT 'INR' |
| billing_interval | TEXT | NOT NULL DEFAULT 'monthly' |
| is_active | BOOLEAN | NOT NULL DEFAULT true |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

`CORE` seed row: `price_paise = 79900` (₹799.00), configurable per MEM-002/OD-22 — a system value, not a hardcoded constant in application code.

#### `subscriptions`
Purpose: membership lifecycle (MEM-005–007).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL |
| plan_id | UUID | FK → plans.id, NOT NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('active','past_due','canceled','expired')) |
| current_period_start | TIMESTAMPTZ | NOT NULL |
| current_period_end | TIMESTAMPTZ | NOT NULL |
| grace_period_ends_at | TIMESTAMPTZ | NULL (7-day grace window, OD-06) |
| canceled_at | TIMESTAMPTZ | NULL |
| gateway_subscription_id | TEXT | NULL (Razorpay reference, behind `PaymentService`) |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Indexes: `(user_id, status)` for fast "current effective tier" lookup.

#### `payments`
Purpose: payment attempt/result records (PAY-002/003).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| subscription_id | UUID | FK → subscriptions.id, NOT NULL |
| amount_paise | INTEGER | NOT NULL |
| currency | CHAR(3) | NOT NULL DEFAULT 'INR' |
| status | TEXT | NOT NULL, CHECK (status IN ('pending','succeeded','failed','refunded')) |
| gateway_reference_id | TEXT | NOT NULL, UNIQUE (idempotency key for webhook processing, ERR-003) |
| billing_period_start, billing_period_end | TIMESTAMPTZ | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

UNIQUE on `gateway_reference_id` is the mechanism that guarantees ERR-003 idempotency (a webhook delivered twice for the same transaction cannot double-credit).

#### `invoices`
Purpose: implementation-ready billing/tax architecture (PAY-005, OD-16).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK (invoice_id) |
| user_id | UUID | FK → users.id, NOT NULL (customer) |
| payment_id | UUID | FK → payments.id, NOT NULL |
| amount_paise | INTEGER | NOT NULL |
| tax_paise | INTEGER | NOT NULL DEFAULT 0 (computed only via `TaxService`) |
| currency | CHAR(3) | NOT NULL DEFAULT 'INR' |
| payment_status | TEXT | NOT NULL |
| invoice_date | DATE | NOT NULL |
| billing_period | TEXT | NOT NULL |
| gateway_reference | TEXT | NOT NULL |
| tax_treatment_version | TEXT | NULL — records which `TaxService` ruleset/version produced this invoice, so historical invoices remain reproducible once GST/HSN-SAC treatment is finalized by an accountant (OD-16 pending item) |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

The exact GST/HSN-SAC field set and invoice numbering scheme remain pending accountant confirmation (OD-16) — this table only locks the *architecture*, not the tax logic, matching the PRD's explicit framing.

#### `posts`
Purpose: community posts, including research-linked discussion (OD-14, COMM-*, PCR-001).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| author_id | UUID | FK → users.id, NOT NULL |
| channel | TEXT | NULL, CHECK (channel IS NULL OR channel IN ('announcements','general_discussion','research_discussion','market_discussion','learning','help_questions','off_topic')) — constrained to the 7 channels locked in COMM-001; nullable because a research-linked post may not belong to a channel; a second CHECK (channel IS NOT NULL OR research_id IS NOT NULL) enforces "must be either a channel post or a research post" |
| research_id | UUID | NULL, FK → research.id — set for research-discussion posts (OD-14), NULL for general community posts |
| content | TEXT | NOT NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('visible','restricted','removed')), DEFAULT 'visible' — see Section 10.1 for the full moderation state model; `'restricted'` replaces the earlier ad hoc `'hidden'` value to match `reports.resolution_action` terminology exactly (MOD-002) |
| is_edited | BOOLEAN | NOT NULL DEFAULT false |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

Indexes: `(channel)` for feed queries, `(research_id)` for research-item discussion queries, partial index `WHERE status = 'visible'` for feed performance.

Content-visibility semantics (per MOD-002 acceptance criteria): `'visible'` — shown to all users with tier access; `'restricted'` — hidden from public/other members, still visible to the author and to MODERATOR/ADMIN/SUPER_ADMIN (implements "Restrict: hide from public, visible to author"); `'removed'` — hidden from everyone including the author, retained in the database only (soft-delete, never hard-deleted, per PCR-002).

#### `comments`
Purpose: replies on posts.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| post_id | UUID | FK → posts.id, NOT NULL |
| author_id | UUID | FK → users.id, NOT NULL |
| content | TEXT | NOT NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('visible','restricted','removed')), DEFAULT 'visible' — same semantics as `posts.status` above |
| is_edited | BOOLEAN | NOT NULL DEFAULT false |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

#### `reactions`
Purpose: single "like" reaction type in MVP (PCR-003).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL |
| target_type | TEXT | NOT NULL, CHECK (target_type IN ('post','comment')) |
| target_id | UUID | NOT NULL |
| reaction_type | TEXT | NOT NULL, CHECK (reaction_type = 'like') — MVP has exactly one type |
| created_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(user_id, target_type, target_id, reaction_type)` — prevents duplicate reactions (COMM-005).

#### `reports`
Purpose: moderation queue entry source (MOD-001).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| reporter_id | UUID | FK → users.id, NOT NULL |
| target_type | TEXT | NOT NULL, CHECK (target_type IN ('post','comment','research')) |
| target_id | UUID | NOT NULL |
| reason | TEXT | NOT NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('open','resolved')), DEFAULT 'open' |
| resolution_action | TEXT | NULL, CHECK (resolution_action IN ('approved','edited','restricted','removed','member_suspended')) |
| resolved_by | UUID | NULL, FK → users.id |
| resolved_at | TIMESTAMPTZ | NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |

`reports` records the *complaint* (who reported what, why, and its resolution summary). The step-by-step *action* the moderator actually took — including its effect on content state — is separately recorded in `moderation_actions` below, which is the authoritative audit trail for MOD-002/AUDIT-001/002. `reports.resolution_action` is a denormalized summary field for quick queue display; the `moderation_actions` row for the same event is the source of truth.

#### `moderation_actions`
Purpose: authoritative, append-only audit trail of every moderation action taken (MOD-002, MOD-005, AUDIT-001/002). Added in this correction pass to resolve the action/content-status mismatch identified during architecture verification — see Section 10.1 for the full state model this table supports.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| moderator_id | UUID | FK → users.id, NOT NULL — the acting MODERATOR/ADMIN/SUPER_ADMIN |
| target_type | TEXT | NOT NULL, CHECK (target_type IN ('post','comment','research','member')) — `'member'` covers suspend/reinstate actions (MOD-004/ADMIN-004), the other three cover content actions |
| target_id | UUID | NOT NULL — references `posts.id` / `comments.id` / `research.id` / `users.id` depending on `target_type`; no FK constraint possible across a polymorphic target (same accepted trade-off as `reactions`/`reports` — see AD-13) |
| action | TEXT | NOT NULL, CHECK (action IN ('approve','edit','restrict','remove','reinstate','suspend_member','reinstate_member')) — the full MOD-002 action vocabulary plus explicit reversal actions (`reinstate`, `reinstate_member`) needed for a moderator to undo a Restrict/Remove/Suspend |
| report_id | UUID | NULL, FK → reports.id — set when the action was taken in response to a specific report; NULL for proactive moderator action not tied to a report |
| previous_state | TEXT | NULL — the target's `status`/`moderation_status` (or `users.status` for member actions) immediately before this action |
| new_state | TEXT | NOT NULL — the target's `status`/`moderation_status` (or `users.status`) immediately after this action |
| reason | TEXT | NULL — moderator's stated reason, shown to the content author where applicable |
| metadata | JSONB | NULL — action-specific detail (e.g., which fields were changed for an `edit` action) |
| created_at | TIMESTAMPTZ | NOT NULL |

No `updated_at`, no `deleted_at` — append-only by design, identical rationale to `audit_logs` (AUDIT-003). Every write to `moderation_actions` happens in the same DB transaction as the corresponding update to the target's `status`/`moderation_status` column and the corresponding `audit_logs` write, per Section 10.1 — a moderation action, its effect on content state, and its audit trail entry are always atomic, never eventually-consistent.

Indexes: `(target_type, target_id)` for "moderation history of this item," `(moderator_id)` for "actions taken by this moderator," `(report_id)` for tracing a report to its resolving action.

#### `bookmarks`
Purpose: personal saved-posts list (COMM-006, SHOULD-HAVE). Added in this correction pass — previously specified in the PRD but missing from the table specification.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL |
| post_id | UUID | FK → posts.id, NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(user_id, post_id)` — prevents duplicate bookmarks of the same post by the same member. Index on `(user_id, created_at DESC)` for the "my saved posts" list view. Owned by the `community` module (Section 4.2); exposed as `GET /api/v1/community/bookmarks` (add) / `DELETE /api/v1/community/bookmarks/{post_id}` (remove) at the API-spec phase — Core-gated per MEM-003 (bookmarking is a community interaction, gated the same as posting/commenting). No bookmarking of comments or research items in MVP — COMM-006 scopes this to posts only; extending to other content types is a future, additive change if requested.

#### `moderation_rules`
Purpose: admin-configurable flagged-phrase table (OD-08, MOD-003). **Signal only — never an automatic legal classifier.**

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| phrase | TEXT | NOT NULL |
| severity | TEXT | NOT NULL, CHECK (severity IN ('low','medium','high')) |
| enabled | BOOLEAN | NOT NULL DEFAULT true |
| action | TEXT | NOT NULL, CHECK (action = 'flag_for_review') — MVP locks this to review-only; no other action value is permitted, enforcing CMPL-003/MOD-003 at the schema level, not just in application logic |
| created_by | UUID | FK → users.id, NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

The `action` CHECK constraint is a deliberate architectural safeguard: even a future code change cannot silently introduce an "auto-remove" or "auto-block" action without an explicit schema migration and PRD amendment.

#### `companies`
Purpose: static company metadata, listed companies only (CO-001, OD-23).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NOT NULL |
| exchange | TEXT | NOT NULL, CHECK (exchange IN ('NSE','BSE','OTHER_RECOGNIZED')) — enforces listed-only scope at schema level |
| sector | TEXT | NULL |
| industry | TEXT | NULL |
| website | TEXT | NULL |
| description | TEXT | NULL |
| is_merged_into | UUID | NULL, FK → companies.id — set when an ADMIN merges a duplicate (CO-004); the merged (losing) record is archived, not deleted |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |
| deleted_at | TIMESTAMPTZ | NULL (archival, not hard delete) |

Indexes: `GIN (to_tsvector('english', name))` for name search/dedup warnings (ERR-001), UNIQUE-ish trigram or exact-match index for duplicate detection (implementation detail — `pg_trgm` extension candidate, noted as an assumption in Section 16).

#### `research`
Purpose: current-state pointer for a research item, including embedded Q-RESEARCH fields (RES-*, QRES-*, DB-002).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| author_id | UUID | FK → users.id, NOT NULL |
| company_id | UUID | FK → companies.id, NOT NULL |
| research_type | TEXT | NOT NULL |
| industry | TEXT | NULL |
| status | TEXT | NOT NULL, CHECK (status IN ('draft','published')), DEFAULT 'draft' — this is the *authoring lifecycle* state only (draft vs. published), separate from moderation state below |
| moderation_status | TEXT | NOT NULL, CHECK (moderation_status IN ('active','restricted','removed')), DEFAULT 'active' — the *moderation* state, independent of authoring `status`; see Section 10.1. `'active'` = normal visibility per tier gating; `'restricted'` = hidden from public/other members, visible to author and MODERATOR+; `'removed'` = hidden from everyone, retained for audit (never hard-deleted) |
| access_tier | TEXT | NOT NULL, CHECK (access_tier IN ('core','free_example')), DEFAULT 'core' (Amendment 2026-08-29, AD-18) — the *access-classification* dimension, independent of both `status` and `moderation_status`. `'core'` = ordinary Core-only research (LIB-003 paywalled-preview rule applies to FREE members). `'free_example'` = editorially curated research that FREE members may access **in full**, per MEM-004 ("selected research examples (curated, not the full library)"). This is the authoritative field the API serializer/tier-gating logic reads to decide preview-vs-full-content for a FREE caller — see §7.1.2/§7.4.1/§7.4.2 (as amended). Defaulting to `'core'` means every existing and future row keeps today's behavior unless explicitly curated otherwise. This field governs access-tier only and has no bearing on `status`/`moderation_status`/publication eligibility — a `free_example` item that is still `status='draft'` or `moderation_status != 'active'` remains invisible to everyone under the existing rules, exactly as a `core` item would. **Who may change this field (Amendment 2026-08-29, Founder Decision #2, AD-19): ADMIN and SUPER_ADMIN only.** AUTHOR (even the research item's own author), REVIEWER, and MODERATOR cannot set or change `access_tier` under any circumstance — this is an editorial curation decision, not a moderation action or an authoring privilege, and is enforced exclusively at the API/RBAC layer (§7.5 `PATCH /research/{id}/access-tier`, API Specification V1), since a CHECK constraint cannot express "which role" performed a write. |
| title | TEXT | NOT NULL, length 1–200 chars (Amendment 2026-08-29) — author-provided, required from creation; see note below |
| summary | TEXT | NOT NULL, length 1–500 chars (Amendment 2026-08-29) — author-provided; service layer defaults both `title`/`summary` to placeholder values at `POST /research` creation time so the `NOT NULL` constraint never blocks draft creation, with the author expected to supply real values before publish (added to the same publish-validation gate as `bear_case`/sources/disclosure, AD-04) |
| current_version | INTEGER | NOT NULL DEFAULT 0 — 0 until first publish |
| business_quality | TEXT | NULL (Q) |
| financial_snapshot | TEXT | NULL (R) |
| business_model | TEXT | NULL (E) |
| competitive_position | TEXT | NULL (S) |
| valuation_range | TEXT | NULL (E) |
| bull_case | TEXT | NULL |
| base_case | TEXT | NULL |
| bear_case | TEXT | NULL — QRES-003: bear case specifically required before publish (enforced in `service.py` publish validation, not a NOT NULL constraint, since drafts allow incomplete fields per RES-003) |
| risk_register | TEXT | NULL (R) |
| catalysts | TEXT | NULL (C) |
| invalidation_conditions | TEXT | NULL (H) |
| conflict_disclosed | BOOLEAN | NULL — explicit tri-state via nullability: NULL = unanswered, true/false = explicit answer (SRC-004) |
| conflict_detail | TEXT | NULL |
| position_disclosed | BOOLEAN | NULL |
| position_detail | TEXT | NULL |
| research_date | DATE | NULL |
| published_at | TIMESTAMPTZ | NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL |
| deleted_at | TIMESTAMPTZ | NULL |

Publish-time validation (RES-004, QRES-003, SRC-001, SRC-003) is enforced in `modules/research/service.py`, not solely via DB constraints, because drafts must allow partial data (RES-003) — a CHECK constraint would block valid drafts. This is a deliberate architecture decision (see Section 6 Decision Log entry AD-04). **Amendment 2026-08-29:** `title`/`summary` were added as `NOT NULL` columns after founder review of API Specification V1 found the API's own preview/library responses (LIB-003) already assumed these fields existed, with no defined source — see AD-16.

Indexes: `GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(business_model,'')))` — full text search index; this now correctly references an actual column (prior to Amendment 2026-08-29, this index expression already named `title` even though no such column was defined above it — an internal inconsistency in this document, now corrected alongside the column addition rather than left standing). `(company_id)`, `(status)` for library filtering.

#### `research_versions`
Purpose: immutable version snapshots (VER-001–004, DB-002).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| research_id | UUID | FK → research.id, NOT NULL |
| version_number | INTEGER | NOT NULL |
| snapshot | JSONB | NOT NULL — full snapshot of all Q-RESEARCH + thesis fields at publish/edit time |
| change_note | TEXT | NOT NULL — required "what changed/why" (VER-002) |
| edited_by | UUID | FK → users.id, NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(research_id, version_number)`. Rows are never updated or deleted after insert (immutability, VER-001).

#### `research_sources`
Purpose: citations (SRC-001–002).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| research_id | UUID | FK → research.id, NOT NULL |
| label | TEXT | NOT NULL |
| reference | TEXT | NOT NULL — URL or document/filing reference |
| supports_claim | TEXT | NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

At least one row required per `research_id` before publish (SRC-001) — enforced in service-layer publish validation, same rationale as above.

#### `research_tags`
Purpose: tagging for search/browse (LIB-002, LIB-004).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| research_id | UUID | FK → research.id, NOT NULL |
| tag | CITEXT | NOT NULL |

UNIQUE `(research_id, tag)`. A simple join-table design (Principle 8: avoids a separate `tags` master table until Phase 2 needs tag management UI).

#### `compliance_acknowledgments`
Purpose: evidence of CMPL-004 (Member Charter) and CMPL-005 (risk disclosure) acknowledgment, tied to a specific document version. Added 2026-08-29 (Amendment) after API Specification V1 review found neither Architecture V1 nor Database Schema V1 defined where these acknowledgments are stored, despite CMPL-004/005 being MUST-HAVE PRD requirements with clear behavior.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL |
| acknowledgment_type | TEXT | NOT NULL, CHECK (acknowledgment_type IN ('member_charter','risk_disclosure')) |
| document_version | TEXT | NOT NULL — which version of the Charter/risk-disclosure text was acknowledged |
| acknowledged_at | TIMESTAMPTZ | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

No `updated_at`/`deleted_at` — append-only, same discipline as `audit_logs`/`moderation_actions`/`events`: a fresh acknowledgment of a new `document_version` is a new row, never an update to an old one, so which version a user actually acknowledged is never lost even if the Charter/disclosure text changes later. `risk_disclosure` may have multiple rows per user, since CMPL-005 requires acknowledgment both at signup and again at first payment. Chosen over adding two nullable timestamp columns to `profiles` (the minimal alternative) because a dedicated table preserves *which version* was acknowledged — a materially stronger, more compliance-defensible guarantee than a bare timestamp, and keeps `profiles` from accumulating compliance-specific columns unrelated to its PROF-* purpose. Owned by the `users` module (Section 4.2). Indexes: `(user_id, acknowledgment_type, acknowledged_at DESC)`. Traceability: CMPL-004, CMPL-005. Source: this amendment — see AD-16.

#### `watchlists`
Purpose: container per member (WL-*).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL, UNIQUE — one watchlist per member in MVP |
| created_at | TIMESTAMPTZ | NOT NULL |

#### `watchlist_items`
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| watchlist_id | UUID | FK → watchlists.id, NOT NULL |
| company_id | UUID | FK → companies.id, NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

UNIQUE `(watchlist_id, company_id)`.

#### `notifications`
Purpose: in-app notifications (NOTIF-001/002).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL |
| type | TEXT | NOT NULL, CHECK (type IN ('comment_on_content','reaction_on_content','report_resolved','moderation_action','subscription_change')) |
| payload | JSONB | NOT NULL — event-specific data for rendering |
| read_at | TIMESTAMPTZ | NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

Index `(user_id, read_at)` for unread-count queries.

#### `audit_logs`
Purpose: append-only audit trail (AUDIT-001–003).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| actor_id | UUID | FK → users.id, NULL (system-initiated actions may have no human actor) |
| action_type | TEXT | NOT NULL |
| target_entity_type | TEXT | NOT NULL |
| target_entity_id | UUID | NOT NULL |
| before_state | JSONB | NULL |
| after_state | JSONB | NULL |
| reason | TEXT | NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

No `updated_at`, no `deleted_at` — this table is architecturally append-only. No application route or admin capability exposes UPDATE/DELETE on this table (AUDIT-003); this is enforced both by omission (no such endpoint exists) and, as defense-in-depth, by a database-level `REVOKE UPDATE, DELETE` on the application's runtime DB role.

#### `events`
Purpose: analytics/behavioral event log (ANLY-001–003, OD-09). Added in this correction pass to resolve the previously-flagged gap where Section 38's tracking requirements had no architectural representation — see Section 21 for the full design rationale.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK → users.id, NOT NULL — every ANLY-001 event type is a member-initiated action; there is no system/anonymous event in MVP scope |
| event_type | TEXT | NOT NULL, CHECK (event_type IN ('signup','email_verified','login','payment_completed','research_draft_created','research_draft_updated','research_section_completed','research_source_added','research_published','research_commented','post_created','watchlist_added')) — the 9 types explicitly named in ANLY-001, plus 3 additive types (`research_draft_updated`, `research_section_completed`, `research_source_added`) required to make OD-09's "meaningful research activity" set fully trackable (see Section 21.1) |
| entity_type | TEXT | NULL, CHECK (entity_type IS NULL OR entity_type IN ('research','post','comment','payment','subscription','watchlist_item')) — polymorphic reference to what the event relates to; NULL for events with no natural entity (`signup`, `email_verified`, `login`) |
| entity_id | UUID | NULL — paired with `entity_type`; no FK constraint possible across a polymorphic target (same accepted trade-off as `reactions`/`reports`/`moderation_actions` — see AD-13) |
| metadata | JSONB | NULL — small, non-PII structured detail only (e.g., which Q-RESEARCH section was completed for a `research_section_completed` event); never stores free-text content (comment/post bodies, research field values) redundantly — the `entity_id` is the pointer to that content if needed |
| created_at | TIMESTAMPTZ | NOT NULL |

No `updated_at`, no `deleted_at` — append-only by design, identical rationale to `audit_logs` and `moderation_actions`. Same DB-level `REVOKE UPDATE, DELETE` defense-in-depth applies.

Indexes: `(user_id, event_type, created_at)` for the per-member "meaningful activity this month" query (ANLY-002); `(event_type, created_at)` for admin time-windowed aggregate metrics (ANLY-003); a partial index `WHERE event_type IN ('research_draft_created','research_draft_updated','research_section_completed','research_source_added','research_published','research_commented')` specifically accelerates the OD-09 meaningful-activity computation, which is the single most frequently-run analytics query (once per paying member per success-criteria review, per Section 8).

#### `moderation_rules`
Purpose: admin-configurable flagged-phrase table (OD-08, MOD-003). **Signal only — never an automatic legal classifier.**

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| phrase | TEXT | NOT NULL |
| severity | TEXT | NOT NULL, CHECK (severity IN ('low','medium','high')) |
| enabled | BOOLEAN | NOT NULL DEFAULT true |
| action | TEXT | NOT NULL, CHECK (action = 'flag_for_review') — MVP locks this to review-only; no other action value is permitted, enforcing CMPL-003/MOD-003 at the schema level, not just in application logic |
| created_by | UUID | FK → users.id, NOT NULL |
| updated_at | TIMESTAMPTZ | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL |

The `action` CHECK constraint is a deliberate architectural safeguard: even a future code change cannot silently introduce an "auto-remove" or "auto-block" action without an explicit schema migration and PRD amendment.

### 5.4 Deferred (Not Created in MVP Migrations)

Per DB-001/OD-20 and explicit instruction, no schema work is done now for: `theses`, `thesis_updates`, `guilds`, `guild_members`, `guild_cycles`, `guild_reviews`, `courses`, `lessons`, `resources`, `organizations`. These are named here only so future sessions recognize them as intentionally deferred, not forgotten.

## 6. Architecture Decision Log

For every major decision: Decision / Reason / Alternatives considered / Trade-offs / Future migration path.

**AD-01 — Modular monolith over microservices**
- Decision: Single FastAPI deployable with internal module boundaries.
- Reason: MVP scale (Section 8 PRD success criteria: 50 users, 10 paying) does not justify service-per-domain operational overhead; PRD NFR-001 locks this explicitly.
- Alternatives considered: Microservices per module; serverless functions per endpoint.
- Trade-offs: Simpler ops, faster iteration, weaker hard isolation between modules (mitigated by code-level boundaries).
- Future migration path: If a specific module (e.g., `billing` or `research`) needs independent scaling, it can be extracted once real load data justifies it — module boundaries in Section 4.2 are designed to make this extraction mechanical rather than a rewrite.

**AD-02 — Role storage as `TEXT[]` on `profiles` rather than a normalized `user_roles` table**
- Decision: `profiles.role_grants TEXT[]`.
- Reason: Simplicity (Principle 1) for MVP's 6 fixed roles and low query complexity; still satisfies "additive set, not a single enum" (OD-05).
- Alternatives considered: Normalized `user_roles(user_id, role)` join table.
- Trade-offs: Array column is slightly harder to index/query at scale and doesn't support per-role metadata (e.g., "granted_by", "granted_at") without extending the array to a JSONB structure.
- Future migration path: If per-role audit metadata becomes necessary, migrate to a `user_roles` table (additive migration; `role_grants` array becomes derived/read-model during transition).

**AD-03 — Session architecture: HttpOnly server-side cookie, Redis-backed session store**
- Decision: Session ID in a secure HttpOnly cookie; session data (user id, issued_at) stored server-side in Redis with TTL, not a stateless JWT as the primary mechanism.
- Reason: OD-04 locks "secure, HttpOnly, server-side session/cookie architecture" and explicitly allows JWT only as an internal detail if used; a Redis-backed opaque session token gives simpler, immediate revocation (e.g., on suspension, password change) compared to JWT, which is valuable given MOD-004/ADMIN-004 (suspension must take effect promptly).
- Alternatives considered: Pure JWT (access+refresh) as described as a fallback option in OD-04.
- Trade-offs: Requires Redis availability for every authenticated request (mitigated — Redis is already an MVP dependency per NFR-004); simpler revocation semantics than JWT.
- Future migration path: If Redis-session lookups become a latency concern at scale, move to short-lived JWT access tokens (~15 min) with rotation, exactly as OD-04 allows, without changing the cookie-based transport.

**AD-04 — Publish-time validation lives in the service layer, not the database schema**
- Decision: Required-field validation for publishing research (RES-004, QRES-003, SRC-001, SRC-003) is application logic in `modules/research/service.py`.
- Reason: Drafts must allow incomplete fields (RES-003) — a DB-level NOT NULL/CHECK constraint on `research` columns would make saving a partial draft impossible.
- Alternatives considered: Two-table split (`research_drafts` vs `research_published`) to allow different constraint sets.
- Trade-offs: Slightly more responsibility placed on application code correctness/tests rather than being schema-guaranteed; mitigated by mandatory service-layer unit tests as an Architecture Definition of Done item.
- Future migration path: If publish-integrity bugs recur, consider a database-level trigger (`BEFORE UPDATE ... WHEN status = 'published'`) as an additional safety net, layered on top of (not replacing) the service-layer check.

**AD-05 — `moderation_rules.action` locked to a single value via CHECK constraint**
- Decision: `CHECK (action = 'flag_for_review')` rather than an open enum.
- Reason: CMPL-003/MOD-003 require flagged phrases to *never* auto-block/auto-remove/auto-classify content as unlawful — encoding this at the schema level, not just in application code, makes it materially harder to accidentally violate this compliance boundary in a future change.
- Alternatives considered: Open-ended `action TEXT` column trusted to application logic only.
- Trade-offs: Adding a genuinely new, still-compliant action type later requires a migration, not just a config change; considered an acceptable and intentional friction point given the compliance sensitivity.
- Future migration path: If Phase 2 introduces a richer moderation-action taxonomy (still human-review-based), extend the CHECK constraint's allowed set explicitly, with a corresponding PRD/architecture amendment — never silently.

**AD-06 — No separate `theses` table; Thesis fields embedded in `research`**
- Decision: Bull/base/bear, risk register, invalidation conditions are columns on `research`, not a related `theses` entity.
- Reason: PRD Section 23 explicitly resolves this ambiguity — "Thesis" is not a separate entity in MVP, it is the structured Q-RESEARCH research record itself.
- Alternatives considered: A `theses` table 1:1 with `research`.
- Trade-offs: Simpler joins/queries now; if Phase 2 introduces a genuinely separate lightweight thesis-tracking feature, that would be new modeling work rather than an extension.
- Future migration path: PRD's own OD-20/Section 47 already anticipates `theses`/`thesis_updates` as a possible Phase 2 backlog item if needed — deferred, not designed now.

**AD-07 — Background jobs via lightweight Redis-backed worker, not a message broker**
- Decision: Use Redis as both cache and job queue (via a library such as `arq`, chosen for being async-native and FastAPI-friendly) rather than introducing RabbitMQ/Kafka/Celery+broker.
- Reason: MVP job volume (email sends, webhook retries, notification fan-out) does not justify a dedicated message broker; Redis is already an MVP dependency (NFR-004).
- Alternatives considered: Celery + RabbitMQ; synchronous inline processing (no queue at all).
- Trade-offs: Synchronous processing would block request/response cycles on slow operations (e.g., sending email); a full broker is unjustified operational overhead at this scale.
- Future migration path: If job volume/complexity grows significantly (Phase 2 Guild notifications, reputation recalculation), evaluate Celery+broker at that time.

**AD-08 — Separate `moderation_actions` audit table, plus a `moderation_status` column independent of authoring `status`**
- Decision: Content moderation state (`active`/`restricted`/`removed`) is tracked on the content row itself (new `moderation_status` column on `research`; corrected `status` enum on `posts`/`comments`), while the moderator's action history lives in a new, separate `moderation_actions` table. `research.status` (draft/published) is left untouched as a purely authoring-lifecycle field.
- Reason: The original design tried to represent "what happened" (an action) and "what state is this in" (content visibility) in a single `status` column, and `research` had no moderation-relevant status field at all — flagged as a HIGH finding during architecture verification, since MOD-002 requires Restrict/Remove to be executable against research items specifically.
- Alternatives considered: (a) Cramming moderation state into `research.status` alongside draft/published — rejected, conflates two independent lifecycles (authoring vs. moderation) and would require an author to "republish" through a restricted state, which is wrong. (b) Relying solely on `reports.resolution_action` as the state record — rejected, `reports` describes a complaint's resolution, not an authoritative, replayable action log, and doesn't cover proactive (non-report-triggered) moderator actions.
- Trade-offs: One additional table and one additional column versus the original design; in exchange, moderation state is unambiguous, `research` gains real Restrict/Remove capability, and there's now a genuine audit trail distinguishable from `audit_logs` (which stays generic/cross-domain) for moderation specifically.
- Future migration path: If Phase 2 needs richer moderation workflows (e.g., Guild-based peer moderation), `moderation_actions.action` and `target_type` are both extensible via migration, following the same discipline as AD-05.

**AD-09 — `bookmarks` table added for COMM-006**
- Decision: Standalone `bookmarks(id, user_id, post_id, created_at)` table, owned by `community`.
- Reason: COMM-006 (SHOULD-HAVE) was present in the PRD but missing from the original table specification — flagged as a MEDIUM finding during verification. A simple join table is the minimal design satisfying the requirement without inventing scope beyond "bookmark a post."
- Alternatives considered: A `saved_by TEXT[]`/`UUID[]` array column on `posts` — rejected, makes "list my bookmarks" an expensive reverse-scan across all posts instead of an indexed lookup on `user_id`.
- Trade-offs: One small additional table; negligible complexity cost for a correct, queryable design.
- Future migration path: If Phase 2 wants to bookmark comments or research items too, add `target_type`/`target_id` polymorphic columns as an additive migration rather than redesigning now (Principle 8 — not speculatively building this in MVP).

**AD-10 — Member directory: built in MVP, no new table**
- Decision: The member directory (Section 11 SHOULD-HAVE list) is built as a read-only, derived view over existing `users`/`profiles`/`subscriptions` data — no new table.
- Reason: PRD Section 11 lists it as SHOULD-HAVE ("low complexity"), but MEM-003 (MUST-HAVE) separately lists "member directory" among the Core-gated features alongside private Community and the Research Workspace. Verification flagged this priority tension explicitly. Resolution: treat it as MVP-in per MEM-003's MUST-HAVE gating list, since MEM-003 is the more specific, more recently-scoped requirement and building the minimal read-only version is genuinely low-complexity (no schema change, a single query joining three already-existing tables).
- Alternatives considered: Deferring entirely to Phase 2 — rejected, would leave MEM-003's acceptance criteria (which lists "member directory" as a Core-gated feature) unsatisfied without an explicit PRD amendment, which this correction pass is not authorized to make.
- Design: `GET /api/v1/users/directory` (Core-gated per MEM-003) returns `profiles.name`, `profiles.username`, a derived badge/role label from `role_grants`, and `users.created_at` (join date) for all non-anonymized, non-suspended members. No new table; no write path. Privacy: only the fields already exposed on public profiles per PROF-005 are included — no email, no other private fields.
- Trade-offs: None material — this is a thin read endpoint over existing data.
- Future migration path: If Phase 2 wants filtering/search over the directory beyond simple pagination, add indexes to `profiles` as needed; no structural change anticipated.

**AD-11 — CSV export of a member's own research: built in MVP, synchronous, no new table**
- Decision: `GET /api/v1/research/export.csv` (authenticated, self-only) synchronously generates a CSV of the requesting member's own research items (title/company/status/dates/tags) from the existing `research`/`research_tags`/`companies` tables and streams it as a file download. No new table, no background job.
- Reason: PRD Section 11 lists this as SHOULD-HAVE, "low compliance risk," scoped explicitly to "a member's own research" (self-only, not admin/bulk export) — verification flagged its complete absence from the architecture as a MEDIUM finding, not because it was excluded on purpose but because it was silently dropped. Given the explicit "low complexity" framing in the PRD itself and realistic MVP data volumes (a single member's own research items, likely under a few hundred rows even at scale), synchronous generation is appropriate — no background job/queue is justified (Principle 8).
- Alternatives considered: Async export via the `arq` job queue with a download-ready notification — rejected for MVP as premature complexity for the realistic data volume; documented here as the natural future upgrade if row counts grow.
- Authorization: Self-only — a member can only export their own research; enforced by scoping the query to `research.author_id = current_user.id`, with no ADMIN bulk-export endpoint in MVP (not requested by the PRD).
- Security/privacy: The export includes only fields the member already owns/authored; no other members' data, no `research_sources`/citation URLs are excluded from the export (they're the member's own disclosed sources, not third-party private data).
- Trade-offs: None material for MVP scale; documented future path exists if needed.
- Future migration path: If export volume or frequency grows, move to the existing `arq` background-job mechanism (AD-07) with the file delivered via `ObjectStorageService` and a notification (NOTIF-001-style) when ready — additive change, not a redesign.

**AD-12 — REVIEWER badge computed from current `role_grants`, not frozen at comment-creation time**
- Decision: The "elevated visibility" badge on a REVIEWER's comment (PRD Section 30 note) is rendered at *read time* from the comment author's *current* `profiles.role_grants`, not stored as a flag on the `comments` row at creation time.
- Reason: PRD Section 30 describes this as a UI/display distinction only ("a labeled badge on their comment"), not a formal peer-review workflow gate (that's Phase 2 Guild peer review) — there is no PRD requirement that historical accuracy of past REVIEWER status be preserved. Current-role rendering is simpler (Principle 1): no new column, no risk of the badge going stale in the other direction (i.e., a newly-promoted REVIEWER's old comments would retroactively show the badge too, which seems like the more expected behavior for "is this person currently a trusted reviewer").
- Alternatives considered: Freezing `is_reviewer_comment BOOLEAN` on `comments` at creation time — rejected as unnecessary complexity given the PRD's own framing of this as a non-formal UI distinction; would also require a migration to add the column.
- Trade-offs: If a REVIEWER is later demoted, their past comments stop showing the badge retroactively — judged acceptable since the PRD doesn't ask for historical preservation and the badge's purpose (signal current trustworthiness) arguably favors current-state rendering anyway.
- Future migration path: If Phase 2's Guild peer-review workflow needs a frozen "reviewed-as-of" record, that's new modeling work at that time (likely on a `guild_reviews` table already in the deferred list, Section 5.4), not a retrofit of this MVP badge.

**AD-13 — Polymorphic `(target_type, target_id)` on `reactions`, `reports`, `moderation_actions` — accepted trade-off, now explicitly documented**
- Decision: Keep the polymorphic-target pattern (no FK constraint on `target_id`) for `reactions`, `reports`, and the new `moderation_actions` table.
- Reason: A single column can't carry an FK to more than one target table in PostgreSQL; the alternative (a separate reaction/report/action table per target type) multiplies table count for little benefit at MVP's target/content-type cardinality (2–4 types).
- Integrity risk: Without a DB-level FK, an application bug could insert a `target_id` that doesn't exist in the referenced table (an "orphaned" reaction/report/action). In practice this risk is low and bounded, since (a) all content in MVP is soft-deleted, never hard-deleted, so a `target_id` valid at insert time stays resolvable indefinitely, and (b) the only path to `target_id` is through application code that already loaded the target row (no user-supplied raw IDs are trusted without a prior existence check).
- Application-level validation: `service.py` functions in `community`/`moderation` validate the target exists and matches `target_type` before insert; this is a required unit-test case per the testing strategy (Section 16.2).
- Cleanup strategy: Not applicable in the usual sense, since nothing is hard-deleted; if a target row is ever hard-deleted in a future phase, an explicit cleanup migration/job would be required at that time — flagged here so it isn't forgotten if that assumption ever changes.
- Audit implications: `moderation_actions` rows referencing a target remain meaningful even if the target's own status later changes further, since `moderation_actions` stores its own `previous_state`/`new_state` snapshot rather than depending on a live join to reconstruct history.
- Recorded as an accepted architecture trade-off, consistent with how AD-01 through AD-12 document every other trade-off in this document, per verification finding.

**AD-14 — CSRF: double-submit-cookie pattern**
- Decision: See Section 13 (Security Architecture, CSRF row) for the full mechanism. Summarized here for decision-log completeness: a non-HttpOnly `csrf_token` cookie is set alongside the HttpOnly session cookie; the frontend echoes it as an `X-CSRF-Token` header on all mutating requests; the backend validates the match via a `require_csrf` dependency.
- Reason: OD-04 locks cookie-based session auth, which is inherently CSRF-exposed without a separate mitigation; this was flagged as a LOW-but-unresolved gap during verification ("requirement locked, mechanism not") and is resolved in this correction pass rather than left to the API-spec phase.
- Alternatives considered: Synchronizer token pattern (server-stored, per-form token) — rejected as more stateful/complex than necessary given the session is already server-side (Redis-backed, AD-03); a double-submit token piggybacks on that existing infrastructure with less additional state.
- Trade-offs: Double-submit-cookie is slightly weaker than a fully synchronizer-pattern token if an attacker can set cookies on the victim's browser via a separate vulnerability (e.g., a subdomain takeover) — judged an acceptable risk at MVP scale, standard practice for SPA+cookie-session architectures, and mitigated further by `SameSite=Lax` on both cookies.
- Future migration path: If a subdomain-cookie-injection risk becomes concrete (e.g., QFinance adds untrusted subdomains), move to per-request synchronizer tokens stored server-side in the existing Redis session.

**AD-15 — Analytics/event tracking: a single `events` table, PostgreSQL-only, no third-party analytics platform**
- Decision: All ANLY-001 event types (plus 3 additive types needed to fully cover OD-09) are written to one append-only `events` table in the same PostgreSQL database (Section 5.3), written synchronously in the same DB transaction as the underlying state-changing action. No external analytics platform (Mixpanel/PostHog/Amplitude/Segment/etc.), no separate analytics database, and no ETL pipeline are introduced.
- Reason: This gap was flagged as HIGH during the first correction-pass verification — Section 38 (ANLY-001–003, MUST-HAVE) and OD-09's "meaningful research activity" success metric (Section 8) had no architectural representation at all. Explicit founder instruction for this second correction pass requires resolving it while (a) not introducing a third-party analytics platform unless the PRD requires one (it doesn't — ANLY-001–003 only require that events be "tracked" and that admin metrics be computable from them, both satisfiable in Postgres), (b) preferring PostgreSQL-based tracking for MVP if sufficient (it is, at the stated MVP scale of <500 paid members, per Section 16.1's existing performance framing), and (c) avoiding premature analytics infrastructure (Principle 8).
- Alternatives considered: (i) A third-party product-analytics SaaS (PostHog, Mixpanel) — rejected as premature infrastructure and an unnecessary new vendor/data-processor relationship for MVP scale, and not required by any locked PRD requirement. (ii) Deriving "meaningful research activity" purely from existing entity tables (e.g., `research_versions.created_at`, `research_sources.created_at`) without a dedicated `events` table — rejected because ANLY-001 explicitly requires *tracking distinct events* including some with no natural row of their own (`login`, `signup`, `email_verified`), so a dedicated event log is required regardless; once it exists, it is also the natural home for the research-related events, avoiding two different mechanisms for adjacent requirements. (iii) A generic, schema-flexible "analytics platform" table design (arbitrary event names, no CHECK constraint) — rejected per explicit instruction not to build a generic analytics platform; the `event_type` CHECK constraint locks the table to exactly the events this PRD asks for, the same discipline already applied to `moderation_rules.action` (AD-05).
- Trade-offs: One additional table and one additional module (`analytics`); every module that triggers a tracked action (`auth`, `membership`/`billing`, `research`, `community`) gains one additional responsibility (write an `events` row) alongside its existing domain writes and its existing `audit_logs`/`notifications` writes where applicable — judged a small, well-precedented addition (this is the fourth append-only log table in the architecture, alongside `audit_logs`, `moderation_actions`, and now `events`, all following the same pattern).
- Future migration path: See Section 21.6.

**AD-16 — `research.title`/`research.summary` stored, not derived; `compliance_acknowledgments` as a dedicated table**
- Decision: `research` gains two required (`NOT NULL`) author-provided columns, `title` and `summary`. CMPL-004/CMPL-005 acknowledgment evidence is stored in a new, dedicated `compliance_acknowledgments` table rather than as two nullable timestamp columns on `profiles`.
- Reason: Founder review of API Specification V1 (2026-08-29) found the API's own preview/library responses (LIB-003) already assumed `title`/`summary` fields existed on `research` — with no defined source anywhere in Architecture or Database Schema V1 — and the API spec's own §12 self-flagged the missing acknowledgment-storage location. The PRD treats title as a displayed, author-defined research-item field (not something the system derives from company name + research type), so a stored column is the correct contract rather than inventing a derivation rule the PRD never specified.
- Alternatives considered: (a) Deriving `title` from `company.name` + `research_type` at read time — rejected, removes author control and isn't what the PRD describes. (b) Truncating `business_model` or another existing field for `summary` — rejected, silently repurposes a field for a different display purpose the author didn't write it for. (c) Two nullable timestamp columns on `profiles` for compliance acknowledgment — rejected in favor of a dedicated table, since a bare timestamp can't record *which version* of the Charter/disclosure text was acknowledged, a materially weaker compliance guarantee.
- Trade-offs: Two new `NOT NULL` columns on an already-large `research` table, plus one new table; both are additive (DB-001-compliant) and address gaps that existed in the document from the start (the FTS index already silently referenced a non-existent `title` column — see the `research` table note), not scope creep.
- Future migration path: None anticipated — both are now permanent, minimal parts of the schema.

**AD-17 — Published-research editing requires full re-validation, not just a change note**
- Decision: `PATCH` on an already-published `research` item must pass the same publish-validation gate as the original publish action (AD-04) before the edit commits; a failed validation leaves the currently-published version completely unchanged.
- Reason: The original design (a `change_note`-only requirement for published edits) allowed an author to remove or blank a required field (e.g., `bear_case`, a disclosure answer) on a live, published item without re-checking CMPL-001's requirements — identified during founder review of API Specification V1 as a genuine compliance-relevant gap, not a hypothetical one.
- Alternatives considered: (a) Leaving published edits unvalidated, relying only on the original publish-time check — rejected, this is exactly the gap being fixed. (b) Disallowing edits to published research entirely, requiring un-publish-then-republish — rejected as worse UX for a routine workflow (research naturally needs updating) and not requested by the PRD.
- Trade-offs: Slightly more friction for authors editing published research (a field they blank must be re-filled, or the edit is rejected) — judged correct given the compliance stakes; the same trade-off AD-04 already accepted for the original publish action, now applied consistently to every subsequent edit of published content.
- Future migration path: None anticipated; this closes the gap rather than deferring it.

**AD-19 — Authorization for `research.access_tier` changes: ADMIN/SUPER_ADMIN only, no new role, audited via existing `audit_logs`**
- Decision: Only ADMIN and SUPER_ADMIN may change `research.access_tier`. SUPER_ADMIN's capability is inherited automatically under the existing additive RBAC model (Architecture §8/AD-02) — no new role, capability flag, or grant mechanism is introduced. AUTHOR (including the research item's own author), REVIEWER, and MODERATOR are explicitly denied — this is not an authoring privilege and not a moderation action. Every change is recorded in the existing `audit_logs` table (Database Schema §22); no new audit table or column is introduced.
- Reason: Founder Decision #2 (2026-08-29) resolves the authorization question AD-18 explicitly deferred. `access_tier` represents editorial curation of the research library (which items represent QFinance to a prospective FREE-tier member), not a moderation judgment about content quality/compliance (that remains `moderation_status`, AD-08) and not an authoring choice (an author cannot self-designate their own work as a curated showcase example — verified as a required behavior, not merely a default).
- Why `audit_logs` and not `moderation_actions`: `moderation_actions.action` is a CHECK-constrained enum (`approve`/`edit`/`restrict`/`remove`/`reinstate`/`suspend_member`/`reinstate_member`, Database Schema §16) representing MOD-002's specific moderation vocabulary — adding an `access_tier` change to it would require widening that CHECK constraint for an action that is not a moderation action, which would blur the state model AD-08 deliberately kept clean (moderation state vs. editorial classification are different dimensions, per AD-18). `audit_logs.action_type` is a free `TEXT` column with no such constraint, and its `actor_id`/`target_entity_type`/`target_entity_id`/`before_state`/`after_state`/`created_at` columns already capture exactly the required record (who, which item, previous value, new value, when) with zero schema changes — confirmed by direct inspection of Database Schema V1 §22 before this decision was finalized, per the project's standing verify-before-amend discipline.
- Alternatives considered: (a) Extending `moderation_actions.action` with a new `change_access_tier` value — rejected per the reasoning above (wrong table for a non-moderation action). (b) A new dedicated `access_tier` audit table — rejected as unnecessary; `audit_logs` already generically supports this without modification, and creating a redundant table would violate Principle 8 (avoidance of premature infrastructure) for no added capability. (c) Allowing REVIEWER to curate (since REVIEWER already has elevated trust for comment badging, AD-12) — rejected; REVIEWER's elevated trust is a community-visibility signal (AD-12), not an editorial-authority grant, and the founder's explicit instruction restricts this to ADMIN/SUPER_ADMIN only.
- Trade-offs: None material — this is an RBAC/API-layer rule plus reuse of existing infrastructure, not a schema or architectural change beyond the already-approved AD-18 column.
- Future migration path: If a Phase 2 curation workflow needs richer state (e.g., a curation request/approval queue, multiple curators with different scopes), that would be new modeling work at that time, not a retrofit of this MVP rule.

## 6A. Research Access Classification — Authorization Summary (Amendment 2026-08-29, Founder Decision #2)

```text
ADMIN        → may change research.access_tier
SUPER_ADMIN  → may change research.access_tier (inherits via existing additive RBAC model, AD-02 — no new role)
AUTHOR       → cannot change access_tier (including on their own research)
REVIEWER     → cannot change access_tier
MODERATOR    → cannot change access_tier
```

A change to `access_tier`:
- requires ADMIN or SUPER_ADMIN authorization (enforced at the API/RBAC layer, §7.5 API Specification V1);
- is recorded in `audit_logs` (existing table, no schema change — AD-19);
- never automatically publishes research (`status` is untouched);
- never bypasses or is bypassed by `status`/`moderation_status` (the three dimensions remain fully independent, per AD-18's original framing);
- never allows an author to self-designate their own research as `free_example` (RBAC-enforced denial, not merely an unexercised default);
- introduces no new role (SUPER_ADMIN inherits ADMIN's capability under the existing additive model, exactly as every other ADMIN-level capability already works, Architecture §8).

## 7. Authentication & Session Architecture

- Registration/login/logout/reset per AUTH-001–005.
- Password policy: Argon2id hashing, 12-character minimum, no forced composition rules (AUTH-006/OD-03).
- Rate limiting: login attempts throttled per account and per IP using Redis counters with a sliding window (AUTH-007).
- Breached-password check (AUTH-009, SHOULD): optional integration with a k-anonymity breach-check API (e.g., HaveIBeenPwned range API) at registration/reset time — warns, does not block.
- Session: see AD-03. Session cookie attributes: `HttpOnly; Secure; SameSite=Lax; Path=/`. No auth data in `localStorage`/`sessionStorage` (AUTH-008) — verified as part of Architecture Definition of Done via a manual/automated browser-storage check.
- Email verification gate: unverified accounts are blocked from Community/Research Workspace routes both in the frontend route guard (UX) and in the backend dependency `deps.require_verified_email` (actual enforcement, AUTH-002).

## 8. RBAC & Permission Enforcement

- `deps.py` exposes a generic `require_role(*roles)` FastAPI dependency, used to decorate every protected route.
- Role checks read from `profiles.role_grants` fetched fresh per request (or from the Redis session cache, invalidated on role change) — never trust a role claim baked into a long-lived client-held token (consistent with AD-03's revocation-friendly design; a role change should apply on the user's next request without requiring re-login, per RBAC-002).
- The full capability matrix from PRD Section 30 is mirrored as a static permissions table in `core/permissions.py` (`ROLE_CAPABILITIES: dict[str, set[Capability]]`), so route-level checks are declarative (`require_capability("moderation.take_action")`) rather than scattered ad hoc role-name comparisons — this centralizes the matrix in one place, making it easy to audit against PRD Section 30 for drift.
- Every protected endpoint has an automated test asserting a 403 for roles lacking the capability (RBAC-001 acceptance criterion) — tracked as an Architecture Definition of Done / testing requirement (Section 13).

## 9. Membership, Billing & Payments

- `membership` module computes a user's *effective* tier from `subscriptions.status` + `grace_period_ends_at`, never trusting a cached/denormalized "tier" field as the source of truth for access decisions (though a denormalized `effective_tier` may be cached in Redis for read performance, with the `subscriptions` table remaining authoritative).
- Payment flow: `PaymentService.create_subscription()` → Razorpay checkout → webhook confirms → `billing.service` updates `subscriptions`/`payments`/`invoices` inside a single DB transaction, using `payments.gateway_reference_id` UNIQUE constraint for webhook idempotency (ERR-003, PAY-002/003).
- Webhook endpoint (`/api/v1/webhooks/razorpay`) is exempt from CSRF (server-to-server, not a browser form) but requires signature verification via `PaymentService.verify_webhook_signature()` before any state change — no webhook payload is trusted unverified.
- Grace period (MEM-006/OD-06): a scheduled job (daily) checks `subscriptions` with `status = 'past_due'` and `grace_period_ends_at < now()`, downgrades to FREE tier, retains all content (no cascading delete — this is enforced by never having a delete-on-downgrade code path, and by FK `ON DELETE RESTRICT` defaults preventing accidental cascade).
- Cancellation (MEM-007): sets `subscriptions.status = 'canceled'`, `canceled_at`, leaves `current_period_end` untouched — access remains until period end, computed at read time, not by an immediate access-revocation job.
- `BillingService`/`TaxService`/`InvoiceService` per AD in Section 4.4 — `TaxService` is the only code path permitted to compute `invoices.tax_paise`.

## 10. Community, Moderation & Research Workspace

- Community and Research modules communicate only via the `posts.research_id` nullable FK (OD-14) — no separate discussion engine exists or is planned for MVP.
- Flagged-phrase detection (MOD-003) runs synchronously at content-submission time (post/research publish) against enabled `moderation_rules`, purely as a **matcher that creates a `reports`-equivalent moderation-queue entry** — it never blocks, alters, or removes the content itself. Content is saved/published normally regardless of a match; only a review-queue entry is added.
- Research Workspace: Q-RESEARCH fields are individually-saved sections (QRES-001/002) — the frontend editor auto-saves each section independently (debounced) rather than requiring a single "Save" for the whole form, matching "each stage is a distinct, individually-saved field/section."
- Versioning (VER-001–004): every publish or post-publish edit calls `research.service.create_version_snapshot()`, which inserts an immutable `research_versions` row and requires a non-empty `change_note` parameter — the API layer rejects the request with a 422 if `change_note` is empty, before any snapshot is written.
- **Published-content editing (Amendment 2026-08-29, AD-17):** editing an already-published research item's fields is allowed, but the edit must pass the **same full publish-validation gate** (`bear_case` non-empty, ≥1 source, `conflict_disclosed`/`position_disclosed` both answered, `title`/`summary` non-placeholder — AD-04's existing service-layer check) before it commits. If validation fails, the request is rejected and **the currently-published version is left completely untouched** — no partial write, no field-level change applied, no new `research_versions` row inserted. Only on successful validation does the edit apply atomically together with the version-increment and snapshot insert described above. This closes a gap where a published item could previously have its compliance-relevant fields (e.g., `bear_case`, disclosure answers) edited down to an incomplete state without re-validation, silently violating CMPL-001 on content already live to members.

### 10.1 Moderation State Model (corrected)

This subsection replaces the earlier single-paragraph description of the Report → Queue → Action flow with an explicit state model, added to resolve the moderation action/content-status mismatch identified during architecture verification. It also resolves the previously-flagged gap where `research` had no field capable of representing a moderator Restrict/Remove action.

**Two separate concerns, deliberately not conflated in one column:**

1. **Content moderation state** — a `moderation_status` (or, for `posts`/`comments`, `status`) column on the content row itself, answering "what does this content look like right now." Values: `active`/`visible`, `restricted`, `removed`. This is what the frontend reads to decide what to render.
2. **Moderation action history** — the `moderation_actions` table (Section 5.3), answering "what actions were taken, by whom, why, and when." This is the audit trail; it is never queried to determine current visibility (that's always the content row's own status column, to avoid "replay the log to know the current state" complexity).

**State transitions per content type:**

| Content type | States (moderation_status / status) | Notes |
|---|---|---|
| `posts` / `comments` | `visible` → `restricted` → `removed` (and reverse, via `reinstate`) | Author-initiated soft-delete (PCR-002) also lands on `removed`, distinguished in `moderation_actions` by whether `moderator_id` is the author themself acting via a self-delete endpoint vs. a MODERATOR acting via the moderation queue — both paths write a `moderation_actions` row for auditability, but only moderator-initiated `remove` actions are reportable/reversible via the moderation queue. |
| `research` | `moderation_status`: `active` → `restricted` → `removed` (independent of the existing `status`: `draft`/`published`) | A published research item can simultaneously be `status='published'` and `moderation_status='restricted'` — the two dimensions are orthogonal. Rendering logic checks both: content is only shown if `status='published' AND moderation_status='active'` (subject to tier gating). |
| `users` (member suspension) | `status`: `active` → `suspended` (and reverse, via `reinstate_member`) | Uses the existing `users.status` CHECK (already includes `'suspended'`, unchanged by this correction) — no new column needed here, only the corresponding `moderation_actions` row. |

**Action → state-transition mapping (MOD-002):**

| Moderator action | Effect on content/member row | `moderation_actions.action` value |
|---|---|---|
| Approve (dismiss report) | No change to content state | `approve` |
| Edit | Content updated in place (post/comment content, or a research field) via the normal author-equivalent update path; `is_edited` set | `edit` |
| Restrict | `status`/`moderation_status` → `restricted` | `restrict` |
| Remove | `status`/`moderation_status` → `removed` | `remove` |
| (Reverse a Restrict/Remove) | `status`/`moderation_status` → `active`/`visible` | `reinstate` |
| Suspend member | `users.status` → `suspended` | `suspend_member` |
| (Reinstate member) | `users.status` → `active` | `reinstate_member` |

**Transactional flow (MOD-001/002, AUDIT-001):** Report → Moderation Queue → Action is implemented as: `reports` row created (target_type includes `'research'`) → `moderation` module's queue view (read from `reports WHERE status = 'open'`) → MODERATOR/ADMIN selects an action → in a **single DB transaction**: (a) the target's `status`/`moderation_status`/`users.status` column is updated, (b) a `moderation_actions` row is inserted capturing `previous_state`/`new_state`/`actor`/`reason`/`target`, (c) `reports.resolution_action`/`resolved_by`/`resolved_at`/`status='resolved'` is updated if the action was report-triggered, and (d) an `audit_logs` entry is written (AUDIT-001 requires this before the success response is returned). All four writes commit together or not at all — there is no path where content state changes without a corresponding `moderation_actions` and `audit_logs` entry, and no path where a moderation action is logged without the content state actually changing to match.

## 11. Search

- PostgreSQL full-text search only (NFR-006/SEARCH-001): `tsvector` generated columns (or a maintained trigger) on `research` (title/body-ish fields) and `companies.name`, indexed with `GIN`.
- Search results respect tier gating (SEARCH-002): the search query itself does not filter by tier; the *response serializer* decides whether to return full content or a paywalled preview based on the requesting user's effective tier, keeping the gating logic in one place (consistent with how LIB-003 previews work generally) rather than duplicating it into the search query.
- Performance target ~1s at MVP scale (PERF-002/SEARCH-003) — achievable with `GIN` indexes at MVP data volumes without additional infrastructure; revisit only if real usage data shows otherwise (Principle 8).

## 12. API Architecture

- RESTful JSON, versioned under `/api/v1/...` (API-001).
- All mutating endpoints require authentication except registration, login, password-reset request (API-002).
- Every route function depends on the shared RBAC dependency chain from Section 8 (API-003).
- Payment webhooks live under a distinct, unauthenticated-by-session-but-signature-verified path (`/api/v1/webhooks/...`), separate from user-facing endpoints (API-004).
- Structured error format (API-005): every error response follows `{ "error": { "code": "...", "message": "...", "fields": {...} } }`, implemented via a single FastAPI exception handler (`core/errors.py`) so individual routes never hand-roll error bodies — this also satisfies STATE-003 ("raw exception text never shown to the user").
- Endpoint-level specification (exact paths/payloads per module) is explicitly **not** part of this document — per the PRD, that is a separate Architecture-phase deliverable (API spec), noted as Pending Work in `work_memory.md` Section 16.

## 13. Security Architecture

| Concern | Approach |
|---|---|
| Transport | HTTPS/TLS everywhere (SEC-001); HSTS enabled at the edge/load balancer. |
| Password storage | Argon2id (SEC-002/OD-03), never logged (verified via a logging-redaction test as part of DoD). |
| RBAC | Server-side only, on every protected endpoint (SEC-003, Section 8). |
| Input validation | Pydantic v2 schemas on every request body; output encoding handled by React/Next.js's default escaping to prevent XSS (SEC-004); no raw HTML rendering of user content without sanitization if rich text is ever introduced (MVP content is plain text/Markdown-lite, not raw HTML). |
| SQL injection | SQLAlchemy parameterized queries exclusively; no raw string-interpolated SQL anywhere in the codebase (enforced via code review checklist + linter rule where feasible). |
| Rate limiting | Redis-backed sliding-window limiter on `/auth/*` and `/webhooks/*` and payment-initiation endpoints (SEC-005). |
| CSRF | **Resolved in this correction pass (was previously an open question).** Double-submit-cookie pattern: on session creation, the server also sets a second, non-HttpOnly cookie (`csrf_token`, `Secure; SameSite=Lax`) containing a random value tied to the session. The frontend's typed API client (`apps/web/lib/api-client.ts`, Section 4.3) reads this cookie and echoes it on every mutating request (`POST`/`PUT`/`PATCH`/`DELETE`) as a custom header, `X-CSRF-Token`. The backend rejects any mutating request where the header value doesn't match the session's stored CSRF token (`core/deps.py`, a `require_csrf` dependency applied to all mutating routes alongside RBAC). `SameSite=Lax` on both cookies is defense-in-depth, not the sole control, since `Lax` still permits some cross-site top-level navigations. Read-only (`GET`) endpoints are exempt, since CSRF only matters for state-changing requests. Payment webhooks (`/api/v1/webhooks/*`) are exempt from this mechanism entirely — they carry no session cookie and are instead verified via `PaymentService.verify_webhook_signature()` (Section 9), a separate and stronger guarantee than CSRF tokens are designed to provide. |
| File-upload security | Not applicable to MVP application flows (no avatar upload, OD-21) beyond any future admin-side content needs; `ObjectStorageService` is provisioned with server-side validation (MIME-type/size checks) as a standing requirement for whenever it is first used, even though MVP may not exercise it. |
| Secrets management | Environment variables injected via the deployment platform's secret store (e.g., AWS Secrets Manager or platform-native equivalent) — never committed to the repository; `.env.example` documents required keys without values. |
| Step-up verification | Admin/SUPER_ADMIN sensitive actions (role escalation, pricing change) require re-authentication (password re-entry) before the action executes (SEC-007). |
| Dependency scanning | CI runs a dependency/vulnerability scan (e.g., `pip-audit`, `npm audit`) on every build (SEC-008). |

## 14. Privacy & Data Lifecycle

- Minimum necessary data collected (PRIV-001) — no raw card data ever touches QFinance servers or database (payment data comes from Razorpay as tokens/references only).
- Account deletion (PRIV-003/OD-17): `users.status = 'deleted'`, `is_anonymized = true`, `profiles.name`/`bio`/`interests` overwritten with anonymized placeholders, `email` replaced with a non-reusable anonymized value, login disabled — but `research`, `research_versions`, `posts`, and `audit_logs` authored by that user are **retained**, now attributed to the anonymized identity, per the explicit requirement that platform-integrity content is not deleted. Exact retention period for these records remains pending legal/privacy review (OD-17) — the architecture supports retention indefinitely by default until that review sets a concrete period, at which point a scheduled purge job (not yet built) would be added.
- Data residency: default deployment region `ap-south-1` (PRIV-004/OD-18) — documented here strictly as an infrastructure preference. No product or marketing copy claim of legal data-residency compliance is authorized by this architecture; that determination remains with counsel.

## 15. Logging, Monitoring, Backups, Disaster Recovery

- **Logging:** structured JSON application logs (request id, user id where authenticated, route, status, latency); passwords, tokens, and full payment payloads are explicitly excluded from log output (redaction list maintained in `core/security.py`).
- **Monitoring:** basic uptime/error-rate monitoring (e.g., platform-native APM or a lightweight external service) — no bespoke observability stack built for MVP (Principle 8: avoid premature infrastructure); Sentry-equivalent error tracking is a reasonable SHOULD-have addition, not a MUST for MVP launch.
- **Backups:** PostgreSQL automated daily backups with point-in-time recovery enabled (standard managed-Postgres feature, e.g., RDS automated backups) — retention period set operationally, not specified as a product requirement in the PRD, so a conservative default (7–14 days) is used pending explicit input.
- **Disaster recovery:** single-region deployment for MVP (consistent with "no premature infrastructure"); RDS/managed-Postgres automated backups + infrastructure-as-code (Section 8's Docker/IaC approach) together allow environment rebuild from source + latest backup. Multi-region failover is explicitly out of scope for MVP.

## 16. Performance, Scalability, Testing, CI/CD

### 16.1 Performance & Scalability
- Targets per PRD Section 43 (PERF-001–003) are directional, not contractual, and sized for <500 paid members. No horizontal-scaling infrastructure (load balancer fleet, read replicas) is provisioned proactively — the modular monolith runs as a small number of container replicas behind a load balancer, scaled manually/simply if needed.
- Admin metrics computed via direct real-time queries by default (OD-19/ADMIN-007); only a specific metric proven too slow as a direct query moves to Redis-backed scheduled aggregation — this is an exception path, implemented per-metric, not a blanket batch-analytics system.

### 16.2 Testing Strategy
- Unit tests: business logic in each module's `service.py`, testable without hitting Postgres/Redis where feasible (mocked repositories/adapters).
- Integration tests: route-level tests against a real (test) Postgres instance and Redis instance, run in CI via Docker Compose test services.
- RBAC tests: for every capability in the Section 30 matrix, at least one test asserting the correct 200/403 outcome per role (explicit DoD item).
- Compliance-critical tests: publish-validation (RES-004/QRES-003/SRC-001/003), moderation-rule signal-only behavior (MOD-003/CMPL-003), audit-log-on-every-moderation-action (AUDIT-001/002), and payment-webhook idempotency (ERR-003) are treated as **must-have automated tests**, not optional coverage, given their compliance/financial sensitivity.

### 16.3 CI/CD
- CI pipeline (GitHub Actions or equivalent): lint (ruff/eslint) → type-check (mypy/tsc) → unit tests → integration tests (Docker Compose services) → dependency/vulnerability scan (SEC-008) → build Docker images.
- CD: manual or tag-triggered deploy to staging; manual promotion to production (no automatic production deploys in MVP — a deliberate simplicity/safety choice given payment and compliance sensitivity).

### 16.4 Docker Strategy
- `docker-compose.yml` at repo root defines local dev services: `api` (FastAPI, hot-reload), `web` (Next.js, hot-reload), `postgres`, `redis`. No production orchestration platform (Kubernetes) is introduced for MVP — a simple container host (e.g., a single managed container service or VM running the two app images + managed Postgres/Redis) is sufficient at this scale (Principle 8).
- Staging mirrors production topology at smaller instance sizes; both are distinct from local Docker Compose, which is dev-only.

## 17. Architecture Risks, Assumptions, Open Questions

### Architecture Risks
- **Compliance boundary risk:** the `moderation_rules.action` CHECK constraint (AD-05) and service-layer-only publish validation (AD-04) are strong safeguards but not infallible — a future migration could still weaken them if not reviewed against this document. Mitigation: any schema change touching `moderation_rules` or `research` publish logic should be checked against Sections 5.3/10 before merge.
- **Session/Redis coupling risk (AD-03):** making Redis load-bearing for every authenticated request (not just cache) means a Redis outage becomes an auth outage. Mitigation: Redis deployed with standard managed-service availability guarantees; documented as an accepted trade-off, not unaddressed.
- **Role-array design (AD-02) query risk:** array-based role checks may complicate certain admin queries ("list all MODERATORs") at larger scale; low risk at MVP scale, tracked as a documented future migration path.
- **CSRF mechanism:** RESOLVED in this correction pass — see Section 13 and AD-14 (double-submit-cookie pattern). No longer an open risk; implementation must match the specified mechanism.
- **Moderation state model:** RESOLVED in this correction pass — see Section 10.1 and AD-08. `research` now has a `moderation_status` field distinct from its authoring `status`, and `moderation_actions` is the authoritative action audit trail.

### Technical Assumptions
- UUID generation strategy (random v4 vs. time-sortable v7) is not yet finalized — assumed v4 via `pgcrypto` unless the API-spec/DB-migration phase finds a concrete reason (e.g., index locality) to prefer v7.
- `pg_trgm` extension availability is assumed for company duplicate-detection (ERR-001) — to be confirmed available in the chosen managed-Postgres offering.
- Background job library (`arq` or equivalent) is proposed, not finalized — any async, Redis-backed, FastAPI-compatible library satisfying AD-07's reasoning is acceptable.
- Managed Postgres/Redis (e.g., AWS RDS/ElastiCache or equivalent) is assumed over self-hosted database instances, consistent with "avoid premature infrastructure" and standard backup/DR features.

### Remaining Technical Questions
1. UUID generation strategy (v4 vs v7) — deferred to database migration authoring.
2. Exact background-job library choice — deferred to implementation/scaffold phase.
3. Backup retention period (currently a conservative operational default, not a specified product requirement) — should be confirmed with the founder or left as an infra default.
4. Whether `docs/PRD/README.md` is a required project convention remains unresolved (carried over from `work_memory.md` Section 22 — not an architecture concern, noted for completeness only).
5. Whether the first payment attempt creates a `subscriptions` row in a pending state before checkout, or whether the row is created upon webhook confirmation — minor sequencing detail, deferred to the API-spec phase, does not block founder review of this architecture.

(CSRF mechanism is no longer listed here — resolved in this correction pass, see Section 13/AD-14.)

### Recommended Implementation Order
1. Repository/monorepo scaffold (directory structure per Section 4.1, no business logic yet).
2. Database migrations for Section 5.3 tables (Alembic), in dependency order: `users` → `profiles` → `plans` → `subscriptions` → `payments`/`invoices` → `companies` → `research`/`research_versions`/`research_sources`/`research_tags` → `posts`/`comments`/`reactions`/`reports`/`bookmarks` → `moderation_rules`/`moderation_actions` → `watchlists`/`watchlist_items` → `notifications` → `audit_logs`.
3. `core/` cross-cutting infrastructure: config, db session, security (password hashing, session), error handler, audit writer.
4. `auth` module end-to-end (register/login/logout/reset), with RBAC dependency scaffolding.
5. `users`/`membership`/`billing` modules (including provider abstractions, before wiring real Razorpay/Resend credentials).
6. `companies`/`research` modules (workspace + versioning + sources).
7. `community`/`moderation` modules (including the OD-14 nullable `research_id` linkage).
8. `watchlist`/`notifications`/`search`/`admin` modules.
9. API specification document (endpoint-level contract) — explicitly the next artifact after this architecture is approved, per PRD Section 40.
10. Frontend scaffold against the finalized API spec.

### Architecture Definition of Done
This architecture document is considered ready for founder review when:
1. Every PRD MUST-HAVE functional area (Sections 13–41 of the PRD) has a corresponding architectural home (module, table, or explicit cross-cutting concern) in this document.
2. No Phase 2/3 feature (Guilds, Learning Hub, avatar upload, member-facing AI, DMs, real-time data, mobile app, microservices) appears as an implemented requirement anywhere above — only as an explicitly deferred/extension-point note.
3. All 23 locked OD decisions are reflected accurately and none are reinterpreted or reopened (cross-checked in Section 18 below).
4. Every external provider (Razorpay, Resend, S3) is referenced only through its abstraction (`PaymentService`/`EmailService`/`ObjectStorageService`), never directly.
5. The compliance boundary (Section 32/CMPL-*, BOUND-001–003) is structurally reflected (e.g., `moderation_rules.action` CHECK constraint, service-layer-only publish gating) and explicitly disclaimed as non-sufficient for legal compliance.
6. This document does not itself contain SQL migration files or endpoint implementation code — architecture only, as instructed.

---

## Architecture Decision Summary

See Section 6 (AD-01 through AD-07) for the full decision log with reasons, alternatives, trade-offs, and migration paths. In brief: modular monolith over microservices (AD-01); role storage as an array over a join table for MVP simplicity (AD-02); Redis-backed server-side sessions over pure JWT for revocation control (AD-03); service-layer publish validation over DB-level constraints to preserve draft flexibility (AD-04); a schema-level CHECK constraint locking moderation actions to review-only as a compliance safeguard (AD-05); Thesis fields embedded in `research` rather than a separate entity, per the PRD's own reconciliation (AD-06); a lightweight Redis-backed job queue over a dedicated message broker (AD-07).

## Architecture Risks

See Section 17 — Architecture Risks: compliance-boundary enforcement depends on schema/service-layer discipline not being weakened in future changes; Redis becomes load-bearing for authentication availability; role-array design has a bounded future scaling limitation; CSRF mechanism is a locked requirement but not yet a locked implementation.

## Technical Assumptions

See Section 17 — Technical Assumptions: UUID version, `pg_trgm` availability, background-job library choice, and managed (not self-hosted) Postgres/Redis are all assumed defaults pending confirmation during implementation, not product decisions.

## Remaining Technical Questions

See Section 17 — Remaining Technical Questions: CSRF mechanism, UUID strategy, background-job library, backup retention period, and the unrelated-to-architecture `docs/PRD/README.md` convention question carried over from `work_memory.md`.

## Recommended Implementation Order

See Section 17 — Recommended Implementation Order: scaffold → migrations → core infra → auth → membership/billing → companies/research → community/moderation → watchlist/notifications/search/admin → API spec → frontend.

## Architecture Definition of Done

See Section 17 — Architecture Definition of Done: full PRD MUST-HAVE coverage, no Phase 2/3 leakage, all 23 OD decisions respected, providers abstracted, compliance boundary structurally reflected, no premature SQL/implementation code included.

---

## 18. Verification Against Locked PRD and Work Memory

This section records the self-verification performed before presenting this document, per instruction.

**Phase 2/3 leakage check:** Reviewed every module and table in Sections 4–5 against PRD Sections 46–48 (Out of Scope / Phase 2 / Phase 3 backlog). No Guilds, Learning Hub, Certification, avatar upload, member-facing AI, DMs, real-time market data, mobile app, or microservices infrastructure appears as an implemented requirement anywhere above. Where relevant, deferral is stated explicitly (Section 5.4, AD-06, PROF/profiles note).

**23 Locked Decisions check:** Each OD-01–OD-23 was traced to at least one concrete architectural element:
- OD-01 → Section 9 payment go-live note, compliance notice at document top.
- OD-02 → tier gating logic implied by `subscriptions`/`plans` + module-level access checks (Section 4.2/9).
- OD-03 → Section 7 (Argon2id, 12-char minimum).
- OD-04 → AD-03 (session architecture).
- OD-05 → AD-02 (`role_grants` array, additive set).
- OD-06 → `subscriptions.grace_period_ends_at`, Section 9 grace-period job.
- OD-07 → `payments.status = 'refunded'` value present, no auto-refund code path described.
- OD-08 → `moderation_rules` table, AD-05.
- OD-09 → the OD-09 *definition* itself is a product decision, not a schema concern, and remains correctly unreflected in tables. Section 38 (ANLY-001–003) requiring the underlying events to be *tracked* was originally found to have no architectural treatment — flagged as a HIGH finding in the first verification pass, and **now resolved** in Section 21 (`events` table, AD-15). OD-09's exact qualifying-activity wording maps one-to-one onto the `events.event_type` qualifying set (Section 21.3), with no remaining interpretation gap.
- OD-10 → `PaymentService`/Razorpay, Section 4.4/9.
- OD-11 → `ObjectStorageService`/S3, Section 4.4.
- OD-12 → `EmailService`/Resend, Section 4.4.
- OD-13 → not a schema concern; UX cadence explicitly deferred to UI/UX spec, consistent with PRD.
- OD-14 → `posts.research_id` nullable FK, Section 5.3/10.
- OD-15 → no "Research Reviewed" metric appears anywhere in this document.
- OD-16 → `invoices` table + `BillingService`/`TaxService`/`InvoiceService`, Section 5.3/4.4.
- OD-17 → Section 14 (anonymization architecture).
- OD-18 → Section 14/15 (region preference, explicitly not a compliance claim).
- OD-19 → Section 16.1 (direct query default).
- OD-20 → Section 5.4 (Learning Hub tables deferred).
- OD-21 → `profiles` table has no avatar column, explicitly noted.
- OD-22 → `plans` table, ₹799 seed value noted as configurable.
- OD-23 → `companies.exchange` CHECK constraint.

**BOUND-001–003 check:** No table, module, or endpoint in this document executes trades, connects to a broker, manages a portfolio, or generates a personalized buy/sell/hold instruction. Payment billing go-live remains explicitly gated on OD-01 (Section 9).

**Compliance-claim check:** This document does not anywhere assert that QFinance is legally compliant as a result of the controls described; the notice at the top and Section 14 explicitly disclaim this, consistent with PRD Section 32.

No contradictions with the locked PRD or `work_memory.md` were found during this self-verification. The moderation action/content-status mismatch and the ANLY-*/event-tracking architecture gap, both identified during formal verification passes, have both now been resolved — see Section 10.1/AD-08 (moderation) and Section 21/AD-15 (analytics). No HIGH or CRITICAL findings remain outstanding as of this second correction pass (see Section 22).

---

## 19. PRD Requirement Traceability Matrix

For every MVP requirement group: PRD requirement → architecture section → database entity (if applicable) → API/module (if applicable). Gaps are called out explicitly rather than omitted.

| PRD Requirement Group | Architecture Section | Database Entity | Module |
|---|---|---|---|
| AUTH-001–009 (Authentication) | §7 | `users` | `auth` |
| PROF-001–006 (Profile) | §5.3 `profiles` | `profiles` | `users` |
| Member directory (Section 11 SHOULD / MEM-003 gated feature) | AD-10 | derived from `users`/`profiles`/`subscriptions`, no new table | `users` (`GET /api/v1/users/directory`) |
| MEM-001–007 (Membership) | §9 | `plans`, `subscriptions` | `membership` |
| COMM-001–008 (Community) | §10, PCR-* | `posts`, `comments`, `reactions` | `community` |
| COMM-006 (Bookmarks) | AD-09, §5.3 | `bookmarks` | `community` |
| PCR-001–003 | §5.3 `posts`/`comments`/`reactions` | same | `community` |
| MOD-001–005 (Moderation) | §10.1, AD-08 | `reports`, `moderation_actions`, `moderation_rules` | `moderation` |
| LIB-001–005 (Research Library) | §11 Search, §5.3 `research` | `research`, `research_tags` | `research`, `search` |
| CO-001–004 (Company) | §5.3 `companies` | `companies` | `companies` |
| RES-001–006, QRES-001–003 (Research Workspace) | §10, AD-04 | `research` | `research` |
| Thesis (Section 23) | AD-06 | embedded in `research` | `research` |
| VER-001–004 (Versioning) | §10 | `research_versions` | `research` |
| SRC-001–004 (Sources/Disclosure) | §5.3 `research_sources`, `research` disclosure columns | `research_sources` | `research` |
| WL-001–003 (Watchlist) | §5.3 | `watchlists`, `watchlist_items` | `watchlist` |
| NOTIF-001–003 (Notifications) | §5.3 | `notifications` | `notifications` |
| ADMIN-001–007 (Admin Dashboard) | §16.1 | reads across all modules | `admin` |
| RBAC-001–003 | §8 | `profiles.role_grants` | cross-cutting (`core/deps.py`, `core/permissions.py`) |
| AUDIT-001–003 | §5.3 `audit_logs` | `audit_logs` | `audit` |
| CMPL-001–005 (Compliance) | §1 notice, §14, §10.1 | `research` disclosure fields, `moderation_rules` | `research`, `moderation` |
| PRIV-001–004 (Privacy) | §14 | `users.is_anonymized`, soft-delete columns | `users`, `auth` |
| ERR-001–004 (Error/Edge cases) | §5.3 `companies` indexes, §9 idempotency | `companies`, `payments` | `companies`, `billing` |
| STATE-001–003 (Empty/Loading/Error states) | §4.3, §12 | — (frontend/API concern) | frontend, `core/errors.py` |
| SEARCH-001–003 | §11 | `research`, `companies` (GIN indexes) | `search` |
| **ANLY-001–003 (Analytics/Event Tracking)** | **§21 (Analytics & Event Tracking Architecture), AD-15** | **`events`** | **`analytics`, consumed by `admin`** |
| PAY-001–006 (Payments) | §9 | `payments`, `subscriptions` | `billing`, `membership` |
| RBAC matrix / REVIEWER badge | AD-12 | `profiles.role_grants` (read at render time) | `community` |
| CSV export (Section 11 SHOULD) | AD-11 | none — derived from `research` | `research` (`GET /api/v1/research/export.csv`) |
| DB-001–002 | §5.1, §5.4 | all tables (additive-migration discipline) | — |
| API-001–005 | §12 | — | cross-cutting |
| INT-001–004 | §4.4 | — | `integrations` |
| SEC-001–008 | §13 | — | cross-cutting |
| PERF-001–003 | §16.1 | — | — |
| A11Y-001–003 | not covered in this architecture (frontend implementation detail, not schema/module-level) | — | frontend, deferred to UI/UX spec |
| SEO-001–003 | §4.3 (SSR) | — | frontend |

**Remaining traceability gap:** None. ANLY-001–003 is now fully represented (Section 21, `events` table, `analytics` module) — see Section 22 (Second Correction Log) for the resolution record.

## 20. Correction Log

This section records what changed in this correction pass, for founder review, distinct from the Architecture Decision Log (Section 6) which explains *why*.

| # | Finding (from verification report) | Severity | Status | Where fixed |
|---|---|---|---|---|
| 1 | Moderation action/content-status mismatch; `research` had no moderator-actionable state | HIGH | **Fixed** | §10.1, AD-08, `research.moderation_status`, `posts`/`comments.status` corrected, new `moderation_actions` table |
| 2 | No `bookmarks` table for COMM-006 | MEDIUM | **Fixed** | §5.3 `bookmarks`, AD-09 |
| 3 | Member directory: MVP status undetermined, architecture silent | MEDIUM | **Fixed** — determined to be MVP-in per MEM-003, architected | AD-10 |
| 4 | CSV export: MVP status undetermined, architecture silent | MEDIUM | **Fixed** — determined to be MVP SHOULD-HAVE, architected | AD-11 |
| 5 | REVIEWER badge historical behavior undefined | LOW | **Fixed** — current-role rendering chosen, documented | AD-12 |
| 6 | `posts.channel` unconstrained | LOW | **Fixed** | §5.3 `posts.channel` CHECK constraint |
| 7 | Polymorphic `(target_type, target_id)` trade-off undocumented | LOW | **Fixed** — documented as accepted trade-off | AD-13 |
| 8 | CSRF mechanism unresolved | LOW | **Fixed** — double-submit-cookie pattern specified | §13, AD-14 |
| 9 | Database completeness re-check | — | **Performed** — see table below | §5.3, §19 |
| 10 | PRD traceability matrix | — | **Added** | §19 |
| 11 | Final verification | — | **Performed** — see Correction Report delivered alongside this document | — |
| — | ANLY-001–003 / Section 38 event-tracking architecture missing | HIGH | **Fixed in second correction pass** — see §21, §22 | Not in scope of this correction instruction at the time; flagged in §18, §19 |

### 20.1 Database Completeness Re-Check (Finding #9)

Every MVP entity listed in PRD Section 39 plus the two entities added in this correction pass now has an architectural representation:

`users`, `profiles`, `plans`, `subscriptions`, `payments`, `invoices`, `posts`, `comments`, `reactions`, `reports`, **`bookmarks` (added)**, `moderation_rules`, **`moderation_actions` (added)**, `companies`, `research`, `research_versions`, `research_sources`, `research_tags`, `watchlists`, `watchlist_items`, `notifications`, `audit_logs`. (`events` was added in the subsequent second correction pass — see Section 22.1.)

No unnecessary tables were introduced — member directory and CSV export were deliberately given *no* new table (AD-10, AD-11), consistent with Principle 1 (Simplicity) and Principle 8 (Avoidance of premature infrastructure), since both are derivable from existing tables.

---

## 21. Analytics & Event Tracking Architecture

This section resolves the one HIGH-severity finding left outstanding after the first correction pass: PRD Section 38 (ANLY-001–003) and OD-09's underlying event-tracking requirement had no architectural representation. See AD-15 (Section 6) for the decision-log entry; this section is the full design.

### 21.1 What events are tracked

The `events` table (Section 5.3) tracks exactly 12 `event_type` values via a CHECK constraint — the 9 named explicitly in ANLY-001, plus 3 additive types needed so OD-09's "meaningful research activity" definition is fully computable from tracked events rather than partially inferred:

| event_type | Source (ANLY-001 or additive) | Emitted when |
|---|---|---|
| `signup` | ANLY-001 | A `users` row is created (AUTH-001) |
| `email_verified` | ANLY-001 | `users.email_verified_at` is set (AUTH-002 verification link followed) |
| `login` | ANLY-001 | A session is successfully issued (AUTH-003) |
| `payment_completed` | ANLY-001 | A `payments` row transitions to `status='succeeded'` (PAY-002/003) |
| `research_draft_created` | ANLY-001 | A new `research` row is created in `draft` status (RES-001) |
| `research_draft_updated` | **Additive** | An existing draft `research` row is saved again with changed field values (RES-003) — needed because OD-09 explicitly includes "research draft created/**updated**" but ANLY-001's list only names `research_draft_created` |
| `research_section_completed` | **Additive** | Any one of the 9 Q-RESEARCH stage fields (Section 22) transitions from empty/NULL to non-empty on save — needed because OD-09 explicitly includes "research section completed" as its own qualifying activity, distinct from a generic draft update |
| `research_source_added` | **Additive** | A `research_sources` row is created (SRC-001/002) — needed because OD-09 explicitly includes "source added" as its own qualifying activity |
| `research_published` | ANLY-001 | `research.status` transitions to `published` (RES-005) |
| `research_commented` | ANLY-001 | A `comments` row is created on a post where `posts.research_id IS NOT NULL` (i.e., a research-discussion comment, per OD-14) — general community comments on `research_id IS NULL` posts do **not** emit this event (see 21.2) |
| `post_created` | ANLY-001 | Any `posts` row is created, general or research-linked |
| `watchlist_added` | ANLY-001 | A `watchlist_items` row is created (WL-001) |

All 12 are enforced via the `event_type` CHECK constraint on `events` (Section 5.3) — the same schema-level discipline already used for `moderation_rules.action` (AD-05), so a future code change cannot silently start emitting an unlisted event type without a migration.

### 21.2 Which user/member actions generate events

Events are emitted from the **service layer** (`modules/<name>/service.py`), never from route handlers and never from the frontend. This mirrors the `audit_logs`/`moderation_actions` pattern (Section 10.1) and for the same reason: the service layer is the one place that knows an action has *actually succeeded* (committed to the database), so it is the only trustworthy place to say "this event genuinely happened." Concretely:

- `modules/auth/service.py` emits `signup`, `email_verified`, `login`.
- `modules/billing/service.py` emits `payment_completed`, inside the same transaction as the `payments`/`subscriptions` update described in Section 9 (webhook-driven, using the existing `gateway_reference_id` idempotency guarantee — see 21.9).
- `modules/research/service.py` emits `research_draft_created`, `research_draft_updated`, `research_section_completed`, `research_source_added`, `research_published`.
- `modules/community/service.py` emits `post_created` (always) and `research_commented` (only when the target post's `research_id IS NOT NULL` — this single condition is what implements OD-09's "substantive comment/review on a research item" vs. excluded "general (non-research) community comments": a research-discussion comment is definitionally the substantive kind OD-09 asks to count, and a General Discussion/Off Topic comment is definitionally the excluded kind, with no separate "substantive" judgment call needed).
- `modules/watchlist/service.py` emits `watchlist_added`.
- Reactions ("likes") **never** emit an event of any kind — ANLY-001's list has no `reaction_added` event, and OD-09 explicitly excludes likes from the meaningful-activity metric; there is deliberately no tracking mechanism for reactions at all, not even one that's simply excluded from the OD-09 query, to avoid building unused tracking surface (Principle 8).

### 21.3 Which events are required for "meaningful research activity" (OD-09/ANLY-002)

The qualifying set is exactly six of the twelve event types:

```
research_draft_created, research_draft_updated, research_section_completed,
research_source_added, research_published, research_commented
```

This set is a direct, complete mapping of OD-09's own wording ("research draft created/updated, research section completed, source added, research published, substantive comment/review on a research item") to the `event_type` vocabulary in 21.1 — no interpretation gap remains between the two. `signup`, `email_verified`, `login`, `payment_completed`, `post_created`, and `watchlist_added` are explicitly excluded, matching OD-09's exclusion of "likes and general (non-research) community comments" (reactions were never tracked at all per 21.2, and `post_created`/general comments are structurally distinguished from `research_commented` as described above).

### 21.4 Event schema/entity

See Section 5.3 `events` table for the full column specification. Summary: `id`, `user_id` (NOT NULL FK), `event_type` (CHECK-constrained), `entity_type`/`entity_id` (nullable polymorphic pointer, same accepted trade-off as AD-13), `metadata` (JSONB, non-PII structured detail only), `created_at`. No `updated_at`/`deleted_at` — append-only.

### 21.5 Storage: PostgreSQL, confirmed sufficient for MVP

Yes — `events` is an ordinary PostgreSQL table in the same database as every other MVP table, per explicit instruction to prefer PostgreSQL-based tracking if sufficient. At MVP scale (Section 8: 50 registered users, 20+ MAU, 10+ paying, growing to the <500-paid-member ceiling referenced in Section 16.1), even a generous estimate of 20 events/user/day yields roughly 10,000 events/day at the upper end — trivially within PostgreSQL's comfortable range with the indexes specified in Section 5.3, with no partitioning, read replica, or separate analytics database needed at this scale.

### 21.6 Event retention

No PRD requirement specifies an events-specific retention period (Section 38 is silent on retention, unlike PRIV-003/OD-17 which explicitly discusses account-deletion retention). Default: retained indefinitely, consistent with the same "no stated period → retain until a future policy sets one" approach already used for `audit_logs` and post-anonymization content (Section 14). If volume ever becomes a genuine storage/performance concern (not expected at MVP scale per 21.5), the future migration path is monthly table partitioning by `created_at` (a standard, additive PostgreSQL technique) rather than deletion, since historical events remain useful for trend metrics (e.g., "Churn, trailing 30 days" per ADMIN-002 needs at least 30+ days of history, and multi-month cohort analysis needs more).

### 21.7 Privacy considerations

- `events` collects only what ANLY-001 asks for: a user ID, an event type, a timestamp, and a minimal non-PII entity pointer — consistent with PRIV-001's "minimum necessary data" principle.
- `metadata` JSONB is restricted by convention (enforced in code review / testing, Section 16.2) to small structured, non-identifying detail (e.g., `{"section": "risk_register"}` for a `research_section_completed` event) — it never duplicates free-text content (comment bodies, research field values, payment amounts beyond what's already in `payments`), so `events` never becomes a second, less-protected copy of sensitive content.
- `events` is an **internal, admin-facing** analytics log (feeding ADMIN-002/007 metrics only) — it is not exposed to other members, not used for member-facing profiling or personalization (which would risk brushing against BOUND-001's "no personalized instruction" boundary), and not shared with or sold to any third party. No member-facing feature reads from `events` in MVP.
- Account anonymization (PRIV-003/OD-17): `events.user_id` is **retained**, not nulled, on the same reasoning already applied to `audit_logs`/`research`/`posts` (Section 14) — historical event data remains attributed to the now-anonymized identity rather than being deleted, since deleting it would silently corrupt historical trend metrics (e.g., a past month's "meaningful activity" count would retroactively change if the underlying events disappeared). This introduces no new privacy exposure beyond what anonymization already accepts for those other tables.

### 21.8 Immutability

Yes — `events` has no `updated_at` and no `deleted_at`, identical in spirit to `audit_logs` and `moderation_actions`. No application route or admin capability exposes UPDATE/DELETE on `events`; enforced by omission (no such endpoint exists) and, as defense-in-depth, the same database-level `REVOKE UPDATE, DELETE` on the application's runtime DB role already specified for `audit_logs`.

### 21.9 User/member identity requirement

Yes — `events.user_id` is `NOT NULL`. All 12 tracked event types are member-initiated actions by definition (even `signup`, which requires the just-created `users.id`); there is no system-initiated or anonymous event type in MVP scope, so there is no need for a nullable actor column here (unlike `audit_logs.actor_id`, which is nullable for genuinely system-initiated actions like the automated grace-period downgrade job).

### 21.10 How events are queried for analytics (ANLY-002/003)

Two query shapes cover every MVP analytics need, both direct real-time queries per OD-19/ADMIN-007 (no batch ETL):

1. **Per-member meaningful-activity check (ANLY-002):** `SELECT COUNT(*) > 0 FROM events WHERE user_id = :user_id AND event_type IN (:qualifying_set) AND created_at >= :month_start AND created_at < :month_end`. Backed by the `(user_id, event_type, created_at)` index (Section 5.3).
2. **Admin time-windowed aggregate metrics (ANLY-003, feeding ADMIN-002's "Research Created," "Research Updated," "Research Discussions" panels and the OD-09 success-criteria rollup in Section 8):** `SELECT event_type, COUNT(*) FROM events WHERE event_type IN (...) AND created_at >= :window_start GROUP BY event_type`. Backed by the `(event_type, created_at)` index.

Point-in-time totals that don't need historical/time-windowed behavior (e.g., "Total Users," "Paid Members" as of right now) continue to query their entity tables directly (`users`, `subscriptions`) rather than `events` — `events` is the source for *activity-over-a-window* metrics specifically, not a replacement for querying current entity state. This division of responsibility is deliberate: it avoids the ambiguity of two different sources of truth for the same number.

### 21.11 How the Admin Dashboard obtains its metrics

ADMIN-002's metric list is served by `modules/admin/service.py`, which for each metric picks the appropriate source per the 21.10 division: `Total Users`/`Paid Members` → direct `users`/`subscriptions` queries; `New Members`/`Churn` → time-windowed `subscriptions`/`users` queries (these don't need `events` since the entity tables already carry the relevant timestamps); `Research Created`/`Research Updated`/`Research Discussions`/`Posts`/`Comments`/`Reports` → time-windowed `events` queries per 21.10 pattern 2 (this is *why* `research_draft_updated` was added as an additive event type — without it, "Research Updated" as a distinct metric from "Research Created" would have no data source); `MRR` → direct `subscriptions`/`plans` computation. No metric is computed by an ETL job or a separate analytics warehouse (OD-19).

### 21.12 Meaningful-research-activity metric calculation (Section 8 success criteria)

The Section 8 success-criteria rollup ("70%+ of paying members perform at least one meaningful research activity per month") is computed as: for each active Core `subscriptions` row, run the 21.10 pattern-1 query for the relevant calendar month, then `percentage = (count of members with >=1 qualifying event) / (count of active paying members that month) * 100`. This is a direct query over `events` joined to `subscriptions`, run on demand when the founder reviews success criteria (Section 8 is a review cadence, not a live dashboard tile in MVP's ADMIN-002 list — ADMIN-002 lists specific metrics and "meaningful activity %" is not named among them, so it is not built as a dashboard panel, only as an available query pattern; if the founder wants it promoted to a dashboard tile, that is a small additive change reusing this exact query).

### 21.13 Avoiding duplicate/replayed events

- Events are written **only** from the service layer, in the same DB transaction as the underlying entity write (e.g., the `research_published` event insert and the `research.status = 'published'` update commit together or not at all) — never from the API/route layer (which could double-fire on client retries) and never from the frontend (untrusted, replayable).
- `payment_completed` specifically reuses the existing `payments.gateway_reference_id` UNIQUE constraint (ERR-003, Section 5.3): the event-emitting code path only runs once per unique gateway transaction, since it lives inside the same idempotent webhook-handling transaction described in Section 9 — a webhook delivered twice for the same transaction cannot produce two `payment_completed` events, for the same reason it cannot double-credit a subscription.
- `login` has no dedup requirement — each successful login is a genuinely discrete, intentionally-repeatable event; there is no "duplicate login" concept to guard against.
- No idempotency key column is added to `events` itself, since the transactional-write discipline above is sufficient at MVP scale and avoids over-engineering a mechanism the table doesn't need (Principle 8).

### 21.14 Synchronous vs. asynchronous writes

Synchronous, in the same DB transaction as the triggering action — not queued via Redis/`arq` (AD-07). Reason: an `events` INSERT is a single, cheap row write; queuing it would add latency-hiding complexity (a background job, a retry policy, a dead-letter concern) for no benefit, and would reintroduce exactly the "could an event silently fail to record" risk that a same-transaction write avoids. This mirrors the same choice already made for `moderation_actions` and `audit_logs` (Section 10.1): compliance/measurement-relevant log writes are transactional, not best-effort.

### 21.15 Whether Redis/background jobs are necessary

No, not for event *capture* (21.14). Redis/`arq` (AD-07) remains reserved for its existing MVP purposes (email sending, webhook retries, session cache) and is not extended to cover analytics writes. The only place Redis could optionally enter the analytics picture is the existing OD-19 exception path already described in Section 16.1 ("a specific metric proven too slow as a direct query may use scheduled Redis-backed aggregation") — this remains a documented future exception, not something needed for launch, since 21.5 shows MVP-scale `events` volume is trivially query-able directly.

### 21.16 Indexes required for efficient analytics queries

Already specified in Section 5.3: `(user_id, event_type, created_at)` for the ANLY-002 per-member query; `(event_type, created_at)` for the ANLY-003 admin aggregate query; a partial index restricted to the six OD-09 qualifying event types (21.3) to keep the most frequently-run query's index small and fast. No additional indexes are anticipated at MVP scale.

### 21.17 Separation from business/domain tables

`events` is owned by its own module (`analytics`, Section 4.2) rather than being bolted onto an existing module (e.g., `research` or `audit`) — this keeps the cross-cutting "every module can emit a tracked event" responsibility architecturally distinct from any one domain's business logic, the same reasoning already applied to `audit` (Section 4.2's `audit` module) and consistent with Principle 5 (clear module boundaries). It remains in the **same PostgreSQL database** as every other table (Principle 8, per explicit instruction) — "separated" means module/ownership separation, not physical/infrastructure separation.

### 21.18 Future migration path to a dedicated analytics system

If QFinance later needs capabilities this design deliberately doesn't build (funnels, cohort retention curves, session replay, real-time streaming dashboards, self-serve exploratory analytics for non-engineers), the migration path is: (a) begin dual-writing `events` rows to a dedicated analytics platform (e.g., PostHog, self-hosted or cloud) alongside the existing Postgres writes, without removing the Postgres table (which remains the system of record for the OD-09 metric and ADMIN-002 dashboard, both of which have no dependency on the new platform), then (b) migrate specific *dashboard* consumers to the new platform's query layer one at a time as they're rebuilt with richer needs. This is explicitly **not** designed into MVP — named here only so a future session recognizes it as an available, additive extension point rather than a redesign, consistent with how Section 5.4 documents other deferred/future schema needs.

---

## 22. Second Correction Log — ANLY-001–003 Resolution

This section records the second, narrower correction pass: resolving the single outstanding HIGH finding left after Section 20's correction pass (analytics/event-tracking architecture), per explicit founder instruction.

### 22.1 Analytics requirements (from the locked PRD, read verbatim before designing)

- **ANLY-001** (MUST): track 9 named distinct events (`signup`, `email_verified`, `payment_completed`, `research_draft_created`, `research_published`, `research_commented`, `post_created`, `watchlist_added`, `login`), each with user ID and timestamp.
- **ANLY-002** (MUST, OD-09-linked): "meaningful research activity" computed per member per calendar month as at least one of {research draft created/updated, research section completed, source added, research published, substantive comment/review on a research item}; likes and general community comments explicitly excluded.
- **ANLY-003** (MUST): Admin metrics (Section 28/ADMIN-002) computed from tracked events plus core entity tables, on a defined refresh cadence (OD-19: real-time query by default).

### 22.2 Architecture changes

- Added Section 21 (Analytics & Event Tracking Architecture), 18 subsections covering every point requested in the correction instruction (events tracked, triggering actions, OD-09 qualifying set, schema, storage choice, retention, privacy, immutability, identity requirement, query patterns, admin-dashboard integration, meaningful-activity calculation, duplicate-prevention, sync/async choice, Redis necessity, indexes, table-separation rationale, future migration path).
- Added AD-15 to the Architecture Decision Log (Section 6): single PostgreSQL `events` table, no third-party analytics platform, written synchronously in the service layer.
- Added `events` to the ERD (Section 5.2) and to the module-ownership table (Section 4.2, new `analytics` module).
- Updated Section 18 self-verification (OD-09 line, closing contradiction-check paragraph) and Section 19 traceability matrix (ANLY-001–003 row now fully populated) to reflect the resolution.

### 22.3 New/modified entities

- **New:** `events` table (Section 5.3) — `id`, `user_id` (NOT NULL FK), `event_type` (CHECK-constrained to 12 values), `entity_type`/`entity_id` (nullable polymorphic pointer), `metadata` (JSONB), `created_at`. Append-only, no `updated_at`/`deleted_at`.
- No existing entity's columns were changed by this pass (unlike the first correction pass, which altered `research`/`posts`/`comments`).

### 22.4 New/modified indexes

- `(user_id, event_type, created_at)` on `events` — ANLY-002 per-member monthly query.
- `(event_type, created_at)` on `events` — ANLY-003 admin aggregate query.
- Partial index on `events` restricted to the six OD-09 qualifying `event_type` values — accelerates the single most-run analytics query.

### 22.5 OD-01 through OD-23

All 23 remain respected and none reinterpreted. OD-09 specifically: the *product definition* was never touched (it was never a schema concern), but the previously-missing *tracking mechanism* it depends on is now built (Section 21), closing the gap between the locked product decision and the architecture's ability to actually compute it.

### 22.6 PRD traceability

Section 19's traceability matrix ANLY-001–003 row now reads: Architecture Section §21/AD-15, Database Entity `events`, Module `analytics`. Zero rows in the traceability matrix remain marked "NOT ARCHITECTED."

### 22.7 MVP scope

No scope change. `events` tracks only the 9 ANLY-001-named actions plus 3 additive event types strictly required to make OD-09's own already-locked wording computable — no new user-facing feature, no member-facing analytics/profiling surface, no scope creep beyond what Section 38 and Section 8 already required.

### 22.8 Phase 2 leakage

None. Explicitly rejected in AD-15: no third-party analytics platform, no advanced/member-intelligence analytics dashboard (that remains Phase 2 backlog per PRD Section 47, untouched). The `events` table is deliberately minimal — exactly the PRD's own requirement, nothing more.

### 22.9 Database completeness

`events` is now included in the full MVP entity list (Section 20.1 note above). Every PRD Section 39 entity, plus `bookmarks`/`moderation_actions` (first correction pass) and `events` (this pass), has an architectural representation. No unnecessary tables introduced.

### 22.10 Security

No change to the security posture described in Section 13. `events` follows the same append-only, `REVOKE UPDATE/DELETE` pattern as `audit_logs`/`moderation_actions`; no new attack surface (no new user-facing endpoint takes arbitrary input into `events` — all writes are internal, service-layer-triggered).

### 22.11 Privacy/compliance

See Section 21.7 in full. Summary: minimum-necessary data (PRIV-001-consistent), no PII duplication in `metadata`, internal/admin-only consumption (no member-facing profiling, consistent with BOUND-001's spirit), and consistent anonymization treatment with `audit_logs`/`research`/`posts` on account deletion (PRIV-003/OD-17).

### 22.12 Remaining findings

**None at HIGH or CRITICAL severity.** All findings from both verification passes are now either Fixed or were LOW-severity items already fixed in the first correction pass (Section 20). No new findings were introduced by this second pass — the addition is scoped exactly to Section 38/OD-09 per instruction, with no incidental changes to moderation, bookmarks, member directory, CSV export, RBAC, CSRF, or any other already-corrected area.

One pre-existing LOW/administrative item remains open, carried over unchanged from Section 17 (not part of either correction instruction's scope, and not HIGH/CRITICAL): the exact sequencing of `subscriptions` row creation relative to first checkout (payment-flow implementation detail, explicitly deferred to the API-spec phase in Section 17, does not block founder approval of this architecture document).

### 22.13 Final architecture status

**🔒 APPROVED — founder confirmation 2026-08-29 ("i approve it go further").**

Zero HIGH/CRITICAL unresolved architectural findings remained at the time of approval. See Section 22.12 for the one remaining LOW/administrative item (payment-flow sequencing detail), which does not block API Specification V1 and is explicitly deferred to that phase.

---

*QFinance Architecture V1 — 🔒 APPROVED, founder confirmation 2026-08-29; Amendment 1 applied 2026-08-29 (post-approval, resolving `research.title`/`summary`, `compliance_acknowledgments`, and published-edit revalidation — see AD-16/AD-17); Amendment 2 applied 2026-08-29 (post-approval, Founder Decision #1, adding `research.access_tier` — see AD-18); Amendment 3 applied 2026-08-29 (post-approval, Founder Decision #2, adding the `access_tier` authorization rule — see AD-19, Section 6A: ADMIN/SUPER_ADMIN only, no new role, audited via existing `audit_logs`). Database Schema V1 (derived from this document) is also 🔒 APPROVED, with matching amendments already applied where schema changes were needed (Amendment 3/Founder Decision #2 required no schema change — see that document's own Amendment Log). API Specification V1 is the current in-progress artifact and should be re-checked against all amendments, including the new §7.5 `PATCH /research/{id}/access-tier` endpoint, before it is marked locked.*
