# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 0–11 done (scaffolding, schema/migrations, API scaffolding, auth/RBAC, core ticket domain, AI pipeline, SLA + automation engines, notifications/webhooks, search + reporting, frontend foundation, Customer Portal, Agent Console). Next is Phase 12 (Admin Dashboard) in [06 AgentDesk Implementation Plan.md](docs/06%20AgentDesk%20Implementation%20Plan.md).

Phase 9 built the shell: `frontend/src/components` (base library + the AI-signature set), `frontend/src/shell` (top bar, role sidebar, bottom tabs, Cmd+K palette), `frontend/src/lib` (API client with single-flight token refresh, session store, theme). Routing is `react-router` v7 — the only frontend dependency added since Phase 0. Only `/admin` still renders `pages/Placeholder.tsx`; Phase 12 replaces those, leaving `src/routes/` guards alone.

Phase 10 shipped the Customer Portal (`frontend/src/pages/portal/`) **plus the backend it needed**, which earlier phases had never built: `GET /categories`, `GET /priorities` (`admin_config/taxonomy_router.py`), the knowledge-base read API (`knowledge_base/`), CSAT (`tickets/csat_router.py` + the `CsatResponse` model), `POST /auth/password-change`, and `GET /tickets/{id}/attachments`. Admin **write** access for categories/priorities/KB is still unbuilt and stays listed in `tests/integration/test_api_surface.py::MISSING_ENDPOINTS` — that dict plus `EXPECTED_ROUTES` pin the whole route table, so adding an endpoint means updating both.

Spec tension resolved in Phase 10: App Flow §1 lists Priority on the New Ticket form, but Doc 05 §6 makes priority a staff-only classification field and the AI pipeline assigns it. The form reports priority rather than asking for it; `TicketCreate` accepts `category_id` only.

Phase 11 shipped the Agent Console (`frontend/src/pages/agent/`), with `frontend/src/lib/agent.ts` holding its pure logic (legal transitions, SLA scrubber maths, `@mention` parsing) so `npm run selfcheck` can assert it. Three backend additions came with it:

- `GET /tickets` gained `assignee_id` and `unassigned` query params — the three queue tabs are one endpoint with different filters, and the caller's row scope still caps what any filter can return.
- `GET /users` opened to `agent`, team-scoped exactly as `team_lead` already was.
- `POST` / `PATCH /knowledge-base/articles` (App Flow §19): staff draft, **only an Admin may publish** — `status: "published"` is 403 for anyone else, on create and on update alike.

Two spec tensions resolved in Phase 11, both documented at the code:
- Doc 05 §6 gives an Agent "read own profile only", but Doc 06 Phase 11 mandates an assignment modal and `@mention` autocomplete, neither of which can exist without a colleague directory. Agents read the team-scoped directory; no write access anywhere. `tests/security/test_permissions.py` pins the team scoping.
- `ticket_status_history` is Team Lead+ (Doc 05 §6), so the History tab's activity feed is assembled client-side from what the caller may already read — a plain Agent sees comments, AI events and ticket timestamps, a Team Lead additionally sees status changes. Narrower, never broken.

An agent's queue only shows tickets inside `scope_tickets_to_caller` — a brand-new ticket with no queue and no assignee is invisible to agents until the AI pipeline routes it. That is Phase 4 behaviour, not a queue bug; test against tickets the pipeline has already touched.

Phase 5 resolved decisions (user-chosen, do not re-open silently): LLM = Gemini 2.5 Flash, embeddings = `gemini-embedding-001` at 1536 dims (matches migration 0001's `vector(1536)`), classifier = DistilBERT fine-tuned on synthetic seed data (`scripts/train_classifier.py` → `ml_models/classifier`, gitignored). `GEMINI_API_KEY` in `.env` gates the pipeline; without it ticket creation still works and the pipeline logs a skip. Still open: vector store beyond pgvector, final SLA thresholds, hosting target.

## Commands

Backend runs from its own venv at `backend/.venv` (Python 3.12 — the system `python3` is 3.9 and will not work).

```bash
cd backend && .venv/bin/fastapi dev app/main.py   # serve
cd backend && .venv/bin/pytest                    # tests (single: pytest tests/test_health.py::test_health)
cd backend && .venv/bin/ruff check . && .venv/bin/ruff format .
cd frontend && npm run dev | npm run build | npm run lint | npm run format
cd frontend && npm run selfcheck                  # assertions on the shell's pure logic (no test framework)
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
- **Design tokens live only in `frontend/src/index.css`.** No component invents a colour, radius, shadow, type size, or spacing value. Note the spacing scale is keyed in pixels (`p-16` is 16px), so any Tailwind utility that reads the spacing namespace with a non-token number (`size-8`, `max-w-120`) will resolve to something surprising — write those as explicit `[32px]` values.
- **The brand gradient means "the AI produced this"** — Doc 04's Signature Element. The only non-AI exceptions are the primary CTA, the active nav indicator, and the Login hero.

## Open decisions (do not silently pick one)

LLM/embedding provider (Anthropic vs. OpenAI), vector store (pgvector-only vs. Pinecone/Chroma), classifier (XGBoost vs. DistilBERT), embedding dimension, final SLA thresholds, hosting target. Phases 5 and 16 are where these must be resolved — surface them rather than defaulting.

DO NOT PUSH OR COMMIT ANYTHING TO MY REPOSITORY. THIS WILL BE DONE MANUALLY.