# QFinance Database Schema V2

**Status:** 🟢 ACTIVE — additive delta on top of QFINANCE_DATABASE_SCHEMA_V1.md. All V1 tables/columns/constraints remain exactly as documented there unless explicitly listed as changed below. No V1 table is dropped or renamed.

## 1. New Tables

### `journal_entries`
```sql
CREATE TABLE journal_entries (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    company_id UUID NULL REFERENCES companies(id),
    entry_type TEXT NOT NULL CHECK (entry_type IN ('decision','reasoning','observation','note')),
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 10000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX ix_journal_entries_user ON journal_entries(user_id, created_at DESC);
```
Never joined from any `community` query. Soft-delete, matching V1's convention for user-generated content.

### `broker_connections`
```sql
CREATE TABLE broker_connections (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    broker TEXT NOT NULL CHECK (broker = 'zerodha'),   -- MVP: single value, extensible later
    status TEXT NOT NULL CHECK (status IN ('connected','disconnected','error')),
    access_token TEXT NULL,        -- NEVER returned via any API response; server-side only
    kite_user_id TEXT NULL,
    connected_at TIMESTAMPTZ NULL,
    last_synced_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, broker)
);
```
`access_token` is application-layer-encrypted-at-rest is a recommended hardening, NOT implemented in MVP (flagged as a known gap, matching V1's own precedent of flagging deferred hardening rather than silently skipping the note).

### `ratings`
```sql
CREATE TABLE ratings (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    post_id UUID NOT NULL REFERENCES posts(id),
    score SMALLINT NOT NULL CHECK (score BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, post_id)
);
```
Enforcement that `post_id` refers to a `post_type='thesis'` post, and that `user_id != posts.author_id`, both happen at the application layer (a DB CHECK can't express a cross-table join condition without a trigger, and V1 has no precedent of using triggers — kept consistent).

### `contributions` (Phase 5/P1 — append-only, mirrors `events`)
```sql
CREATE TABLE contributions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    source_type TEXT NOT NULL CHECK (source_type IN ('thesis_published','engagement_received','rating_received')),
    source_entity_id UUID NOT NULL,
    points INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `credit_ledger` (Phase 5/P1)
```sql
CREATE TABLE credit_ledger (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    amount_paise INTEGER NOT NULL,
    reason TEXT NOT NULL,
    contribution_id UUID NULL REFERENCES contributions(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 2. Changed Existing Tables (additive columns only)

### `posts` (V1 table, unchanged columns kept as-is)
```sql
ALTER TABLE posts ADD COLUMN post_type TEXT NOT NULL DEFAULT 'general'
    CHECK (post_type IN ('general','thesis','question','discussion'));
```
`channel` remains nullable exactly as in V1 (a post can have a `post_type` and optionally still a `channel`); `research_id` (V1, nullable) is reused as-is per Architecture V2 §5 — no new column needed for the thesis bridge.

### `comments` (V1 table)
```sql
ALTER TABLE comments ADD COLUMN parent_comment_id UUID NULL REFERENCES comments(id);
CREATE INDEX ix_comments_parent ON comments(parent_comment_id);
```
`parent_comment_id IS NULL` means a top-level comment (unchanged V1 behavior); non-null means a reply. No depth limit at the DB layer (Architecture V2 §4).

## 3. Deferred / Explicitly Not Built This Phase
- No materialized rating-aggregate column on `posts` (computed at read time, Architecture V2 §6).
- No `broker_connections.access_token` encryption-at-rest (flagged, not implemented).
- No `watchlist`/`notifications`/`admin` tables — pre-existing V1 gap, unrelated to this restructure, still open.
