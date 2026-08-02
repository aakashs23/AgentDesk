# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Phases 0–14 done (scaffolding, schema/migrations, API scaffolding, auth/RBAC, core ticket domain, AI pipeline, SLA + automation engines, notifications/webhooks, search + reporting, frontend foundation, Customer Portal, Agent Console, Admin Dashboard, multi-channel intake, knowledge base). All three client surfaces are built and all three intake channels (portal, email, chat) are live. Next is Phase 15 (Testing & QA) in [06 AgentDesk Implementation Plan.md](docs/06%20AgentDesk%20Implementation%20Plan.md).

Phase 9 built the shell: `frontend/src/components` (base library + the AI-signature set), `frontend/src/shell` (top bar, role sidebar, bottom tabs, Cmd+K palette), `frontend/src/lib` (API client with single-flight token refresh, session store, theme). Routing is `react-router` v7 — the only frontend dependency added since Phase 0. Every route now renders a real screen; `pages/Placeholder.tsx` is gone.

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

Phase 12 shipped the Admin Dashboard (`frontend/src/pages/admin/`), with `frontend/src/lib/admin.ts` holding its pure logic (category-tree nesting, automation-rule validation, audit diffing, the §26 setup checklist) for `npm run selfcheck`. Backend additions, all in `admin_config/config_router.py` at TRD §3's paths:

- `/admin/teams`, `/admin/queues`, `/admin/sla-rules` — full CRUD; `POST`/`PATCH`/`DELETE /admin/categories` and `/admin/priorities` (reads stay on the shared `/categories`, `/priorities`).
- `GET /admin/audit-logs` (+ `/entity-types` for the filter dropdown) — read-only, because `audit_logs` is an immutable trail.
- `DELETE /knowledge-base/articles/{id}`, Admin only, completing KB CRUD.
- `ai_performance_trend` joined `reporting/service.py::GENERATORS` — the AI monitor's "over time" is a report type, not a new endpoint, so it inherits scoping, background generation and CSV/XLSX/PDF export.

Two rules run through the config CRUD: **a delete never orphans** (a row still referenced by a ticket, another config row or AI history is a 409, not a cascade) and **every change is audited**, which is Doc 06's Phase 12 checkpoint. `tests/integration/test_admin_config.py` pins both.

Deliberately not built in Phase 12, with reasons at the code:
- **`PATCH /admin/config` / branding** (TRD §3, Doc 03 §1 "portal logo/theme"). Doc 05 defines no settings table and the schema invariant forbids adding one, so Templates & Branding edits notification templates and states the constraint instead. Still in `MISSING_ENDPOINTS`.
- **Status editing.** Statuses are a fixed vocabulary compiled into the workflow engine (App Flow §10), not a table — the Ticket Configuration screen displays the machine rather than pretending to edit it.
- **Tag deletion.** No endpoint, and `ticket_tags` has no cascade in Doc 05.

