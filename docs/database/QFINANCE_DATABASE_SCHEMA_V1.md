# QFinance — Database Schema V1

**Status:** 🔒 APPROVED — founder approval confirmed 2026-08-29 (explicit chat confirmation: "I approve Database Schema V1.")
**Depends on:** `docs/PRD/QFINANCE_MVP_PRD_V1.md` (🔒 LOCKED), `docs/architecture/QFINANCE_ARCHITECTURE_V1.md` (🔒 APPROVED, Section 5 — PostgreSQL Architecture), `work_memory.md`
**Document type:** Concrete PostgreSQL schema design (DDL-level), derived strictly from the approved architecture
**Project root:** `/home/prd/Projects/QFinance`

**Scope discipline (per explicit founder instruction):** This document introduces **no new product features and no new architectural decisions**. Every table, column, constraint, and index below is a direct, literal translation of Architecture V1 Section 5's table specifications into executable-shape PostgreSQL DDL. Where Architecture V1 left an implementation detail open (e.g., UUID v4 vs v7, per Architecture §17 Technical Assumptions), this document makes the same assumption Architecture V1 already stated, not a new one. This is a **design document**, not an executed migration — no Alembic migration files are created, and no DDL here has been run against any database. Migration authoring is future work per the Recommended Implementation Order (Architecture §17).

---

## 0. Conventions and Extensions

```sql
-- Required PostgreSQL extensions (per Architecture §5.1, §17 Technical Assumptions)
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive email/username
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- company duplicate-detection (Architecture ERR-001 note)
```

- **Primary keys:** `UUID DEFAULT gen_random_uuid()` everywhere, per Architecture §5.1. UUID v4 (not v7) — Architecture §17 left this open and assumed v4 pending a concrete reason to prefer v7; this document carries that same assumption forward rather than deciding it fresh.
- **Timestamps:** `TIMESTAMPTZ` throughout. `created_at`/`updated_at` present on every table per Architecture §5.1, except the four append-only tables (`audit_logs`, `moderation_actions`, `events`, `research_versions`) which intentionally have `created_at` only — no `updated_at`, no `deleted_at` — per Architecture §5.3's explicit immutability rationale for each.
- **`updated_at` maintenance:** a single shared trigger function, applied to every table that has the column:

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Applied per-table below as: CREATE TRIGGER trg_<table>_updated_at BEFORE UPDATE ON <table>
-- FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

- **Soft delete:** `deleted_at TIMESTAMPTZ NULL` on soft-deletable tables per Architecture §5.1 (PRIV-003, PCR-002, CO-004). A row with `deleted_at IS NOT NULL` is excluded from application queries via `WHERE deleted_at IS NULL` in every read path — this document does not use partial-index-enforced exclusion beyond the one case (`users.email`) Architecture §5.3 already specified.
- **Money:** integer minor units (paise), `INTEGER`, with `currency CHAR(3) DEFAULT 'INR'` alongside, per Architecture §5.1.
- **Foreign keys:** `ON DELETE RESTRICT` by default; explicit `ON DELETE CASCADE`/other only where Architecture §5.3 stated it (only `profiles.user_id → users.id`).
- **Append-only defense-in-depth:** for `audit_logs`, `moderation_actions`, and `events`, Architecture §5.3/13 specifies a database-level `REVOKE UPDATE, DELETE` on the application's runtime role. That grant/revoke statement is environment-specific (depends on the actual runtime role name chosen at deployment time) and is therefore listed as a **deployment-time task**, not baked into this schema document with a placeholder role name.

---

## 1. `users`

