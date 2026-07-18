# AgentDesk

Ticket Management System for Cube AI Solutions.

An AI-native ticket management platform that classifies, routes, and resolves support
tickets autonomously — a standalone ticketing system with its own database, workflow
engine, and API, not an agent bolted onto ServiceNow or Jira.

The full specification lives in [`/docs`](docs/) (Documents 01–05) and the phased build
plan in [Document 06](docs/06%20AgentDesk%20Implementation%20Plan.md). Those documents are
the source of truth; this README only covers local setup.

## Stack

- **Backend** — Python 3.12, FastAPI, SQLModel, Alembic, LangChain/LangGraph
- **Frontend** — React 19 + TypeScript, Vite, Tailwind CSS v4, React Query, Zod, Recharts
- **Database** — PostgreSQL 17 with `pgvector`, `pgcrypto`, `pg_trgm`

## Setup

```bash
cp .env.example .env          # then fill in JWT_SECRET and any API keys
```

### With Docker (all three services)

```bash
docker compose up
```

Backend on http://localhost:8000, frontend on http://localhost:5173, Postgres on 5432.

### Without Docker

```bash
# Backend
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/fastapi dev app/main.py

# Frontend
cd frontend && npm install && npm run dev
```

Postgres still needs to be running with the extensions from
[`backend/scripts/init-extensions.sql`](backend/scripts/init-extensions.sql) enabled —
`docker compose up postgres` is the easiest way to get just the database.

## Commands

| Task              | Command                                                            |
| ----------------- | ------------------------------------------------------------------ |
| Backend dev serve | `cd backend && .venv/bin/fastapi dev app/main.py`                  |
| Backend tests     | `cd backend && .venv/bin/pytest`                                   |
| One backend test  | `cd backend && .venv/bin/pytest tests/test_health.py::test_health` |
| Backend lint      | `cd backend && .venv/bin/ruff check . && .venv/bin/ruff format .`  |
| Frontend dev      | `cd frontend && npm run dev`                                       |
| Frontend build    | `cd frontend && npm run build`                                     |
| Frontend lint     | `cd frontend && npm run lint`                                      |
| Frontend format   | `cd frontend && npm run format`                                    |

Migrations arrive in Phase 1 (`alembic upgrade head`).

## Project status

Phase 0 (repository & environment setup) complete. Phase 1 is the database schema and
migrations — see Document 06 for the ordered task list and per-phase checkpoints.
