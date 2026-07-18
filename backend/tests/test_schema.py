"""Phase 1 checkpoint audit (Implementation Plan, docs/06).

Verifies the live database against Backend Schema Document 05: every table and
column with its exact type, FK enforcement, the checkpoint-named indexes, and
the seed dataset. Needs a migrated database (skips if unreachable).
"""

import os

import pytest
import sqlalchemy as sa

URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://agentdesk:agentdesk@localhost:5432/agentdesk"
).replace("+asyncpg", "+psycopg2")

# column -> information_schema data_type, per Document 05 Section 1
U, T, TS, B, J, INT, N, V = (
    "uuid",
    "text",
    "timestamp with time zone",
    "boolean",
    "jsonb",
    "integer",
    "numeric",
    "USER-DEFINED",  # pgvector's `vector`
)
TOKEN_COLS = {
    "id": U,
    "user_id": U,
    "token_hash": T,
    "expires_at": TS,
    "used_at": TS,
    "created_at": TS,
}
EXPECTED = {
    "roles": {"id": U, "name": T, "created_at": TS},
    "teams": {"id": U, "name": T, "created_at": TS},
    "users": {
        "id": U,
        "email": T,
        "password_hash": T,
        "full_name": T,
        "role_id": U,
        "team_id": U,
        "is_active": B,
        "email_verified_at": TS,
        "notification_preferences": J,
        "theme_preference": T,
        "last_login_at": TS,
        "created_at": TS,
        "updated_at": TS,
    },
    "refresh_tokens": {
        "id": U,
        "user_id": U,
        "token_hash": T,
        "user_agent": T,
        "ip_address": T,
        "expires_at": TS,
        "revoked_at": TS,
        "created_at": TS,
    },
    "password_reset_tokens": TOKEN_COLS,
    "email_verification_tokens": TOKEN_COLS,
    "tickets": {
        "id": U,
        "display_id": INT,
        "subject": T,
        "description": T,
        "requester_id": U,
        "assignee_id": U,
        "category_id": U,
        "priority_id": U,
        "queue_id": U,
        "status": T,
        "channel": T,
        "source_email_message_id": T,
        "response_due_at": TS,
        "resolution_due_at": TS,
        "resolved_at": TS,
        "closed_at": TS,
        "reopened_count": INT,
        "merged_into_ticket_id": U,
        "created_at": TS,
        "updated_at": TS,
    },
    "comments": {
        "id": U,
        "ticket_id": U,
        "author_id": U,
        "body": T,
        "is_internal": B,
        "is_ai_generated": B,
        "ai_confidence": N,
        "created_at": TS,
        "updated_at": TS,
    },
    "comment_mentions": {"id": U, "comment_id": U, "mentioned_user_id": U, "created_at": TS},
    "attachments": {
        "id": U,
        "ticket_id": U,
        "comment_id": U,
        "uploader_id": U,
        "file_name": T,
        "storage_path": T,
        "mime_type": T,
        "size_bytes": INT,
        "version": INT,
        "replaced_by_attachment_id": U,
        "deleted_at": TS,
        "created_at": TS,
    },
    "tags": {"id": U, "name": T, "created_at": TS},
    "ticket_tags": {"ticket_id": U, "tag_id": U, "added_by": U, "created_at": TS},
    "categories": {"id": U, "name": T, "parent_id": U, "created_at": TS},
    "priorities": {"id": U, "name": T, "rank": INT, "color_hex": T, "created_at": TS},
    "queues": {"id": U, "name": T, "team_id": U, "created_at": TS},
    "sla_policies": {
        "id": U,
        "category_id": U,
        "priority_id": U,
        "response_minutes": INT,
        "resolution_minutes": INT,
        "created_at": TS,
        "updated_at": TS,
    },
    "automation_rules": {
        "id": U,
        "name": T,
        "trigger_type": T,
        "conditions": J,
        "actions": J,
        "priority": INT,
        "is_active": B,
        "created_by": U,
        "created_at": TS,
        "updated_at": TS,
    },
    "automation_execution_logs": {
        "id": U,
        "automation_rule_id": U,
        "ticket_id": U,
        "execution_status": T,
        "execution_started_at": TS,
        "execution_completed_at": TS,
        "error_message": T,
        "created_at": TS,
    },
    "ai_classification_history": {
        "id": U,
        "ticket_id": U,
        "predicted_category_id": U,
        "predicted_priority_id": U,
        "confidence": N,
        "confidence_tier": T,
        "model_version": T,
        "was_overridden": B,
        "overridden_by": U,
        "corrected_category_id": U,
        "corrected_priority_id": U,
        "created_at": TS,
    },
    "ai_draft_history": {
        "id": U,
        "ticket_id": U,
        "generated_by_model": T,
        "draft_content": T,
        "confidence_score": N,
        "review_status": T,
        "reviewed_by": U,
        "reviewed_at": TS,
        "final_comment_id": U,
        "created_at": TS,
    },
    "embeddings": {"id": U, "ticket_id": U, "source_model": T, "embedding": V, "created_at": TS},
    "conversation_history": {
        "id": U,
        "ticket_id": U,
        "session_id": T,
        "speaker": T,
        "message": T,
        "created_at": TS,
    },
    "knowledge_base_articles": {
        "id": U,
        "title": T,
        "body": T,
        "category_id": U,
        "status": T,
        "source_ticket_id": U,
        "author_id": U,
        "embedding": V,
        "published_at": TS,
        "created_at": TS,
        "updated_at": TS,
    },
    "notification_templates": {
        "id": U,
        "trigger_type": T,
        "channel": T,
        "subject_template": T,
        "body_template": T,
        "is_active": B,
        "created_by": U,
        "created_at": TS,
        "updated_at": TS,
    },
    "notifications": {
        "id": U,
        "user_id": U,
        "ticket_id": U,
        "template_id": U,
        "trigger_type": T,
        "channel": T,
        "is_read": B,
        "payload": J,
        "created_at": TS,
    },
    "saved_views": {"id": U, "user_id": U, "name": T, "filters": J, "created_at": TS},
    "csat_responses": {"id": U, "ticket_id": U, "rating": INT, "comment": T, "submitted_at": TS},
    "webhooks": {
        "id": U,
        "event_type": T,
        "target_url": T,
        "secret": T,
        "is_active": B,
        "created_by": U,
        "created_at": TS,
    },
    "webhook_deliveries": {
        "id": U,
        "webhook_id": U,
        "event_type": T,
        "payload": J,
        "response_status": INT,
        "attempt_count": INT,
        "delivered_at": TS,
        "created_at": TS,
    },
    "audit_logs": {
        "id": U,
        "entity_type": T,
        "entity_id": U,
        "actor_id": U,
        "action": T,
        "before_state": J,
        "after_state": J,
        "created_at": TS,
    },
    "ticket_status_history": {
        "id": U,
        "ticket_id": U,
        "old_status": T,
        "new_status": T,
        "changed_by": U,
        "changed_at": TS,
    },
}


