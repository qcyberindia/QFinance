"""Add the research/companies full-text-search indexes and research title/
summary length CHECK constraints that Database Schema V1 §7 ('companies')
and §8 ('research') already specify but that were missing from
0001_initial_schema.py.

This is a corrective, additive migration, not a new design decision — every
statement below is copied verbatim (mechanism, columns, bounds) from the
locked Database Schema V1 document:
  - Database Schema V1 §7 `companies`:
      CREATE INDEX ix_companies_name_fts ON companies
        USING GIN (to_tsvector('english', name));
  - Database Schema V1 §8 `research`:
      title   TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200)
      summary TEXT NOT NULL CHECK (char_length(summary) BETWEEN 1 AND 500)
      CREATE INDEX ix_research_fts ON research
        USING GIN (to_tsvector('english',
                                coalesce(title, '') || ' ' || coalesce(business_model, '')));

Per Database Schema V1 Amendment Log row 1, the `ix_research_fts` expression
literally concatenates `title` and `business_model` (not `summary`, not
`research_tags.tag`, not `companies.name`) — that is the exact locked
expression, carried forward unchanged here rather than "corrected" to match
API Specification V1 §7.4.2's prose description of search scope
("title, company name, tags"). That prose/DDL tension is a genuine,
pre-existing inconsistency between two locked/approved documents; it is
flagged in work_memory.md, not silently resolved by changing either document
here. `research_tags.tag` and `companies.name` are searched by the service
layer via the indexes that DO cover them (this migration's
`ix_companies_name_fts` for company name; `research_tags` has no FTS index in
any approved document, so tag matching remains a direct equality/ILIKE
lookup on that table, unchanged).

WRITTEN, NOT EXECUTED — `alembic upgrade head` has not been run against a
real PostgreSQL instance in this session. This file has not been executed by
a real interpreter either; syntax-reviewed only.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-01
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Database Schema V1 §8 `research` — length CHECK constraints (missing from 0001).
    op.execute(
        "ALTER TABLE research ADD CONSTRAINT ck_research_title_length "
        "CHECK (char_length(title) BETWEEN 1 AND 200)"
    )
    op.execute(
        "ALTER TABLE research ADD CONSTRAINT ck_research_summary_length "
        "CHECK (char_length(summary) BETWEEN 1 AND 500)"
    )

    # Database Schema V1 §8 `research` — GIN full-text-search index (exact locked expression).
    op.execute(
        "CREATE INDEX ix_research_fts ON research "
        "USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(business_model, '')))"
    )

    # Database Schema V1 §7 `companies` — GIN full-text-search index on name
    # (companies already has ix_companies_name_trgm from 0001; this adds the
    # separate FTS index the schema also specifies alongside it).
    op.execute(
        "CREATE INDEX ix_companies_name_fts ON companies "
        "USING GIN (to_tsvector('english', name))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_companies_name_fts")
    op.execute("DROP INDEX IF EXISTS ix_research_fts")
    op.execute("ALTER TABLE research DROP CONSTRAINT IF EXISTS ck_research_summary_length")
    op.execute("ALTER TABLE research DROP CONSTRAINT IF EXISTS ck_research_title_length")
