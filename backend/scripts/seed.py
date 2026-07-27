"""Local dev seed (Implementation Plan, Phase 1).

One demo user per role, a small category tree, default priorities (rank +
color_hex per Document 04's semantic colors), one queue, one SLA policy per
priority. Run after `alembic upgrade head`:

    python -m scripts.seed          # from backend/ or inside the backend container
"""

import uuid

import bcrypt
import sqlalchemy as sa

from app.config import get_settings
from app.notifications.templates import default_templates

DEMO_PASSWORD = "Password123!"

# ponytail: SLA minutes are placeholders — final thresholds are a flagged open
# decision (docs/06, Phase 5/16); resolve there, don't trust these numbers.
SLA_MINUTES = {"Critical": (30, 240), "High": (60, 480), "Medium": (240, 1440), "Low": (480, 2880)}

# name, rank, color_hex — colors from Document 04's semantic palette
PRIORITIES = [
    ("Low", 1, "#34D399"),
    ("Medium", 2, "#8A93A6"),
    ("High", 3, "#F5A623"),
    ("Critical", 4, "#F05252"),
]

CATEGORY_TREE = {
    "Billing": ["Refunds", "Invoices"],
    "Technical Support": ["Login Issues", "Bug Report"],
    "General": [],
}


def _seed_notification_templates(conn) -> int:
    """One default template per (trigger_type, channel), idempotent (Phase 7).

    Created by the demo admin; skipped for any pair that already has a row so
    re-running never duplicates or clobbers Admin edits.
    """
    admin_id = conn.execute(
        sa.text(
            "SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE r.name = 'admin' LIMIT 1"
        )
    ).scalar()
    if admin_id is None:
        return 0
    inserted = 0
    for row in default_templates():
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM notification_templates "
                "WHERE trigger_type = :t AND channel = :c LIMIT 1"
            ),
            {"t": row["trigger_type"], "c": row["channel"]},
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO notification_templates "
                "(trigger_type, channel, subject_template, body_template, created_by) "
                "VALUES (:t, :c, :s, :b, :admin)"
            ),
            {
                "t": row["trigger_type"],
                "c": row["channel"],
                "s": row["subject_template"],
                "b": row["body_template"],
                "admin": admin_id,
            },
        )
        inserted += 1
    return inserted


def main() -> None:
    engine = sa.create_engine(get_settings().database_url.replace("+asyncpg", "+psycopg2"))
    with engine.begin() as conn:
        if conn.execute(sa.text("SELECT 1 FROM users LIMIT 1")).first():
            print("Base data already seeded — users exist.")
            added = _seed_notification_templates(conn)
            print(f"Notification templates: {added} inserted (existing left untouched).")
            return

        team_id = uuid.uuid4()
        conn.execute(
            sa.text("INSERT INTO teams (id, name) VALUES (:id, 'Support')"), {"id": team_id}
        )

        pw_hash = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        roles = dict(conn.execute(sa.text("SELECT name, id FROM roles")).all())
        for role, email in [
            ("requester", "requester@agentdesk.dev"),
            ("agent", "agent@agentdesk.dev"),
            ("team_lead", "lead@agentdesk.dev"),
            ("admin", "admin@agentdesk.dev"),
        ]:
            conn.execute(
                sa.text(
                    "INSERT INTO users (email, password_hash, full_name, role_id, team_id, "
                    "email_verified_at) VALUES (:email, :pw, :name, :role_id, :team_id, now())"
                ),
                {
                    "email": email,
                    "pw": pw_hash,
                    "name": f"Demo {role.replace('_', ' ').title()}",
                    "role_id": roles[role],
                    # Requesters have no team (Document 05, users.team_id note)
                    "team_id": None if role == "requester" else team_id,
                },
            )

        for parent, children in CATEGORY_TREE.items():
            parent_id = uuid.uuid4()
            conn.execute(
                sa.text("INSERT INTO categories (id, name) VALUES (:id, :name)"),
                {"id": parent_id, "name": parent},
            )
            for child in children:
                conn.execute(
                    sa.text("INSERT INTO categories (name, parent_id) VALUES (:name, :parent_id)"),
                    {"name": child, "parent_id": parent_id},
                )

        for name, rank, color in PRIORITIES:
            resp, resolution = SLA_MINUTES[name]
            pid = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO priorities (id, name, rank, color_hex) "
                    "VALUES (:id, :name, :rank, :color)"
                ),
                {"id": pid, "name": name, "rank": rank, "color": color},
            )
            conn.execute(
                sa.text(
                    "INSERT INTO sla_policies (priority_id, response_minutes, resolution_minutes) "
                    "VALUES (:pid, :resp, :res)"
                ),
                {"pid": pid, "resp": resp, "res": resolution},
            )

        conn.execute(
            sa.text("INSERT INTO queues (name, team_id) VALUES ('General Support', :team_id)"),
            {"team_id": team_id},
        )

        _seed_notification_templates(conn)

    print(f"Seeded. Demo logins: *@agentdesk.dev / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