```sql
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email             CITEXT NOT NULL,
  password_hash     TEXT NOT NULL,
  email_verified_at TIMESTAMPTZ NULL,
  status            TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'suspended', 'deleted')),
  is_anonymized     BOOLEAN NOT NULL DEFAULT false,
  last_login_at     TIMESTAMPTZ NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ NULL
);

-- Partial unique index: allows email reuse after anonymization (Architecture §5.3 note, OD-17-pending)
CREATE UNIQUE INDEX ux_users_email_active ON users (email) WHERE deleted_at IS NULL;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Traceability: AUTH-001–009, OD-03, PRIV-003/OD-17. Source: Architecture §5.3 `users`.

---

## 2. `profiles`

```sql
CREATE TABLE profiles (
  user_id           UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  name              TEXT NOT NULL,
  username          CITEXT NOT NULL,
  bio               TEXT NULL,
  experience_level  TEXT NULL
                       CHECK (experience_level IN ('beginner', 'intermediate', 'advanced')),
  interests         TEXT[] NULL,
  role_grants       TEXT[] NOT NULL DEFAULT ARRAY['FREE_MEMBER'],
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_profiles_username ON profiles (username);

CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

No `avatar_url` column — per OD-21/PROF-006, unchanged from Architecture. `role_grants` values are constrained to the 6 locked roles at the **application layer** (Architecture AD-02 explicitly chose `TEXT[]` over a normalized table for MVP simplicity; a DB-level check on array element membership is possible in Postgres via a trigger, but Architecture did not specify one, so none is added here — application-layer enforcement matches what was approved). Traceability: PROF-001–006, OD-05/RBAC-003, AD-02. Source: Architecture §5.3 `profiles`.

---

## 3. `plans`

```sql
CREATE TABLE plans (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code              TEXT NOT NULL UNIQUE
                       CHECK (code IN ('FREE', 'CORE')),
  price_paise       INTEGER NOT NULL DEFAULT 0,
  currency          CHAR(3) NOT NULL DEFAULT 'INR',
  billing_interval  TEXT NOT NULL DEFAULT 'monthly',
  is_active         BOOLEAN NOT NULL DEFAULT true,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_plans_updated_at BEFORE UPDATE ON plans
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed data (MEM-001/002, OD-22) — values, not schema, and matches the PRD exactly
INSERT INTO plans (code, price_paise, billing_interval) VALUES
  ('FREE', 0, 'monthly'),
  ('CORE', 79900, 'monthly');
```

Traceability: MEM-001, MEM-002/OD-22. Source: Architecture §5.3 `plans`.

---

## 4. `subscriptions`

```sql
CREATE TABLE subscriptions (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  UUID NOT NULL REFERENCES users(id),
  plan_id                  UUID NOT NULL REFERENCES plans(id),
  status                   TEXT NOT NULL
                              CHECK (status IN ('active', 'past_due', 'canceled', 'expired')),
  current_period_start     TIMESTAMPTZ NOT NULL,
  current_period_end       TIMESTAMPTZ NOT NULL,
  grace_period_ends_at     TIMESTAMPTZ NULL,
  canceled_at              TIMESTAMPTZ NULL,
  gateway_subscription_id  TEXT NULL,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_subscriptions_user_status ON subscriptions (user_id, status);

CREATE TRIGGER trg_subscriptions_updated_at BEFORE UPDATE ON subscriptions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Traceability: MEM-005–007, OD-06. Source: Architecture §5.3 `subscriptions`, §9.

---

## 5. `payments`

```sql
CREATE TABLE payments (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id        UUID NOT NULL REFERENCES subscriptions(id),
  amount_paise           INTEGER NOT NULL,
  currency               CHAR(3) NOT NULL DEFAULT 'INR',
  status                 TEXT NOT NULL
                            CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded')),
  gateway_reference_id   TEXT NOT NULL,
  billing_period_start   TIMESTAMPTZ NOT NULL,
  billing_period_end     TIMESTAMPTZ NOT NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_payments_gateway_reference_id ON payments (gateway_reference_id);

CREATE TRIGGER trg_payments_updated_at BEFORE UPDATE ON payments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

The `UNIQUE` on `gateway_reference_id` is the webhook-idempotency mechanism (ERR-003) — unchanged from Architecture, not a new decision. Traceability: PAY-002/003, ERR-003. Source: Architecture §5.3 `payments`.

---

## 6. `invoices`

```sql
CREATE TABLE invoices (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 UUID NOT NULL REFERENCES users(id),
  payment_id              UUID NOT NULL REFERENCES payments(id),
  amount_paise            INTEGER NOT NULL,
  tax_paise               INTEGER NOT NULL DEFAULT 0,
  currency                CHAR(3) NOT NULL DEFAULT 'INR',
  payment_status          TEXT NOT NULL,
  invoice_date            DATE NOT NULL,
  billing_period          TEXT NOT NULL,
  gateway_reference       TEXT NOT NULL,
  tax_treatment_version   TEXT NULL,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_invoices_user_id ON invoices (user_id);

CREATE TRIGGER trg_invoices_updated_at BEFORE UPDATE ON invoices
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

`tax_paise` is only ever written by `TaxService` at the application layer (Architecture §4.4/9) — not a schema-level constraint, since SQL cannot enforce "which code path" wrote a value; this remains an application-discipline requirement carried forward unchanged. Traceability: PAY-005/OD-16. Source: Architecture §5.3 `invoices`.

---

## 7. `companies`

```sql
CREATE TABLE companies (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  exchange        TEXT NOT NULL
                    CHECK (exchange IN ('NSE', 'BSE', 'OTHER_RECOGNIZED')),
  sector          TEXT NULL,
  industry        TEXT NULL,
  website         TEXT NULL,
  description     TEXT NULL,
  is_merged_into  UUID NULL REFERENCES companies(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at      TIMESTAMPTZ NULL
);

CREATE INDEX ix_companies_name_fts ON companies USING GIN (to_tsvector('english', name));
CREATE INDEX ix_companies_name_trgm ON companies USING GIN (name gin_trgm_ops);

CREATE TRIGGER trg_companies_updated_at BEFORE UPDATE ON companies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

`ix_companies_name_trgm` implements the `pg_trgm`-based duplicate-detection candidate Architecture §5.3/§17 flagged as an assumption pending confirmation of extension availability — included here as the concrete index, per that already-stated intent, not a new decision. Traceability: CO-001–004, OD-23, ERR-001. Source: Architecture §5.3 `companies`.

---

## 8. `research`

```sql
CREATE TABLE research (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id               UUID NOT NULL REFERENCES users(id),
  company_id              UUID NOT NULL REFERENCES companies(id),
  research_type           TEXT NOT NULL,
  industry                TEXT NULL,
  status                  TEXT NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft', 'published')),
  moderation_status       TEXT NOT NULL DEFAULT 'active'
                             CHECK (moderation_status IN ('active', 'restricted', 'removed')),
  access_tier              TEXT NOT NULL DEFAULT 'core'
                             CHECK (access_tier IN ('core', 'free_example')),
  current_version         INTEGER NOT NULL DEFAULT 0,
  title                    TEXT NOT NULL
                             CHECK (char_length(title) BETWEEN 1 AND 200),
  summary                  TEXT NOT NULL
                             CHECK (char_length(summary) BETWEEN 1 AND 500),
  business_quality        TEXT NULL,
  financial_snapshot      TEXT NULL,
  business_model          TEXT NULL,
  competitive_position    TEXT NULL,
  valuation_range         TEXT NULL,
  bull_case                TEXT NULL,
  base_case                TEXT NULL,
  bear_case                TEXT NULL,
  risk_register            TEXT NULL,
  catalysts                TEXT NULL,
  invalidation_conditions  TEXT NULL,
  conflict_disclosed       BOOLEAN NULL,
  conflict_detail          TEXT NULL,
  position_disclosed       BOOLEAN NULL,
  position_detail          TEXT NULL,
  research_date            DATE NULL,
  published_at             TIMESTAMPTZ NULL,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at                TIMESTAMPTZ NULL
);

CREATE INDEX ix_research_company_id ON research (company_id);
CREATE INDEX ix_research_status ON research (status);
CREATE INDEX ix_research_fts ON research
  USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(business_model, '')));

CREATE TRIGGER trg_research_updated_at BEFORE UPDATE ON research
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

**No CHECK constraint enforces publish-time required fields** (bear_case, sources, disclosure) — this is a deliberate carry-forward of Architecture AD-04: publish validation lives in the service layer because drafts must allow incomplete fields (RES-003), and a DB constraint would block valid drafts. This document does not introduce a stricter constraint than Architecture already decided against. `moderation_status` is independent of `status`, per Architecture AD-08/§10.1 — the two-dimension model, unchanged. **`access_tier` is a third, independent dimension** (Amendment 2, 2026-08-29 founder decision, Architecture AD-18): `'core'` (default) is ordinary Core-gated research; `'free_example'` marks an editorially curated item that FREE members may access in full, per PRD MEM-004. This field has no effect on `status`/`moderation_status`/publish-time validation — a `free_example` item still must be `status='published' AND moderation_status='active'` to be visible to anyone, exactly like a `core` item; `access_tier` only changes *what a FREE member sees* once an item is otherwise eligible for viewing. No endpoint for setting/changing `access_tier` is defined in this amendment — who may do so is an explicitly deferred, separate founder decision (not yet made). **`title` and `summary` are `NOT NULL` and author-provided** (Amendment 1, 2026-08-29 founder decision) — unlike the Q-RESEARCH stage fields, these two are required even in `draft` status, since a research item needs a title to be identifiable in a member's "Continue Research" list from the moment it's created; the service layer defaults both to a placeholder (e.g., `"Untitled research"` / empty-string-disallowed placeholder) at creation time (`RES-001`) if not supplied, so the `NOT NULL` constraint is satisfiable at `POST /research` without blocking draft creation, and the author is expected to fill in a real title/summary before publish (enforced as part of the same service-layer publish-validation gate as `bear_case`/sources/disclosure, extended per Amendment 1's published-edit revalidation rule below). The full-text-search index now literally matches Architecture §5.3's corrected column reference — no more silent deviation (see Section 27 Amendment Log for the correction record). Traceability: RES-001–006, QRES-001–003, SRC-001–004, LIB-002/003, MEM-004, DB-002, AD-04, AD-08, AD-16, AD-18. Source: Architecture §5.3 `research` (as amended).

---

## 8A. `compliance_acknowledgments`

```sql
CREATE TABLE compliance_acknowledgments (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id               UUID NOT NULL REFERENCES users(id),
  acknowledgment_type   TEXT NOT NULL
                           CHECK (acknowledgment_type IN ('member_charter', 'risk_disclosure')),
  document_version      TEXT NOT NULL,
  acknowledged_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_compliance_acknowledgments_user_type
  ON compliance_acknowledgments (user_id, acknowledgment_type, acknowledged_at DESC);
```

Added per founder decision 2026-08-29 (Amendment 1), resolving API Specification V1 §12 item 2. Append-only — no `updated_at`/`deleted_at`, same discipline as `audit_logs`/`moderation_actions`/`events`: a fresh acknowledgment of a new `document_version` is a new row, not an update to an old one, so the record of *which version* a user acknowledged is never lost even if the Member Charter or risk-disclosure text changes later. `risk_disclosure` may have more than one row per user (PRD requires acknowledgment both at signup and at first payment — CMPL-005) — the index supports querying "has this user acknowledged the current version" as `MAX(acknowledged_at) WHERE document_version = :current`. Chosen over adding two nullable timestamp columns to `profiles` (the alternative API Spec §12 flagged) because this preserves *which version* was acknowledged, not just *that* acknowledgment happened — a materially different (and more compliance-defensible) guarantee. Traceability: CMPL-004, CMPL-005. Source: this amendment, not pre-existing in Architecture §5.3 — **Architecture V1 requires a corresponding amendment to stay in sync (see amendment note to be applied to Architecture §5.3/§5.2).**

---

## 9. `research_versions`

```sql
CREATE TABLE research_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  research_id     UUID NOT NULL REFERENCES research(id),
  version_number  INTEGER NOT NULL,
  snapshot        JSONB NOT NULL,
  change_note     TEXT NOT NULL,
  edited_by       UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_research_versions_research_version ON research_versions (research_id, version_number);
CREATE INDEX ix_research_versions_research_id ON research_versions (research_id);
```

No `updated_at`/`deleted_at` — immutable by design (VER-001), unchanged from Architecture. No UPDATE/DELETE trigger is attached; enforcement is by omission (no application code path exists to modify these rows) plus the same `REVOKE`-at-deployment pattern noted in Section 0. Traceability: VER-001–004, DB-002. Source: Architecture §5.3 `research_versions`.

---

## 10. `research_sources`

```sql
CREATE TABLE research_sources (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  research_id     UUID NOT NULL REFERENCES research(id),
  label           TEXT NOT NULL,
  reference       TEXT NOT NULL,
  supports_claim  TEXT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_research_sources_research_id ON research_sources (research_id);
```

At-least-one-source-before-publish (SRC-001) is service-layer validation, unchanged from Architecture — no schema constraint enforces a minimum row count per `research_id` (not expressible as a simple CHECK in Postgres). Traceability: SRC-001–002. Source: Architecture §5.3 `research_sources`.

---

## 11. `research_tags`

```sql
CREATE TABLE research_tags (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  research_id  UUID NOT NULL REFERENCES research(id),
  tag          CITEXT NOT NULL
);

CREATE UNIQUE INDEX ux_research_tags_research_tag ON research_tags (research_id, tag);
```

Traceability: LIB-002, LIB-004. Source: Architecture §5.3 `research_tags`.

---

## 12. `posts`

```sql
CREATE TABLE posts (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id     UUID NOT NULL REFERENCES users(id),
  channel       TEXT NULL
                  CHECK (channel IS NULL OR channel IN (
                    'announcements', 'general_discussion', 'research_discussion',
                    'market_discussion', 'learning', 'help_questions', 'off_topic'
                  )),
  research_id   UUID NULL REFERENCES research(id),
  content       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'visible'
                  CHECK (status IN ('visible', 'restricted', 'removed')),
  is_edited     BOOLEAN NOT NULL DEFAULT false,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_posts_channel_or_research CHECK (channel IS NOT NULL OR research_id IS NOT NULL)
);

CREATE INDEX ix_posts_channel ON posts (channel);
CREATE INDEX ix_posts_research_id ON posts (research_id);
CREATE INDEX ix_posts_visible ON posts (created_at) WHERE status = 'visible';

CREATE TRIGGER trg_posts_updated_at BEFORE UPDATE ON posts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

`channel` value list and the channel-or-research CHECK are exact carry-forwards of Architecture §5.3's corrected `posts` spec (which itself resolved a finding during architecture review — not reopened here). Traceability: COMM-001–008, PCR-001–003, OD-14. Source: Architecture §5.3 `posts`, §10.1.

---

## 13. `comments`

```sql
CREATE TABLE comments (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  post_id     UUID NOT NULL REFERENCES posts(id),
  author_id   UUID NOT NULL REFERENCES users(id),
  content     TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'visible'
                CHECK (status IN ('visible', 'restricted', 'removed')),
  is_edited   BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_comments_post_id ON comments (post_id);

CREATE TRIGGER trg_comments_updated_at BEFORE UPDATE ON comments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Traceability: COMM-004, PCR-001. Source: Architecture §5.3 `comments`.

---

## 14. `reactions`

```sql
CREATE TABLE reactions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES users(id),
  target_type    TEXT NOT NULL
                    CHECK (target_type IN ('post', 'comment')),
  target_id      UUID NOT NULL,
  reaction_type  TEXT NOT NULL
                    CHECK (reaction_type = 'like'),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_reactions_unique
  ON reactions (user_id, target_type, target_id, reaction_type);
```

Polymorphic `target_id` carries no FK constraint — accepted trade-off per Architecture AD-13, unchanged; integrity relies on application-layer validation before insert (Architecture §6 AD-13 required unit-test coverage of this). Traceability: COMM-005, PCR-003. Source: Architecture §5.3 `reactions`, AD-13.

---

## 15. `reports`

```sql
CREATE TABLE reports (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reporter_id        UUID NOT NULL REFERENCES users(id),
  target_type        TEXT NOT NULL
                        CHECK (target_type IN ('post', 'comment', 'research')),
  target_id          UUID NOT NULL,
  reason             TEXT NOT NULL,
  status             TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'resolved')),
  resolution_action  TEXT NULL
                        CHECK (resolution_action IN ('approved', 'edited', 'restricted', 'removed', 'member_suspended')),
  resolved_by        UUID NULL REFERENCES users(id),
  resolved_at        TIMESTAMPTZ NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_reports_status ON reports (status);

CREATE TRIGGER trg_reports_updated_at BEFORE UPDATE ON reports
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

Traceability: MOD-001. Source: Architecture §5.3 `reports`.

---

## 16. `moderation_actions`

```sql
CREATE TABLE moderation_actions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  moderator_id    UUID NOT NULL REFERENCES users(id),
  target_type     TEXT NOT NULL
                    CHECK (target_type IN ('post', 'comment', 'research', 'member')),
  target_id       UUID NOT NULL,
  action          TEXT NOT NULL
                    CHECK (action IN ('approve', 'edit', 'restrict', 'remove', 'reinstate', 'suspend_member', 'reinstate_member')),
  report_id       UUID NULL REFERENCES reports(id),
  previous_state  TEXT NULL,
  new_state       TEXT NOT NULL,
  reason          TEXT NULL,
  metadata        JSONB NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_moderation_actions_target ON moderation_actions (target_type, target_id);
CREATE INDEX ix_moderation_actions_moderator ON moderation_actions (moderator_id);
CREATE INDEX ix_moderation_actions_report ON moderation_actions (report_id);
```

Append-only — no `updated_at`/`deleted_at`, matching Architecture AD-08's rationale exactly. Traceability: MOD-002, MOD-005, AUDIT-001/002, AD-08. Source: Architecture §5.3 `moderation_actions`, §10.1.

---

## 17. `bookmarks`

```sql
CREATE TABLE bookmarks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id),
  post_id     UUID NOT NULL REFERENCES posts(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_bookmarks_user_post ON bookmarks (user_id, post_id);
CREATE INDEX ix_bookmarks_user_created ON bookmarks (user_id, created_at DESC);
```

Traceability: COMM-006, AD-09. Source: Architecture §5.3 `bookmarks`.

---

## 18. `moderation_rules`

```sql
CREATE TABLE moderation_rules (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phrase      TEXT NOT NULL,
  severity    TEXT NOT NULL
                CHECK (severity IN ('low', 'medium', 'high')),
  enabled     BOOLEAN NOT NULL DEFAULT true,
  action      TEXT NOT NULL
                CHECK (action = 'flag_for_review'),
  created_by  UUID NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_moderation_rules_enabled ON moderation_rules (enabled);

CREATE TRIGGER trg_moderation_rules_updated_at BEFORE UPDATE ON moderation_rules
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

The `action = 'flag_for_review'` CHECK is the exact compliance safeguard from Architecture AD-05 — not weakened or extended here. Traceability: OD-08, MOD-003, CMPL-003, AD-05. Source: Architecture §5.3 `moderation_rules`.

---

## 19. `watchlists`

```sql
CREATE TABLE watchlists (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL UNIQUE REFERENCES users(id),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Traceability: WL-001–003. Source: Architecture §5.3 `watchlists`.

---

## 20. `watchlist_items`

```sql
CREATE TABLE watchlist_items (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  watchlist_id   UUID NOT NULL REFERENCES watchlists(id),
  company_id     UUID NOT NULL REFERENCES companies(id),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_watchlist_items_watchlist_company ON watchlist_items (watchlist_id, company_id);
```

Traceability: WL-001. Source: Architecture §5.3 `watchlist_items`.

---

## 21. `notifications`

```sql
CREATE TABLE notifications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id),
  type        TEXT NOT NULL
                CHECK (type IN ('comment_on_content', 'reaction_on_content', 'report_resolved', 'moderation_action', 'subscription_change')),
  payload     JSONB NOT NULL,
  read_at     TIMESTAMPTZ NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_notifications_user_read ON notifications (user_id, read_at);
```

Traceability: NOTIF-001/002. Source: Architecture §5.3 `notifications`.

---

## 22. `audit_logs`

```sql
CREATE TABLE audit_logs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id            UUID NULL REFERENCES users(id),
  action_type         TEXT NOT NULL,
  target_entity_type  TEXT NOT NULL,
  target_entity_id    UUID NOT NULL,
  before_state        JSONB NULL,
  after_state         JSONB NULL,
  reason              TEXT NULL,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_audit_logs_target ON audit_logs (target_entity_type, target_entity_id);
CREATE INDEX ix_audit_logs_actor ON audit_logs (actor_id);
```

`actor_id` is nullable — the one deliberate exception among the append-only tables, for genuinely system-initiated actions (e.g., the automated grace-period downgrade job), per Architecture §5.3/§21.9's explicit contrast with `events.user_id` (which is `NOT NULL`). Traceability: AUDIT-001–003. Source: Architecture §5.3 `audit_logs`.

---

## 23. `events`

```sql
CREATE TABLE events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id),
  event_type   TEXT NOT NULL
                 CHECK (event_type IN (
                   'signup', 'email_verified', 'login', 'payment_completed',
                   'research_draft_created', 'research_draft_updated',
                   'research_section_completed', 'research_source_added',
                   'research_published', 'research_commented',
                   'post_created', 'watchlist_added'
                 )),
  entity_type  TEXT NULL
                 CHECK (entity_type IS NULL OR entity_type IN (
                   'research', 'post', 'comment', 'payment', 'subscription', 'watchlist_item'
                 )),
  entity_id    UUID NULL,
  metadata     JSONB NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_events_user_type_created ON events (user_id, event_type, created_at);
CREATE INDEX ix_events_type_created ON events (event_type, created_at);

-- Partial index accelerating the OD-09 "meaningful research activity" query (Architecture §21.3/21.16)
CREATE INDEX ix_events_meaningful_activity ON events (user_id, created_at)
  WHERE event_type IN (
    'research_draft_created', 'research_draft_updated', 'research_section_completed',
    'research_source_added', 'research_published', 'research_commented'
  );
```

12-value `event_type` CHECK is the exact list from Architecture §21.1/AD-15 (9 ANLY-001-named + 3 additive types required for OD-09 computability) — not modified here. Traceability: ANLY-001–003, OD-09, AD-15. Source: Architecture §5.3 `events`, §21.

---

## 24. Entity-Relationship Summary (as-built)

This mirrors Architecture §5.2 exactly, restated here for a single reference point alongside the concrete DDL above — no relationship differs from what Architecture already specified.

```
users ──1:1── profiles
users ──1:N── subscriptions ──N:1── plans
subscriptions ──1:N── payments
subscriptions ──1:N── invoices (via payments)
users ──1:N── posts ──N:1── (nullable) research
posts ──1:N── comments
posts/comments ──1:N── reactions (polymorphic, no FK)
posts/comments/research ──1:N── reports (polymorphic, no FK)
posts/comments/research/users ──1:N── moderation_actions (polymorphic, no FK)
reports ──0:N── moderation_actions
users ──1:N── bookmarks ──N:1── posts
users ──1:N── compliance_acknowledgments
users ──1:N── research ──1:N── research_versions
research ──1:N── research_sources
research ──1:N── research_tags
research ──N:1── companies
users ──1:N── watchlists ──1:N── watchlist_items ──N:1── companies
users ──1:N── notifications
users ──0:N── audit_logs (actor, nullable)
users ──1:N── events
moderation_rules (standalone)
```

---

## 25. Migration Strategy

Per Architecture §17 Recommended Implementation Order and DB-001 (additive-only migrations), the dependency-ordered migration sequence for Alembic authoring (future work, not performed in this document) is:

1. Extensions (`pgcrypto`, `citext`, `pg_trgm`) + `set_updated_at()` function.
2. `users` → `profiles`.
3. `plans` → `subscriptions`.
4. `payments` → `invoices`.
5. `companies`.
6. `research` → `research_versions` → `research_sources` → `research_tags`.
7. `posts` → `comments` → `reactions` → `reports` → `bookmarks`.
8. `moderation_rules` → `moderation_actions`.
9. `watchlists` → `watchlist_items`.
10. `notifications`.
11. `audit_logs`.
12. `events`.

Each numbered step is one Alembic revision; within a step, table creation order follows FK dependency (a table is never created before a table it references). This is a literal restatement of Architecture §17's already-approved order — not a new sequencing decision.

**Additive-only discipline (DB-001):** every table above supports Phase 2 extension without breaking changes — e.g., `theses`/`guilds`/`courses` (Architecture §5.4, deferred) would be added as new tables with new FKs *into* these tables, never requiring a column to be dropped or a type changed on any table above. No Phase 2 table is created in this document, consistent with Architecture §5.4.

**Rollback:** each Alembic revision's `downgrade()` drops exactly what its `upgrade()` created, in reverse order — standard practice, noted here only because Architecture didn't need to specify it (it's a migration-authoring detail, not an architectural one) and this document is the first place it's relevant to mention.

**Environment-specific items deferred to deployment configuration** (not schema, per Section 0 above): the `REVOKE UPDATE, DELETE` grants for `audit_logs`/`moderation_actions`/`events`, since they require a concrete runtime role name that doesn't exist until deployment is configured.

---

## 26. Verification Against Architecture V1

- **Every table in Architecture §5.3 is represented above, plus one amendment:** `users, profiles, plans, subscriptions, payments, invoices, companies, research, research_versions, research_sources, research_tags, posts, comments, reactions, reports, moderation_actions, bookmarks, moderation_rules, watchlists, watchlist_items, notifications, audit_logs, events, compliance_acknowledgments` — **24 tables** (23 from the approved Architecture §5.3 + `compliance_acknowledgments` added by Amendment 1, 2026-08-29, pending a corresponding Architecture V1 amendment).
- **`title`/`summary` on `research` and `compliance_acknowledgments` are the two changes introduced by Amendment 1** — both are additive (new columns, new table), consistent with DB-001's additive-only discipline, and both trace to real gaps identified while deriving API Specification V1, not to a fresh product decision.
- **No other table, column, or constraint appears here that Architecture V1 did not already specify.** Every other CHECK constraint's value list, every FK, every index was copied from Architecture §5.3, not invented fresh.
- **No Phase 2/3 table** (`theses`, `guilds`, `courses`, etc.) appears — consistent with Architecture §5.4.
- **No product decision was reopened:** OD-09's event taxonomy, OD-05's role-array design, OD-08's `flag_for_review`-only constraint, AD-04's service-layer-only publish validation — all carried forward unchanged, not reconsidered.
- **This document is design-only:** no `alembic revision` was generated, no DDL was executed, no application code exists to reference this schema yet.

---

## 27. Amendment Log

| # | Date | Change | Reason | Status |
|---|---|---|---|---|
| 1 | 2026-08-29 | Added `research.title` (`NOT NULL`, ≤200 chars), `research.summary` (`NOT NULL`, ≤500 chars); corrected `ix_research_fts` to reference `title` instead of the non-existent `business_quality` column; added `compliance_acknowledgments` table | Founder review of API Specification V1 surfaced: (a) the API's own preview/library responses referenced `title`/`summary` fields that did not exist in this schema, (b) API Spec §12 item 2 self-flagged the missing acknowledgment-storage location for CMPL-004/005 | Applied to this document. **Architecture V1 §5.2/§5.3 has NOT yet been amended to match — this is a known, temporary inconsistency between the two approved documents, tracked here rather than silently left implicit, and should be closed before final API V1 lock.** |
| 2 | 2026-08-29 | Added `research.access_tier` (`TEXT NOT NULL DEFAULT 'core' CHECK (access_tier IN ('core', 'free_example'))`) | Founder Decision #1: MEM-004 requires FREE members to have full access to "selected research examples (curated, not the full library)" — verification found no field anywhere in the approved documents provided an authoritative way to identify such items, distinct from LIB-003's ordinary Core-only-preview rule. Founder approved `access_tier` as the classification field (Architecture AD-18). | Applied to this document, in the same amendment pass as the corresponding Architecture V1 amendment (Architecture §5.3, AD-18) — the two documents are consistent as of this row, unlike Amendment 1's temporary lag noted above. `access_tier` does not affect `status`/`moderation_status`/publish-time validation; who may set/change it remains an explicitly deferred, separate founder decision — no write endpoint exists for it yet in API Specification V1. |
| 3 | 2026-08-29 | **No schema change.** Verified that the existing `audit_logs` table (§22) fully supports recording `access_tier` changes without modification. | Founder Decision #2: who may change `research.access_tier` (Architecture AD-19) — resolved as ADMIN/SUPER_ADMIN only, audited. Per explicit instruction, this document was checked — not silently redesigned — before concluding no schema amendment was needed: `audit_logs.actor_id` (who), `target_entity_type='research'`/`target_entity_id` (which item), `before_state`/`after_state` JSONB (previous/new `access_tier` value), `created_at` (when) together satisfy every field Founder Decision #2 requires the audit record to capture. `moderation_actions` was considered and rejected as the audit home (its `action` CHECK constraint, §16, represents MOD-002's moderation vocabulary specifically — widening it for a non-moderation editorial action would blur that table's purpose; see Architecture AD-19 for the full reasoning). | **Verified sufficient, no amendment applied to this document.** This row exists to record that the check was performed, not to log a change — Database Schema V1's DDL is byte-for-byte unchanged by Founder Decision #2. |

This document remains internally correct as of Amendment 2; the Amendment 1 cross-document sync note above (Architecture V1 §5.2/§5.3 not yet amended to match, re: `title`/`summary`/`compliance_acknowledgments`) has since been resolved — Architecture V1's own header now confirms Amendment 1 was applied there as well — but this row is left as the historical record of when the lag existed, per the project's standing discipline of not silently rewriting prior log entries.

---

*QFinance Database Schema V1 — 🔒 APPROVED, founder confirmation 2026-08-29; Amendment 1 applied 2026-08-29 (`research.title`/`summary`, `compliance_acknowledgments`); Amendment 2 applied 2026-08-29 (Founder Decision #1, `research.access_tier`); Founder Decision #2 (2026-08-29) checked and confirmed to require no schema change (see Amendment Log row 3). Do not author or run actual Alembic migrations, and do not mark API Specification V1 locked.*
