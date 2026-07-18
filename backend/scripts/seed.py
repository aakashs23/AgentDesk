"""Local dev seed (Implementation Plan, Phase 1).

One demo user per role, a small category tree, default priorities (rank +
color_hex per Document 04's semantic colors), one queue, one SLA policy per
priority. Run after `alembic upgrade head`:

    python scripts/seed.py          # inside the backend container, or
    DATABASE_URL=... python scripts/seed.py
"""

import os
import uuid

import bcrypt
import sqlalchemy as sa

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


def main() -> None:
    url = os.environ.get(
        "DATABASE_URL", "postgresql+asyncpg://agentdesk:agentdesk@localhost:5432/agentdesk"
    ).replace("+asyncpg", "+psycopg2")
    engine = sa.create_engine(url)
    with engine.begin() as conn:
        if conn.execute(sa.text("SELECT 1 FROM users LIMIT 1")).first():
            print("Already seeded — users exist, nothing to do.")
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

    print(f"Seeded. Demo logins: *@agentdesk.dev / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
