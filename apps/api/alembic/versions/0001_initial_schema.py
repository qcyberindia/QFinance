"""Initial MVP schema — full translation of Database Schema V1 (Architecture §5.3).

WRITTEN, NOT EXECUTED — `alembic upgrade head` has never run against a real
PostgreSQL instance in this session. This file has not been syntax-checked by a
real Python interpreter either; treat it as a first-pass draft to review before
running, not as verified-working DDL.

Revision ID: 0001
Revises:
Create Date: 2026-08-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", pg.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("is_anonymized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active','suspended','deleted')", name="ck_users_status"),
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("username", pg.CITEXT(), nullable=False, unique=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("experience_level", sa.Text(), nullable=True),
        sa.Column("interests", pg.ARRAY(sa.Text()), nullable=True),
        sa.Column("role_grants", pg.ARRAY(sa.Text()), nullable=False, server_default="{FREE_MEMBER}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "experience_level IS NULL OR experience_level IN ('beginner','intermediate','advanced')",
            name="ck_profiles_experience_level",
        ),
    )

    op.create_table(
        "compliance_acknowledgments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acknowledgment_type", sa.Text(), nullable=False),
        sa.Column("document_version", sa.Text(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "acknowledgment_type IN ('member_charter','risk_disclosure')", name="ck_compliance_ack_type"
        ),
    )

    op.create_table(
        "plans",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("price_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="INR"),
        sa.Column("billing_interval", sa.Text(), nullable=False, server_default="monthly"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("code IN ('FREE','CORE')", name="ck_plans_code"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", pg.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gateway_subscription_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','past_due','canceled','expired')", name="ck_subscriptions_status"),
    )
    op.create_index("ix_subscriptions_user_status", "subscriptions", ["user_id", "status"])

    op.create_table(
        "payments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subscription_id", pg.UUID(as_uuid=True), sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("gateway_reference_id", sa.Text(), nullable=False, unique=True),
        sa.Column("billing_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending','succeeded','failed','refunded')", name="ck_payments_status"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_id", pg.UUID(as_uuid=True), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("tax_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.CHAR(3), nullable=False, server_default="INR"),
        sa.Column("payment_status", sa.Text(), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("billing_period", sa.Text(), nullable=False),
        sa.Column("gateway_reference", sa.Text(), nullable=False),
        sa.Column("tax_treatment_version", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "companies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_merged_into", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("exchange IN ('NSE','BSE','OTHER_RECOGNIZED')", name="ck_companies_exchange"),
    )
    op.execute("CREATE INDEX ix_companies_name_trgm ON companies USING GIN (name gin_trgm_ops)")

    op.create_table(
        "research",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("author_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("research_type", sa.Text(), nullable=False),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("moderation_status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("access_tier", sa.Text(), nullable=False, server_default="core"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("business_quality", sa.Text(), nullable=True),
        sa.Column("financial_snapshot", sa.Text(), nullable=True),
        sa.Column("business_model", sa.Text(), nullable=True),
        sa.Column("competitive_position", sa.Text(), nullable=True),
        sa.Column("valuation_range", sa.Text(), nullable=True),
        sa.Column("bull_case", sa.Text(), nullable=True),
        sa.Column("base_case", sa.Text(), nullable=True),
        sa.Column("bear_case", sa.Text(), nullable=True),
        sa.Column("risk_register", sa.Text(), nullable=True),
        sa.Column("catalysts", sa.Text(), nullable=True),
        sa.Column("invalidation_conditions", sa.Text(), nullable=True),
        sa.Column("conflict_disclosed", sa.Boolean(), nullable=True),
        sa.Column("conflict_detail", sa.Text(), nullable=True),
        sa.Column("position_disclosed", sa.Boolean(), nullable=True),
        sa.Column("position_detail", sa.Text(), nullable=True),
        sa.Column("research_date", sa.Date(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft','published')", name="ck_research_status"),
        sa.CheckConstraint("moderation_status IN ('active','restricted','removed')", name="ck_research_mod_status"),
        sa.CheckConstraint("access_tier IN ('core','free_example')", name="ck_research_access_tier"),
    )
    op.create_index("ix_research_company", "research", ["company_id"])
    op.create_index("ix_research_status", "research", ["status"])

    op.create_table(
        "research_versions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("research_id", pg.UUID(as_uuid=True), sa.ForeignKey("research.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", pg.JSONB(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False),
        sa.Column("edited_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("research_id", "version_number", name="ux_research_versions_research_version"),
    )

    op.create_table(
        "research_sources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("research_id", pg.UUID(as_uuid=True), sa.ForeignKey("research.id"), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("supports_claim", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "research_tags",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("research_id", pg.UUID(as_uuid=True), sa.ForeignKey("research.id"), nullable=False),
        sa.Column("tag", pg.CITEXT(), nullable=False),
        sa.UniqueConstraint("research_id", "tag", name="ux_research_tags_research_tag"),
    )

    op.create_table(
        "posts",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("author_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("research_id", pg.UUID(as_uuid=True), sa.ForeignKey("research.id"), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="visible"),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "channel IS NULL OR channel IN "
            "('announcements','general_discussion','research_discussion','market_discussion',"
            "'learning','help_questions','off_topic')",
            name="ck_posts_channel",
        ),
        sa.CheckConstraint("channel IS NOT NULL OR research_id IS NOT NULL", name="ck_posts_channel_or_research"),
        sa.CheckConstraint("status IN ('visible','restricted','removed')", name="ck_posts_status"),
    )
    op.create_index("ix_posts_channel", "posts", ["channel"])
    op.create_index("ix_posts_research", "posts", ["research_id"])

    op.create_table(
        "comments",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("post_id", pg.UUID(as_uuid=True), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("author_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="visible"),
        sa.Column("is_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('visible','restricted','removed')", name="ck_comments_status"),
    )

    op.create_table(
        "reactions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reaction_type", sa.Text(), nullable=False, server_default="like"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_type IN ('post','comment')", name="ck_reactions_target_type"),
        sa.CheckConstraint("reaction_type = 'like'", name="ck_reactions_type"),
        sa.UniqueConstraint("user_id", "target_type", "target_id", "reaction_type", name="ux_reactions_unique"),
    )

    op.create_table(
        "reports",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("reporter_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("resolution_action", sa.Text(), nullable=True),
        sa.Column("resolved_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_type IN ('post','comment','research')", name="ck_reports_target_type"),
        sa.CheckConstraint("status IN ('open','resolved')", name="ck_reports_status"),
    )

    op.create_table(
        "moderation_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("moderator_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("report_id", pg.UUID(as_uuid=True), sa.ForeignKey("reports.id"), nullable=True),
        sa.Column("previous_state", sa.Text(), nullable=True),
        sa.Column("new_state", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("target_type IN ('post','comment','research','member')", name="ck_mod_actions_target_type"),
        sa.CheckConstraint(
            "action IN ('approve','edit','restrict','remove','reinstate','suspend_member','reinstate_member')",
            name="ck_mod_actions_action",
        ),
    )
    op.create_index("ix_mod_actions_target", "moderation_actions", ["target_type", "target_id"])

    op.create_table(
        "moderation_rules",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("phrase", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("action", sa.Text(), nullable=False, server_default="flag_for_review"),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("severity IN ('low','medium','high')", name="ck_mod_rules_severity"),
        sa.CheckConstraint("action = 'flag_for_review'", name="ck_mod_rules_action"),
    )

    op.create_table(
        "bookmarks",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("post_id", pg.UUID(as_uuid=True), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "post_id", name="ux_bookmarks_user_post"),
    )

    op.create_table(
        "watchlists",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "watchlist_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("watchlist_id", pg.UUID(as_uuid=True), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("company_id", pg.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("watchlist_id", "company_id", name="ux_watchlist_items_watchlist_company"),
    )

    op.create_table(
        "notifications",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "type IN ('comment_on_content','reaction_on_content','report_resolved',"
            "'moderation_action','subscription_change')",
            name="ck_notifications_type",
        ),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actor_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("target_entity_type", sa.Text(), nullable=False),
        sa.Column("target_entity_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", pg.JSONB(), nullable=True),
        sa.Column("after_state", pg.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "events",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", pg.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_type IN ('signup','email_verified','login','payment_completed',"
            "'research_draft_created','research_draft_updated','research_section_completed',"
            "'research_source_added','research_published','research_commented','post_created',"
            "'watchlist_added')",
            name="ck_events_type",
        ),
    )
    op.create_index("ix_events_user_type_created", "events", ["user_id", "event_type", "created_at"])
    op.create_index("ix_events_type_created", "events", ["event_type", "created_at"])

    # Seed the two locked plans (MEM-001, OD-22) — price is a system value, not app-hardcoded.
    op.execute(
        "INSERT INTO plans (code, price_paise, currency, billing_interval) VALUES "
        "('FREE', 0, 'INR', 'monthly'), ('CORE', 79900, 'INR', 'monthly')"
    )


def downgrade() -> None:
    for table in (
        "events", "audit_logs", "notifications", "watchlist_items", "watchlists", "bookmarks",
        "moderation_rules", "moderation_actions", "reports", "reactions", "comments", "posts",
        "research_tags", "research_sources", "research_versions", "research", "companies",
        "invoices", "payments", "subscriptions", "plans", "compliance_acknowledgments",
        "profiles", "users",
    ):
        op.drop_table(table)
