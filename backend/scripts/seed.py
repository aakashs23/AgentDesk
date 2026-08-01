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


# Published KB articles, so self-service has something to serve: the New Ticket
# form's suggestions, the chat widget's answers and global search all read this
# table, and every one of them is a no-op against an empty knowledge base.
# `embedding` stays null — generating one needs a live API key, which a seed
# script must never require. Full-text and trigram matching work without it;
# the vector half switches on when Phase 14 embeds articles on publish.
KB_ARTICLES = [
    (
        "Login Issues",
        "Resetting your AgentDesk password",
        "If you cannot sign in, reset your password rather than retrying — six failed "
        "attempts locks the account for 15 minutes.\n\n"
        "1. On the sign-in screen, choose 'Forgot password'.\n"
        "2. Enter the email address your account uses and submit.\n"
        "3. Open the email titled 'Reset your AgentDesk password' and follow the link. "
        "The link is single-use and expires after one hour.\n"
        "4. Choose a new password of at least 12 characters.\n\n"
        "If the email does not arrive within a few minutes, check your spam folder and "
        "confirm you used the address your account was created with. Accounts created "
        "for you by an administrator use your work address.",
    ),
    (
        "Technical Support",
        "VPN disconnects every hour",
        "A VPN session that drops on a predictable schedule is almost always the "
        "gateway's re-key interval rather than your network.\n\n"
        "Try these in order:\n"
        "1. Update the VPN client — releases before 5.2 fail to re-key silently.\n"
        "2. Switch the connection profile from UDP to TCP. Re-keying survives a brief "
        "packet loss on TCP; on UDP it does not.\n"
        "3. On Wi-Fi, disable your adapter's power-saving option, which suspends the "
        "radio during idle periods and kills the tunnel.\n\n"
        "If it still drops at the same interval after all three, raise a ticket and "
        "include the client version and whether you are on Wi-Fi or wired.",
    ),
    (
        "Refunds",
        "How refunds are processed",
        "Refunds are issued to the original payment method. We cannot redirect a refund "
        "to a different card or account.\n\n"
        "Timing: refunds are approved within two business days of the request. Once "
        "approved, card refunds take a further 5–10 business days to appear, depending "
        "on your bank. Bank transfers usually settle in 3–5 business days.\n\n"
        "Partial refunds are possible on annual plans — you are refunded the unused "
        "whole months remaining. To request one, raise a ticket with your invoice "
        "number and the reason.",
    ),
    (
        "Invoices",
        "Finding and downloading your invoices",
        "Every invoice is available from Billing → Invoices in your account, going back "
        "to the start of your subscription.\n\n"
        "Select an invoice to download it as a PDF. Copies are also emailed to the "
        "billing contact on the account each time one is issued.\n\n"
        "To change the billing contact, the company name or the VAT/tax number printed "
        "on an invoice, raise a ticket — those fields are locked after issue, so we "
        "reissue the invoice rather than editing it.",
    ),
    (
        "Bug Report",
        "What to include when reporting a bug",
        "A report we can reproduce is resolved far faster than one we cannot. Include:\n\n"
        "- What you did, step by step, from a known starting point.\n"
        "- What you expected to happen, and what happened instead.\n"
        "- When it started, and whether it happens every time or intermittently.\n"
        "- Your browser and operating system, plus the exact error text if there was one.\n"
        "- A screenshot or short screen recording, attached to the ticket.\n\n"
        "If the problem involves specific data, give us the ticket reference, invoice "
        "number or account name involved rather than a description of it.",
    ),
]


def _seed_kb_articles(conn) -> int:
    """Published demo articles, idempotent by title so re-running never
    duplicates them or overwrites an edit made in the Admin console."""
    author_id = conn.execute(
        sa.text(
            "SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE r.name = 'admin' LIMIT 1"
        )
    ).scalar()
    categories = dict(conn.execute(sa.text("SELECT name, id FROM categories")).all())
    inserted = 0
    for category, title, body in KB_ARTICLES:
        exists = conn.execute(
            sa.text("SELECT 1 FROM knowledge_base_articles WHERE title = :t LIMIT 1"), {"t": title}
        ).first()
        if exists:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_base_articles "
                "(title, body, category_id, status, author_id, published_at) "
                "VALUES (:title, :body, :cat, 'published', :author, now())"
            ),
            {"title": title, "body": body, "cat": categories.get(category), "author": author_id},
        )
        inserted += 1
    return inserted


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
            articles = _seed_kb_articles(conn)
            print(f"Knowledge base articles: {articles} inserted (existing left untouched).")
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
        _seed_kb_articles(conn)

    print(f"Seeded. Demo logins: *@agentdesk.dev / {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