@pytest.fixture(scope="module")
def conn():
    try:
        engine = sa.create_engine(URL)
        with engine.connect() as c:
            yield c
    except sa.exc.OperationalError:
        pytest.skip("database not reachable — run inside docker compose or set DATABASE_URL")


def test_every_table_and_column_matches_document_05(conn):
    rows = conn.execute(
        sa.text(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    ).all()
    actual: dict[str, dict[str, str]] = {}
    for table, col, dtype in rows:
        actual.setdefault(table, {})[col] = dtype
    actual.pop("alembic_version", None)
    assert set(actual) == set(EXPECTED), (
        f"missing: {set(EXPECTED) - set(actual)}, extra: {set(actual) - set(EXPECTED)}"
    )
    for table, cols in EXPECTED.items():
        assert actual[table] == cols, f"{table} mismatch: {actual[table]} != {cols}"


def test_documented_fk_is_enforced(conn):
    # Checkpoint: tickets.category_id pointing nowhere must be rejected
    requester = conn.execute(sa.text("SELECT id FROM users LIMIT 1")).scalar()
    with pytest.raises(sa.exc.IntegrityError, match="foreign key"):
        with conn.begin_nested():
            conn.execute(
                sa.text(
                    "INSERT INTO tickets (subject, description, requester_id, channel, "
                    "category_id) VALUES ('x', 'x', :r, 'portal', gen_random_uuid())"
                ),
                {"r": requester},
            )


def test_checkpoint_indexes_present(conn):
    idx = {
        t: set(
            r[0]
            for r in conn.execute(
                sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": t}
            )
        )
        for t in ("tickets", "comments", "embeddings")
    }
    for name in ("ix_tickets_status", "ix_tickets_fts", "ix_tickets_subject_trgm"):
        assert name in idx["tickets"]
    for name in ("ix_comments_ticket_id", "ix_comments_fts"):
        assert name in idx["comments"]
    assert "ix_embeddings_embedding_hnsw" in idx["embeddings"]
    assert any("ticket_id" in n for n in idx["embeddings"])  # unique one-per-ticket


def test_seed_produced_usable_demo_dataset(conn):
    counts = {
        t: conn.execute(sa.text(f"SELECT count(*) FROM {t}")).scalar()  # noqa: S608 — fixed table names
        for t in ("roles", "users", "priorities", "sla_policies", "queues", "categories")
    }
    assert counts["roles"] == 4
    assert counts["users"] >= 4
    assert counts["priorities"] == 4
    assert counts["sla_policies"] == 4  # one per priority
    assert counts["queues"] >= 1
    assert counts["categories"] >= 4  # tree with parents + children
    roles = {r[0] for r in conn.execute(sa.text("SELECT name FROM roles"))}
    assert roles == {"requester", "agent", "team_lead", "admin"}
