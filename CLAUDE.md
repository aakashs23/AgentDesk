# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 0–4 done (scaffolding, schema/migrations, app shell, auth/RBAC, core ticket domain). Next is Phase 5 (AI pipeline) in [06 AgentDesk Implementation Plan.md](docs/06%20AgentDesk%20Implementation%20Plan.md) — it opens with a flagged open decision (LLM/embedding provider) that must be surfaced, not defaulted.

## Commands

Backend runs from its own venv at `backend/.venv` (Python 3.12 — the system `python3` is 3.9 and will not work).

```bash
cd backend && .venv/bin/fastapi dev app/main.py   # serve
cd backend && .venv/bin/pytest                    # tests (single: pytest tests/test_health.py::test_health)
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format .
cd frontend && npm run dev | npm run build | npm run lint | npm run format
docker compose up                                 # backend + frontend + postgres
```

Tooling notes, so they don't get "fixed" back: **ruff only** (its formatter is black-compatible), **oxlint** not eslint (Vite 9's template ships it), and **bcrypt directly, no passlib** (passlib 1.7.4 is unmaintained and crashes on bcrypt ≥5).

## Docs are the source of truth

The five spec documents are binding, not background reading. Before implementing anything, read the section the plan cites (`per TRD Section 5`) rather than re-deriving the decision.

| Doc | Use it for |
|---|---|
| [01 PRD](docs/01%20AgentDesk%20PRD.md) | Scope — what's must-have vs. nice-to-have |
| [02 TRD](docs/02%20AgentDesk%20TRD.md) | Stack, module boundaries, API surface (`/api/v1/...`), AI pipeline |
| [03 App Flow](docs/03%20AgentDesk%20App%20Flow.md) | Ticket state machine (§10), SLA timer rules (§16), AI confidence tiers (§14) |
| [04 UI/UX](docs/04%20AgentDesk%20UIUX.md) | Design tokens — Tailwind theme must match exactly |
| [05 Backend Schema](docs/05%20AgentDesk%20Backend%20Schema.md) | Every table, FK, and index; RBAC matrix (§6–7) |
| [06 Implementation Plan](docs/06%20AgentDesk%20Implementation%20Plan.md) | Ordered phases with sign-off checkpoints |

Phases are sequential by real dependency (schema → backend → auth → tickets → AI → automation → frontend). Don't start a phase before the previous checkpoint is verified.

## Architecture

Monorepo: `/backend` (Python + FastAPI), `/frontend` (React + TS + Vite + Tailwind), `/docs`.

Single FastAPI service — no microservices in the prototype. It hosts one module per bounded concern (`auth/`, `tickets/`, `workflow/`, `ai/`, `routing/`, `search/`, `reporting/`, `notifications/`, `sla/`, `admin_config/`, `knowledge_base/`, `audit/`), each exposing an internal service interface consumed by thin routers. Keep business logic out of request handlers so modules stay independently testable and splittable later.

Postgres + `pgvector` is the single source of truth: relational tables, the taxonomy tree (adjacency list), and embeddings all live there. Alembic owns migrations.

Three client surfaces (Customer Portal / Agent Console / Admin Dashboard) hit the same API, differentiated by JWT role: `requester`, `agent`, `team_lead`, `admin`.

### AI pipeline

Ticket creation persists first, then hands off to a LangGraph graph: PII redaction → embedding → hybrid retrieval (taxonomy + vector) → classification (supervised model + LLM pass) → routing agent → draft response. State is a typed graph-state object passed between nodes; new agents get added as nodes rather than by restructuring.

## Invariants

- **RBAC lives in reusable primitives** (`require_role(...)`, `scope_tickets_to_caller()`) built in Phase 3. Every endpoint reuses them — never inline a role check.
- **Status changes write to both `audit_logs` and `ticket_status_history`.** Two tables, two purposes; always populate both.
- **Only the transitions in App Flow §10 are legal.** Reject everything else at the workflow engine, not the router.
- **Reopen starts a new resolution-timer segment** — it does not resume the original clock. `on_hold` pauses/resumes; first agent reply stops the response timer.
- **Human-in-the-loop is mandatory in the prototype**: low-confidence classifications route to manual categorization instead of auto-assignment, and every AI-drafted response needs explicit agent approval before sending. Auto-send is out of scope.
- **Schema matches Document 05 exactly** — no added, dropped, or renamed columns, FKs, or indexes.

## Open decisions (do not silently pick one)

LLM/embedding provider (Anthropic vs. OpenAI), vector store (pgvector-only vs. Pinecone/Chroma), classifier (XGBoost vs. DistilBERT), embedding dimension, final SLA thresholds, hosting target. Phases 5 and 16 are where these must be resolved — surface them rather than defaulting.

DO NOT PUSH OR COMMIT ANYTHING TO MY REPOSITORY. THIS WILL BE DONE MANUALLY.