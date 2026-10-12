"""Create application metadata schemas and tables.

Revision ID: 0001_app_schema
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0001_app_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA app")
    op.execute("CREATE SCHEMA analytics")
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("scope_profile", sa.String(8), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("role IN ('builder', 'viewer')", name="ck_users_role"),
        sa.CheckConstraint("scope_profile IN ('ALL', 'CA', 'TX')", name="ck_users_scope"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        schema="app",
    )
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema="app",
    )
    op.create_index("ix_sessions_user_expires", "sessions", ["user_id", "expires_at"], schema="app")
    op.create_table(
        "dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        schema="app",
    )
    op.create_index("ix_dashboards_owner", "dashboards", ["owner_user_id"], schema="app")
    op.create_table(
        "dashboard_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.dashboards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("base_version_number", sa.Integer()),
        sa.Column("draft_hash", sa.String(64), nullable=False),
        sa.Column("approval_key", sa.String(128), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_dashboard_versions_number"),
        sa.CheckConstraint("base_version_number IS NULL OR base_version_number >= 0", name="ck_dashboard_versions_base"),
        sa.UniqueConstraint("id", "dashboard_id", name="uq_dashboard_versions_identity_dashboard"),
        sa.UniqueConstraint("dashboard_id", "version_number", name="uq_dashboard_versions_number"),
        sa.UniqueConstraint("dashboard_id", "draft_hash", name="uq_dashboard_versions_draft_hash"),
        sa.UniqueConstraint("approval_key", name="uq_dashboard_versions_approval_key"),
        schema="app",
    )
    op.create_foreign_key(
        "fk_dashboards_current_version_same_dashboard",
        "dashboards",
        "dashboard_versions",
        ["current_version_id", "id"],
        ["id", "dashboard_id"],
        source_schema="app",
        referent_schema="app",
    )
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.dashboards.id", ondelete="SET NULL")),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("draft_revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("draft_hash", sa.String(64)),
        sa.Column("base_version_number", sa.Integer()),
        sa.Column("draft_spec", postgresql.JSONB()),
        *timestamps(),
        sa.CheckConstraint("status IN ('running','needs_clarification','awaiting_approval','completed','failed')", name="ck_conversations_status"),
        sa.CheckConstraint("draft_revision >= 0", name="ck_conversations_revision"),
        sa.UniqueConstraint("thread_id", name="uq_conversations_thread"),
        schema="app",
    )
    op.create_index("ix_conversations_owner_updated", "conversations", ["owner_user_id", "updated_at"], schema="app")
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        schema="app",
    )
    op.create_index("ix_messages_conversation_created", "conversation_messages", ["conversation_id", "created_at"], schema="app")
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("thread_id", sa.String(128), nullable=False),
        sa.Column("checkpoint_namespace", sa.String(128), server_default="", nullable=False),
        sa.Column("checkpoint_id", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("thread_id", "checkpoint_namespace", "checkpoint_id", name="uq_checkpoints_identity"),
        schema="app",
    )
    op.create_index("ix_checkpoints_conversation_created", "agent_checkpoints", ["conversation_id", "created_at"], schema="app")
    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("query_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("llm_calls >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND estimated_cost_usd >= 0 AND query_count >= 0 AND latency_ms >= 0", name="ck_usage_nonnegative"),
        sa.UniqueConstraint("run_id", name="uq_usage_run"),
        schema="app",
    )
    op.create_index("ix_usage_user_day", "usage_records", ["user_id", "usage_date"], schema="app")
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app.users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128)),
        sa.Column("details", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="app",
    )
    op.create_index("ix_audit_actor_created", "audit_events", ["actor_user_id", "created_at"], schema="app")
    op.create_index("ix_audit_target", "audit_events", ["target_type", "target_id"], schema="app")


def downgrade() -> None:
    op.drop_table("audit_events", schema="app")
    op.drop_table("usage_records", schema="app")
    op.drop_table("agent_checkpoints", schema="app")
    op.drop_table("conversation_messages", schema="app")
    op.drop_table("conversations", schema="app")
    op.drop_constraint("fk_dashboards_current_version_same_dashboard", "dashboards", schema="app", type_="foreignkey")
    op.drop_table("dashboard_versions", schema="app")
    op.drop_table("dashboards", schema="app")
    op.drop_table("sessions", schema="app")
    op.drop_table("users", schema="app")
    op.execute("DROP SCHEMA analytics")
    op.execute("DROP SCHEMA app")