Reuse Phase 12 leaned on rather than duplicating: `components/ReportRunner.tsx` (extracted from Phase 11's Team Reports) backs both Reports & Analytics and the AI monitor, and `/admin/kb` mounts the Agent Console's KB screens — the API already scopes an Admin to every draft and author, so it is the same screen asked by a different role. Those screens now read their prefix from `useSurfaceBase()`.

Phase 13 shipped multi-channel intake — `backend/app/intake/` (`parser.py` pure, `email_service.py`, `chat_service.py`, `router.py`), the portal chat widget (`frontend/src/pages/portal/ChatWidget.tsx`, mounted by `AppShell` on the portal surface only), the agent-side takeover screen (`frontend/src/pages/agent/Chats.tsx`, `/agent/chats`) and `frontend/src/lib/chat.ts` for `npm run selfcheck`. `ConversationHistory` finally has a model; migration 0001 always had the table.

- **Email arrives two ways, one parser**: `POST /intake/email` (a provider webhook, guarded by `INBOUND_EMAIL_TOKEN` — unset means the route 503s rather than standing open) and an IMAP poll loop started from the lifespan when `IMAP_HOST` and `IMAP_POLL_SECONDS` are both set. Both call `handle_raw_email`.
- **Thread matching order** (App Flow §11 step 6): `[AGT-123]` in the subject → `In-Reply-To`/`References` against `tickets.source_email_message_id` → same sender + same normalised subject on a still-open ticket within 7 days. The acknowledgment email carries the `[AGT-…]` tag, which is what makes step 1 work at all.
- **Email never forks the domain**: new mail goes through `tickets.service.create_ticket`, replies through `create_comment`, attachments through `add_attachment` — so channel differences cannot drift from the portal's rules.

Three schema-forced decisions in Phase 13, documented at the code:
- **The manual review queue is a `queues` row** named `Manual Review`. Doc 05 defines no review table and the schema invariant forbids adding one; malformed mail becomes a ticket in that queue with the parse failure in its description, and the AI pipeline is deliberately not run on it.
- **Unknown senders auto-provision a requester** (unusable password, claimable by password reset), because `tickets.requester_id` is NOT NULL. Mail with no readable sender at all files against `unknown-sender@agentdesk.invalid`.
- **Chat session ownership is encoded in the id** as `{user_id}:{uuid4}`, since `conversation_history` has no owner column. A requester may touch only their own sessions (404, not 403); staff may read any, which is what §12 step 7's takeover needs. An agent posting to a session sets `speaker: "agent"` and stands the bot down permanently.

Phase 14 closed the Knowledge Base loop. It added no endpoints — the gaps were all in wiring:

- **Publishing embeds the article** (`knowledge_base.service.embed_article`): title + body → `pii.redact` → `gemini.embed`, exactly how a ticket's vector is made, because the pipeline compares them with `cosine_distance`. Before this, `knowledge_base_articles.embedding` was never written, so the pipeline's retrieval node (`embedding IS NOT NULL`) could never suggest anything. Re-embeds when a published article's title/body changes; an embedding failure logs and lets the publish through. `scripts/reindex_kb.py` backfills rows that arrived another way (the seed's demo articles).
- **`search.service.search_kb` is the one KB matcher** — global search, the New Ticket form's suggestions, the chat widget and both KB browse screens all route through it, so an article findable on one surface is findable on all of them. The KB list's old ILIKE branch is gone (a typed subject rarely contains a literal substring of an article). It takes a `scope` criterion from the caller rather than importing the KB service, keeping the dependency one-way: `knowledge_base` → `search`.
- **Article visibility has one definition everywhere**: `/search` and the chat widget now pass `scope_articles_to_caller`, so search can no longer surface another agent's draft that the KB screens hide.
- `GET /knowledge-base/articles` gained `status` — that's the Admin's review queue (§19 step 4), surfaced as the Drafts tab on `/admin/kb`, with Publish on the article view so approving a draft doesn't route through the editor.

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

The spec documents are binding, not background reading. Before implementing anything, read the section the plan cites (`per TRD Section 5`) rather than re-deriving the decision.

| Doc | Use it for |
|---|---|
| [01 PRD](docs/01%20AgentDesk%20PRD.md) | Scope — what's must-have vs. nice-to-have |
| [02 TRD](docs/02%20AgentDesk%20TRD.md) | Stack, module boundaries, API surface (`/api/v1/...`), AI pipeline |
| [03 App Flow](docs/03%20AgentDesk%20App%20Flow.md) | Ticket state machine (§10), SLA timer rules (§16), AI confidence tiers (§14) |
| ~~04 UI/UX~~ | **Superseded by Doc 07.** Historical only — its gradient, per-surface dark mode, and Space Grotesk are all retired |
| [05 Backend Schema](docs/05%20AgentDesk%20Backend%20Schema.md) | Every table, FK, and index; RBAC matrix (§6–7) |
| [06 Implementation Plan](docs/06%20AgentDesk%20Implementation%20Plan.md) | Ordered phases with sign-off checkpoints |
| [07 UI/UX (current)](docs/07%20AgentDesk%20UIUX%20Updated%20Document.md) | Design tokens, layout, components, motion — the Tailwind theme must match |

Two project-root files sit alongside them: [PRODUCT.md](PRODUCT.md) (who it's for, what wins when roles conflict, design principles) and [DESIGN.md](DESIGN.md) (the resolved token set, and every call Doc 07 left open).

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
- **The flat violet (`--color-ai`) means "the AI produced this"**, and marks nothing else — AI drafts, suggested categories, confidence chips, the reasoning panel, bot turns. Unlike Doc 04's gradient it has *no* exceptions: the primary CTA, the active nav indicator and the Login hero are all plain now. Human-authored content stays neutral, and the violet is always paired with a label so colour never carries the meaning alone.
- **Doc 07 supersedes Doc 04 for anything visual** (see the docs table). Where Doc 07 is silent — the type scale, the dark scheme, the AI accent — [DESIGN.md](DESIGN.md) decides, and marks those calls `[resolved]`. Two of Doc 07's own specifics are deliberately not implemented, with the reason at the code: the 3px left-border sidebar active state (§6 offers a tint fill, which is what's built) and the 4px left-border toast status stripe (§16 — the tone icon already carries it). Both are the same side-stripe pattern, used nowhere in this codebase.

## Open decisions (do not silently pick one)

LLM/embedding provider (Anthropic vs. OpenAI), vector store (pgvector-only vs. Pinecone/Chroma), classifier (XGBoost vs. DistilBERT), embedding dimension, final SLA thresholds, hosting target. Phases 5 and 16 are where these must be resolved — surface them rather than defaulting.

DO NOT PUSH OR COMMIT ANYTHING TO MY REPOSITORY. THIS WILL BE DONE MANUALLY.