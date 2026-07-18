"""Initial schema — every table, FK, and index from Backend Schema Document 05.

Revision ID: 0001
Revises:
Create Date: 2026-07-18
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# ponytail: vector(1536) is the doc's illustrative placeholder — Phase 5 revises
# this dimension when the embedding provider is finalized.
EMBEDDING_DIM = 1536


def _pk():
    return sa.Column(
        "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def _ts(name, nullable=False, default=True):
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if default and not nullable else None,
    )


def _fk(name, target, nullable=False, unique=False):
    return sa.Column(
        name, UUID(as_uuid=True), sa.ForeignKey(target), nullable=nullable, unique=unique
    )


def upgrade() -> None:
    # --- Identity & Access ---
    op.create_table(
        "roles",
        _pk(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        _ts("created_at"),
    )
    op.create_table(
        "teams",
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("full_name", sa.Text, nullable=False),
        _fk("role_id", "roles.id"),
        _fk("team_id", "teams.id", nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _ts("email_verified_at", nullable=True),
        sa.Column(
            "notification_preferences", JSONB, nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("theme_preference", sa.Text, nullable=False, server_default=sa.text("'system'")),
        _ts("last_login_at", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    for table in ("refresh_tokens", "password_reset_tokens", "email_verification_tokens"):
        extra = (
            [
                sa.Column("user_agent", sa.Text, nullable=True),
                sa.Column("ip_address", sa.Text, nullable=True),
            ]
            if table == "refresh_tokens"
            else []
        )
        end = (
            [_ts("revoked_at", nullable=True)]
            if table == "refresh_tokens"
            else [_ts("used_at", nullable=True)]
        )
        op.create_table(
            table,
            _pk(),
            _fk("user_id", "users.id"),
            sa.Column("token_hash", sa.Text, nullable=False, unique=True),
            *extra,
            _ts("expires_at", nullable=False, default=False),
            *end,
            _ts("created_at"),
        )

    # --- Classification & Configuration (before tickets, which FK into these) ---
    op.create_table(
        "categories",
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        _fk("parent_id", "categories.id", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "priorities",
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("color_hex", sa.Text, nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "queues",
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        _fk("team_id", "teams.id", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "sla_policies",
        _pk(),
        _fk("category_id", "categories.id", nullable=True),
        _fk("priority_id", "priorities.id"),
        sa.Column("response_minutes", sa.Integer, nullable=False),
        sa.Column("resolution_minutes", sa.Integer, nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "automation_rules",
        _pk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("trigger_type", sa.Text, nullable=False),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("actions", JSONB, nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _fk("created_by", "users.id"),
        _ts("created_at"),
        _ts("updated_at"),
    )

    # --- Ticket Core ---
    op.create_table(
        "tickets",
        _pk(),
        sa.Column("display_id", sa.Integer, sa.Identity(), nullable=False, unique=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        _fk("requester_id", "users.id"),
        _fk("assignee_id", "users.id", nullable=True),
        _fk("category_id", "categories.id", nullable=True),
        _fk("priority_id", "priorities.id", nullable=True),
        _fk("queue_id", "queues.id", nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'new'")),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("source_email_message_id", sa.Text, nullable=True),
        _ts("response_due_at", nullable=True),
        _ts("resolution_due_at", nullable=True),
        _ts("resolved_at", nullable=True),
        _ts("closed_at", nullable=True),
        sa.Column("reopened_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        _fk("merged_into_ticket_id", "tickets.id", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "comments",
        _pk(),
        _fk("ticket_id", "tickets.id"),
        _fk("author_id", "users.id", nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_internal", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_ai_generated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("ai_confidence", sa.Numeric(5, 2), nullable=True),
        _ts("created_at"),
        _ts("updated_at", nullable=True),
    )
    op.create_table(
        "comment_mentions",
        _pk(),
        _fk("comment_id", "comments.id"),
        _fk("mentioned_user_id", "users.id"),
        _ts("created_at"),
    )
    op.create_table(
        "attachments",
        _pk(),
        _fk("ticket_id", "tickets.id"),
        _fk("comment_id", "comments.id", nullable=True),
        _fk("uploader_id", "users.id"),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("mime_type", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _fk("replaced_by_attachment_id", "attachments.id", nullable=True),
        _ts("deleted_at", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "tags",
        _pk(),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        _ts("created_at"),
    )
    op.create_table(
        "ticket_tags",
        sa.Column("ticket_id", UUID(as_uuid=True), sa.ForeignKey("tickets.id"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id"), primary_key=True),
        _fk("added_by", "users.id", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "automation_execution_logs",
        _pk(),
        _fk("automation_rule_id", "automation_rules.id"),
        _fk("ticket_id", "tickets.id", nullable=True),
        sa.Column("execution_status", sa.Text, nullable=False),
        _ts("execution_started_at", nullable=False, default=False),
        _ts("execution_completed_at", nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        _ts("created_at"),
    )

    # --- AI & Knowledge ---
    op.create_table(
        "ai_classification_history",
        _pk(),
        _fk("ticket_id", "tickets.id"),
        _fk("predicted_category_id", "categories.id", nullable=True),
        _fk("predicted_priority_id", "priorities.id", nullable=True),
        sa.Column("confidence", sa.Numeric(5, 2), nullable=False),
        sa.Column("confidence_tier", sa.Text, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("was_overridden", sa.Boolean, nullable=False, server_default=sa.text("false")),
        _fk("overridden_by", "users.id", nullable=True),
        _fk("corrected_category_id", "categories.id", nullable=True),
        _fk("corrected_priority_id", "priorities.id", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "ai_draft_history",
        _pk(),
        _fk("ticket_id", "tickets.id"),
        sa.Column("generated_by_model", sa.Text, nullable=False),
        sa.Column("draft_content", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("review_status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        _fk("reviewed_by", "users.id", nullable=True),
        _ts("reviewed_at", nullable=True),
        _fk("final_comment_id", "comments.id", nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "embeddings",
        _pk(),
        _fk("ticket_id", "tickets.id", unique=True),
        sa.Column("source_model", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "conversation_history",
        _pk(),
        _fk("ticket_id", "tickets.id", nullable=True),
        sa.Column("session_id", sa.Text, nullable=False),
        sa.Column("speaker", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "knowledge_base_articles",
        _pk(),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        _fk("category_id", "categories.id", nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'draft'")),
        _fk("source_ticket_id", "tickets.id", nullable=True),
        _fk("author_id", "users.id", nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        _ts("published_at", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )

    # --- Engagement & Ops ---
    op.create_table(
        "notification_templates",
        _pk(),
        sa.Column("trigger_type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("subject_template", sa.Text, nullable=True),
        sa.Column("body_template", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _fk("created_by", "users.id"),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_table(
        "notifications",
        _pk(),
        _fk("user_id", "users.id"),
        _fk("ticket_id", "tickets.id", nullable=True),
        _fk("template_id", "notification_templates.id", nullable=True),
        sa.Column("trigger_type", sa.Text, nullable=False),
        sa.Column("channel", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("payload", JSONB, nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "saved_views",
        _pk(),
        _fk("user_id", "users.id"),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("filters", JSONB, nullable=False),
        _ts("created_at"),
    )
    op.create_table(
        "csat_responses",
        _pk(),
        _fk("ticket_id", "tickets.id", unique=True),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        _ts("submitted_at", nullable=False, default=False),
    )
    op.create_table(
        "webhooks",
        _pk(),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("target_url", sa.Text, nullable=False),
        sa.Column("secret", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        _fk("created_by", "users.id"),
        _ts("created_at"),
    )
    op.create_table(
        "webhook_deliveries",
        _pk(),
        _fk("webhook_id", "webhooks.id"),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("1")),
        _ts("delivered_at", nullable=True),
        _ts("created_at"),
    )

    # --- Governance ---
    op.create_table(
        "audit_logs",
        _pk(),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        _fk("actor_id", "users.id", nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("before_state", JSONB, nullable=True),
        sa.Column("after_state", JSONB, nullable=True),
        _ts("created_at"),
    )
    op.create_table(
        "ticket_status_history",
        _pk(),
        _fk("ticket_id", "tickets.id"),
        sa.Column("old_status", sa.Text, nullable=True),
        sa.Column("new_status", sa.Text, nullable=False),
        _fk("changed_by", "users.id", nullable=True),
        _ts("changed_at", nullable=False, default=False),
    )

    # --- Indexes (Document 05, Section 4; unique indexes come from the column
    # constraints above) ---
    op.create_index("ix_users_role_id", "users", ["role_id"])
    op.create_index("ix_users_team_id", "users", ["team_id"])
    op.create_index(
        "ix_users_is_active", "users", ["is_active"], postgresql_where=sa.text("is_active")
    )
    for col in (
        "requester_id",
        "assignee_id",
        "category_id",
        "priority_id",
        "queue_id",
        "status",
        "created_at",
    ):
        op.create_index(f"ix_tickets_{col}", "tickets", [col])
    op.create_index(
        "ix_tickets_fts",
        "tickets",
        [sa.text("to_tsvector('english', subject || ' ' || description)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_tickets_subject_trgm",
        "tickets",
        [sa.text("subject gin_trgm_ops")],
        postgresql_using="gin",
    )
    op.create_index("ix_comments_ticket_id", "comments", ["ticket_id"])
    op.create_index("ix_comments_author_id", "comments", ["author_id"])
    op.create_index(
        "ix_comments_fts",
        "comments",
        [sa.text("to_tsvector('english', body)")],
        postgresql_using="gin",
    )
    op.create_index("ix_comment_mentions_comment_id", "comment_mentions", ["comment_id"])
    op.create_index(
        "ix_comment_mentions_mentioned_user_id", "comment_mentions", ["mentioned_user_id"]
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index(
        "ix_sla_policies_category_priority", "sla_policies", ["category_id", "priority_id"]
    )
    op.create_index("ix_automation_rules_trigger_type", "automation_rules", ["trigger_type"])
    op.create_index("ix_automation_rules_is_active", "automation_rules", ["is_active"])
    op.create_index(
        "ix_automation_execution_logs_rule_id", "automation_execution_logs", ["automation_rule_id"]
    )
    op.create_index(
        "ix_automation_execution_logs_ticket_id", "automation_execution_logs", ["ticket_id"]
    )
    op.create_index(
        "ix_automation_execution_logs_status", "automation_execution_logs", ["execution_status"]
    )
    op.create_index(
        "ix_ai_classification_history_ticket_id", "ai_classification_history", ["ticket_id"]
    )
    op.create_index("ix_ai_draft_history_ticket_id", "ai_draft_history", ["ticket_id"])
    op.create_index("ix_ai_draft_history_review_status", "ai_draft_history", ["review_status"])
    op.create_index("ix_ai_draft_history_reviewed_by", "ai_draft_history", ["reviewed_by"])
    op.create_index(
        "ix_embeddings_embedding_hnsw",
        "embeddings",
        [sa.text("embedding vector_cosine_ops")],
        postgresql_using="hnsw",
    )
    op.create_index(
        "ix_kb_articles_fts",
        "knowledge_base_articles",
        [sa.text("to_tsvector('english', title || ' ' || body)")],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_kb_articles_embedding_hnsw",
        "knowledge_base_articles",
        [sa.text("embedding vector_cosine_ops")],
        postgresql_using="hnsw",
    )
    op.create_index("ix_kb_articles_status", "knowledge_base_articles", ["status"])
    op.create_index("ix_conversation_history_ticket_id", "conversation_history", ["ticket_id"])
    op.create_index("ix_conversation_history_session_id", "conversation_history", ["session_id"])
    op.create_index(
        "ix_notification_templates_trigger_channel",
        "notification_templates",
        ["trigger_type", "channel"],
    )
    op.create_index(
        "ix_notification_templates_is_active",
        "notification_templates",
        ["is_active"],
        postgresql_where=sa.text("is_active"),
    )
    op.create_index("ix_notifications_template_id", "notifications", ["template_id"])
    op.create_index("ix_notifications_user_id_is_read", "notifications", ["user_id", "is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_ticket_status_history_ticket_id", "ticket_status_history", ["ticket_id"])
    op.create_index("ix_ticket_status_history_changed_at", "ticket_status_history", ["changed_at"])
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])

    # Fixed role vocabulary (Implementation Plan, Phase 1)
    op.execute("INSERT INTO roles (name) VALUES ('requester'), ('agent'), ('team_lead'), ('admin')")


def downgrade() -> None:
    for table in (
        "ticket_status_history",
        "audit_logs",
        "webhook_deliveries",
        "webhooks",
        "csat_responses",
        "saved_views",
        "notifications",
        "notification_templates",
        "knowledge_base_articles",
        "conversation_history",
        "embeddings",
        "ai_draft_history",
        "ai_classification_history",
        "automation_execution_logs",
        "ticket_tags",
        "tags",
        "attachments",
        "comment_mentions",
        "comments",
        "tickets",
        "automation_rules",
        "sla_policies",
        "queues",
        "priorities",
        "categories",
        "email_verification_tokens",
        "password_reset_tokens",
        "refresh_tokens",
        "users",
        "teams",
        "roles",
    ):
        op.drop_table(table)
