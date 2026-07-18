# Document 06 — Implementation Plan
### AgentDesk — Repo-to-Delivery Task Breakdown

This document is the execution plan for everything defined in Documents 01–05. It breaks the entire build — from an empty repository to a demoable prototype — into 17 sequential phases (Phase 0 through Phase 16). Every phase ends with a **Checkpoint**: a manually-verifiable checklist that a human (Aakash, or a reviewer at CubeAISolutions) ticks off before the next phase begins. Nothing here is optional or reordered for convenience — the sequence follows real dependencies (data layer before business logic, backend before frontend, core ticketing before AI, AI before automation, everything before deployment).

**How to use this document:**
- Work top to bottom. Do not start a phase until every box in the previous phase's Checkpoint is checked.
- Every task references the exact document and section it comes from (e.g. "per TRD Section 5"). Consult that section directly rather than re-deriving the decision — these documents are the source of truth, this plan is just the ordered task list.
- A few items across the prior documents were deliberately left open (LLM/embedding provider, exact SLA thresholds, final hosting target). Phases 5 and 16 specifically call out where these must be resolved before proceeding — don't let an unresolved TBD block silently propagate through later phases.
- Checkboxes are for manual sign-off, not self-reporting — a phase isn't "done" because code was written for it, it's done when its Checkpoint has been independently verified.

**Suggested pacing** (mapped loosely to the 3-month internship timeline from the original offer letter — treat as a guide, not a commitment, since actual velocity will vary):

| Phase | Suggested Week(s) |
|---|---|
| 0 — Repository & Environment Setup | Week 1 |
| 1 — Database Schema & Migrations | Week 1 |
| 2 — Backend Foundation | Week 1–2 |
| 3 — Authentication & Authorization | Week 2 |
| 4 — Core Ticket Domain | Week 3–4 |
| 5 — AI Pipeline | Week 5–6 |
| 6 — SLA Engine & Automation Engine | Week 6–7 |
| 7 — Notifications & Webhooks | Week 7 |
| 8 — Search & Reporting | Week 7–8 |
| 9 — Frontend Foundation | Week 8 |
| 10 — Customer Portal | Week 9 |
| 11 — Agent Console | Week 9–10 |
| 12 — Admin Dashboard | Week 10 |
| 13 — Multi-Channel Intake | Week 11 |
| 14 — Knowledge Base Completion | Week 11 |
| 15 — Testing & Quality Assurance | Week 12 |
| 16 — Deployment & Delivery | Week 12 |

---

## Phase 0 — Repository & Environment Setup

**Goal**: stand up the repository, tooling, and local dev environment before any feature code is written.

- [ ] Create the project repository with a monorepo layout: `/backend`, `/frontend`, `/docs`
- [ ] Copy Documents 01–05 into `/docs` verbatim, so they travel with the codebase as the permanent source of truth
- [ ] Initialize git; add a `.gitignore` covering Python, Node, `.env`, and IDE files
- [ ] Set up the backend Python project (`poetry` or `venv` + `requirements.txt`); install FastAPI, SQLAlchemy/SQLModel, Alembic, Pydantic, `python-jose` (JWT), `passlib` (bcrypt/argon2), `asyncpg`/`psycopg2`, `pgvector` Python bindings, LangChain, LangGraph
- [ ] Set up the frontend React + TypeScript project (Vite); install Tailwind CSS, React Query, Zod, Recharts or Chart.js, `lucide-react` (Document 04's icon library), and the three fonts (Space Grotesk, Inter, IBM Plex Mono)
- [ ] Configure the Tailwind theme to match Document 04's tokens exactly: dark/light color palettes, the brand gradient, semantic status colors, the border-radius scale (10px/8px/999px), and the spacing scale (Document 04, Design Tokens section)
- [ ] Create `docker-compose.yml` for local dev: `backend`, `frontend`, and `postgres` services, with the `pgvector` and `pgcrypto` extensions enabled on Postgres startup (TRD Section 16)
- [ ] Create `.env.example` listing every environment variable from TRD Section (Environment Variables): `DATABASE_URL`, `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`, `VECTOR_DB_API_KEY`, `JWT_SECRET`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SLACK_WEBHOOK_URL`, `APP_ENV`, plus `WEBHOOK_SECRET_ENCRYPTION_KEY` (Backend Schema Document 05, Section 8)
- [ ] Set up linting/formatting: `ruff`/`black` for Python, `eslint`/`prettier` for TypeScript
- [ ] Set up a basic CI pipeline (GitHub Actions) running lint and a placeholder test step on every push
- [ ] Write the root `README.md`: a short project description (from PRD Document 01) and local setup instructions

**Checkpoint**
- [ ] `docker-compose up` brings up backend, frontend, and Postgres with no errors
- [ ] `pgvector` and `pgcrypto` extensions are confirmed enabled (`\dx` in `psql`)
- [ ] The frontend dev server renders a blank page using the correct fonts and at least one spot-checked theme color matching Document 04
- [ ] CI passes on the initial commit
- [ ] All five prior documents are present under `/docs`

---

## Phase 1 — Database Schema & Migrations

**Goal**: implement every table in Backend Schema Document 05 exactly as specified, before any business logic is written.

- [ ] Set up Alembic for migrations
- [ ] Migrate the **Identity & Access** group: `roles`, `teams`, `users`, `refresh_tokens`, `password_reset_tokens`, `email_verification_tokens` (Document 05, Section 1)
- [ ] Seed `roles` with the four fixed values: `requester`, `agent`, `team_lead`, `admin`
- [ ] Migrate **Ticket Core**: `tickets`, `comments`, `comment_mentions`, `attachments`, `tags`, `ticket_tags`
- [ ] Migrate **Classification & Configuration**: `categories`, `priorities`, `queues`, `sla_policies`, `automation_rules`, `automation_execution_logs`
- [ ] Migrate **AI & Knowledge**: `ai_classification_history`, `ai_draft_history`, `embeddings` (hold the final `vector` dimension open until Phase 5 resolves the embedding provider), `conversation_history`, `knowledge_base_articles`
- [ ] Migrate **Engagement & Ops**: `notification_templates`, `notifications`, `saved_views`, `csat_responses`, `webhooks`, `webhook_deliveries`
- [ ] Migrate **Governance**: `audit_logs`, `ticket_status_history`
- [ ] Add every foreign key exactly as listed in Document 05, Section 3 — no additions, drops, or renames
- [ ] Add every index listed in Document 05, Section 4, including the GIN `tsvector`/`pg_trgm` indexes and the IVFFlat/HNSW vector indexes
- [ ] Write a local dev seed script: one demo user per role, a small category tree, default priorities (with `rank` and `color_hex` matching Document 04's semantic colors), one queue, one SLA policy per priority

**Checkpoint**
- [ ] `alembic upgrade head` runs cleanly against a fresh database
- [ ] Every table in Document 05, Section 1 exists with the exact column names and types specified
- [ ] An invalid insert violating a documented FK is rejected (test at least one, e.g. a `tickets.category_id` pointing nowhere)
- [ ] The seed script produces a usable demo dataset
- [ ] Confirmed indexes are present on `tickets`, `comments`, and `embeddings` via `\d+` in `psql`

---

## Phase 2 — Backend Foundation

**Goal**: stand up the FastAPI application shell and module boundaries from TRD Section 2, before any single endpoint is built.

- [ ] Scaffold the module structure: `auth/`, `tickets/`, `workflow/`, `ai/`, `routing/`, `search/`, `reporting/`, `notifications/`, `sla/`, `admin_config/`, `knowledge_base/`, `audit/`
- [ ] Implement config loading via Pydantic `BaseSettings`, covering every variable in `.env.example`
- [ ] Set up the SQLAlchemy/SQLModel engine and a request-scoped session dependency
- [ ] Implement structured JSON logging (TRD Section 17)
- [ ] Implement `GET /health` and `GET /health/ready` (checks DB connectivity)
- [ ] Implement global exception handling — unhandled errors return a generic 500 with a server-side logged stack trace, never leaking internals to the client
- [ ] Configure CORS for the frontend dev origin
- [ ] Implement basic per-IP/per-user rate limiting on auth and ticket-creation routes (TRD Section 10)

**Checkpoint**
- [ ] `GET /health` and `GET /health/ready` return 200 locally and inside Docker
- [ ] An undefined route returns a clean 404, not a stack trace
- [ ] All module folders import cleanly with no circular dependencies

---

## Phase 3 — Authentication & Authorization

**Goal**: implement every endpoint and rule in TRD Section 3 (Authentication) and Backend Schema Sections 5–7, so every later phase can assume a working, secure identity layer.

- [ ] Implement password hashing (bcrypt/argon2) and verification
- [ ] Implement `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`
- [ ] Implement `POST /auth/password-reset/request` and `/confirm` using `password_reset_tokens` (single-use, hashed, short expiry — Document 05, Section 5)
- [ ] Implement `POST /auth/verify-email` using `email_verification_tokens`
- [ ] Implement JWT issuance with `sub`/`role`/`team_id` claims, and a dependency that resolves the current user on every protected request
- [ ] Build the RBAC dependency layer enforcing the exact rules in Document 05, Section 6, as reusable primitives (e.g. `require_role("admin")`, `scope_tickets_to_caller()`) — every later endpoint must reuse these, not reimplement checks inline
- [ ] Implement `users` CRUD (`GET/POST/PATCH/DELETE /users`) respecting Document 05, Section 7's permissions matrix
- [ ] Implement invite-based provisioning for Agent/Team Lead/Admin accounts (App Flow Document 03, Section 24)
- [ ] Implement Requester self-registration + email verification (App Flow Document 03, Section 4)
- [ ] Write automated tests: a Requester cannot read another Requester's tickets; an Agent cannot reach any `/admin/*` route — this second case is Acceptance Criteria AC3 from the original requirements document, treat it as a hard, non-optional test

**Checkpoint**
- [ ] All four roles can be created and can log in
- [ ] A Requester JWT is rejected by every Admin-only endpoint, verified explicitly
- [ ] Refresh token rotation and revocation work; logout invalidates the refresh token
- [ ] Password reset and email verification work end-to-end against a real or sandboxed inbox

---

## Phase 4 — Core Ticket Domain

**Goal**: implement the ticket lifecycle, comments, attachments, and tags — matching App Flow Document 03, Section 10 (state machine) and TRD Section 3 — before AI or automation touch any of it.

- [ ] Implement `POST /tickets` (create) — at this phase, without AI classification; ticket lands as `status = new`, unclassified
- [ ] Implement `GET /tickets`, `GET /tickets/{id}`, `PATCH /tickets/{id}`
- [ ] Implement the status state machine exactly per App Flow Document 03, Section 10 — enforce only the transitions shown in that diagram; reject anything else
- [ ] Every status transition writes to **both** `audit_logs` and `ticket_status_history` — these are two distinct tables serving two distinct purposes (Document 05, Section 1); populate both, always
- [ ] Implement SLA timer logic: set `response_due_at`/`resolution_due_at` from the matching `sla_policies` row on creation; stop the response timer on first agent reply; pause/resume the resolution timer across `on_hold`; start a **new** resolution-timer segment on reopen — do not resume the original clock (App Flow Document 03, Section 16)
- [ ] Implement `POST /tickets/{id}/merge`, `/split`, `/reopen`
- [ ] Implement comments: `GET/POST /tickets/{id}/comments`, `PATCH/DELETE /comments/{id}`, with the `is_internal` distinction
- [ ] Implement `@mention` parsing on comment creation: write rows to `comment_mentions` (full notification wiring happens in Phase 7)
- [ ] Implement attachments: `POST /tickets/{id}/attachments` (MIME allowlist + configurable size limit per TRD Section 8), `GET /attachments/{id}`, `DELETE /attachments/{id}`, and the replace/version chain (`version`, `replaced_by_attachment_id`)
- [ ] Implement tags: `GET/POST /tags`, `POST /tickets/{id}/tags`
- [ ] Implement manual assignment/escalation: `POST /tickets/{id}/assign`, `/escalate` (automated routing arrives in Phase 5)
- [ ] Write automated tests covering every transition in the state machine, specifically including "reopen produces a fresh SLA segment" — this is the easiest rule in the whole system to implement wrong

**Checkpoint**
- [ ] A ticket can be created, commented on, tagged, attached to, assigned, escalated, put on hold, resolved, closed, and reopened entirely through the API, with every transition validated
- [ ] `ticket_status_history` and `audit_logs` both show a complete, correct trail for a ticket pushed through every status
- [ ] A reopened ticket shows a fresh `resolution_due_at`, distinct from its original SLA outcome
- [ ] An oversized or disallowed-format attachment is rejected cleanly, not with a 500

---

## Phase 5 — AI Pipeline

**Goal**: implement the full AI pipeline from App Flow Document 03, Section 5 and TRD Section 5, wired into ticket creation from Phase 4.

- [ ] **Resolve the open TBD first**: finalize the LLM provider and embedding model (TRD flags this as open between Anthropic's ecosystem via Voyage AI and OpenAI); confirm the chosen embedding dimension matches `embeddings.embedding` and update the Phase 1 migration if the placeholder dimension needs to change
- [ ] Implement PII detection and redaction as the first pipeline stage, run on every ticket before any content leaves the system
- [ ] Implement embedding generation, writing to `embeddings`
- [ ] Implement hybrid retrieval: taxonomy matching (`categories.parent_id` traversal) run alongside `pgvector` similarity search
- [ ] Implement the classification model call (hybrid LLM + supervised classifier), writing to `ai_classification_history` with `confidence` and `confidence_tier`
- [ ] Implement the confidence-branch logic exactly per App Flow Document 03, Section 14: high confidence → auto-route; medium → suggest, agent confirms; low → manual classification required — implement the thresholds as configurable values, not hardcoded, since Document 03 flags them as illustrative pending real data
- [ ] Implement priority prediction alongside category prediction
- [ ] Wire the pipeline into `POST /tickets` as an async background step (TRD Section 11), so ticket creation is never blocked on it
- [ ] Implement the LangGraph orchestration graph: Classification → Priority → Routing Agent → Assignment → Draft Response Agent → Human Review, with conditional edges for the confidence branches
- [ ] Implement the Draft Response Agent: writes a suggested reply to `ai_draft_history` with `review_status = 'pending'` — it must **never** write directly to `comments`
- [ ] Implement the human-in-the-loop approval endpoint: approving/editing a draft creates the actual `comments` row (`is_ai_generated = true`, carrying `ai_confidence`) and sets `ai_draft_history.final_comment_id`; a rejected draft keeps `final_comment_id` null, permanently
- [ ] Implement the feedback loop: an agent's correction of a low/medium-confidence classification writes to `ai_classification_history.corrected_category_id`/`corrected_priority_id`

**Checkpoint**
- [ ] Creating a ticket through the portal produces a populated `ai_classification_history` row within a few seconds, without delaying the creation response
- [ ] A high-confidence test ticket auto-routes with no agent action; a low-confidence one sits unclassified until an agent manually categorizes it
- [ ] An AI-drafted reply never appears as a sent comment until explicitly approved
- [ ] A deliberately rejected draft is retained in `ai_draft_history` and confirmed to never produce a `comments` row

---

## Phase 6 — SLA Engine & Automation Engine

**Goal**: implement SLA breach/escalation runtime and the automation rule engine on top of the ticket core from Phase 4.

- [ ] Implement a scheduled background job scanning open tickets for SLA warning/breach thresholds (TRD Section 11)
- [ ] Implement the warning and escalation notification triggers per App Flow Document 03, Section 16
- [ ] Implement `automation_rules` CRUD (`/admin/automation-rules`)
- [ ] Implement the Automation Engine runtime: on every relevant event, fetch active rules for that trigger ordered by `priority`, evaluate conditions, execute matched actions
- [ ] Implement conflict resolution: the higher-priority (lower `priority` value) rule wins when two rules produce contradictory actions; log the conflict
- [ ] Write every rule evaluation — matched, skipped, succeeded, failed — to `automation_execution_logs`, including `error_message` on failure
- [ ] Implement the rule preview endpoint (App Flow Document 03, Section 25): given a draft rule, return a sample of existing tickets it would match

**Checkpoint**
- [ ] A test SLA policy with a short threshold correctly fires a warning, then an escalation, if left unresolved
- [ ] A simple automation rule (e.g. category = Billing → assign to a specific queue) fires correctly on ticket creation
- [ ] `automation_execution_logs` shows a row for every evaluation attempt, including a deliberately non-matching rule
- [ ] Two deliberately conflicting rules resolve according to `priority`, visibly logged

---

## Phase 7 — Notifications & Webhooks

**Goal**: implement the full notification runtime (App Flow Document 03, Section 17) and outbound webhook delivery (Backend Schema Document 05, Section 10).

- [ ] Implement `notification_templates` CRUD, seeded with a default template for every `trigger_type` × `channel` combination
- [ ] Implement the Notification Service: on a qualifying event, look up the active template for the trigger and recipient's preferred channel, interpolate variables, write a `notifications` row with `template_id` set, dispatch via the matching channel adapter
- [ ] Implement the Email channel adapter (SMTP)
- [ ] Implement the In-App channel adapter (`notifications` table + `GET /notifications`, `PATCH /notifications/{id}/read`)
- [ ] Implement per-user notification preferences (`users.notification_preferences`) and `PATCH /notifications/preferences`
- [ ] Wire every trigger from App Flow Document 03: assignment, reply, status change, SLA warning, escalation, `@mention` (from Phase 4), ticket closed, automation executed
- [ ] Implement `webhooks` CRUD and the delivery background job: HMAC-SHA256 sign the payload with `webhooks.secret`, POST to `target_url`, record every attempt in `webhook_deliveries` with retry/backoff on failure

**Checkpoint**
- [ ] Every trigger listed above produces a real notification, verified manually at least once each
- [ ] Disabling email for one trigger in a user's preferences suppresses email but not in-app for that same trigger
- [ ] A registered webhook receives a correctly signed payload on `ticket_created`; a deliberately broken target URL shows retry attempts in `webhook_deliveries`

---

## Phase 8 — Search & Reporting

**Goal**: implement hybrid search (TRD Section 6) and the reporting/dashboard endpoints (TRD Section 12).

- [ ] Implement `GET /search/tickets?q=` combining Postgres FTS, `pg_trgm`, and `pgvector` similarity, with metadata filters applied before ranking
- [ ] Implement role-scoped search exactly per App Flow Document 03, Section 18 (Requester: own tickets + published KB; Agent/Team Lead: team-scoped + internal notes + KB; Admin: org-wide + audit log + KB drafts)
- [ ] Implement `saved_views` CRUD
- [ ] Implement `GET /dashboard/metrics`: open ticket count, average resolution time, SLA compliance rate, agent workload
- [ ] Implement `POST /reports/generate` and `/reports/{id}/export` (CSV/PDF/Excel): agent productivity, SLA compliance, ticket trends, category analytics, and AI performance (classification accuracy from `ai_classification_history`; draft approval/edit/reject rate from `ai_draft_history`)
- [ ] Implement pagination/background generation for large report datasets

**Checkpoint**
- [ ] Search returns ranked results blending keyword and semantic matches, correctly scoped per role
- [ ] Admin Overview metrics match a manual count against the seed/demo data
- [ ] A generated report exports correctly in CSV, PDF, and Excel
- [ ] The AI performance report correctly reflects a deliberately rejected draft and a deliberately corrected classification from earlier test phases

---

## Phase 9 — Frontend Foundation

**Goal**: implement Document 04's design system as reusable components, and Document 03's app shell/navigation, before building any individual screen.

- [ ] Implement the Tailwind theme exactly per Document 04: color tokens (light/dark), type scale, spacing scale, border-radius scale
- [ ] Build the base component library — Button, Card (static vs. clickable), Input, Dropdown, Modal, Drawer, Tabs, Accordion, Tooltip, Toast — matching every state in Document 04's Component Behavior section exactly
- [ ] Build the AI-signature components: the gradient-accented AI Insight chip, the AI Draft Response drawer shell, the diff-style change callout — these are the only components permitted to use the brand gradient
- [ ] Build the avatar-initials component (no photo upload, per Document 04 and the deliberate absence of avatar storage in Document 05)
- [ ] Implement the app shell: top bar (search, notification bell, user menu), role-based collapsible sidebar, mobile bottom tab bar
- [ ] Implement dark/light mode switching with Document 04's per-surface defaults (Agent Console/Admin dark by default, Customer Portal/Login light by default), persisted to `users.theme_preference`
- [ ] Implement the command palette (Cmd/Ctrl+K) shell for Agent Console/Admin Dashboard
- [ ] Implement the Login screen with the Aave-style typographic hero (gradient text fill — the one permitted exception to the AI-signature-only gradient rule)
- [ ] Wire up the API client, auth token storage/refresh, and protected-route redirect logic (App Flow Document 03, Section 3)
- [ ] Implement global loading states: skeleton loaders, the AI-generation shimmer, and `prefers-reduced-motion` handling

**Checkpoint**
- [ ] Every shared component visually matches Document 04's tokens (spot-check corner radii, colors, spacing)
- [ ] Logging in as each of the four seeded roles lands on the correct role-based home screen
- [ ] Dark/light mode preference persists across a page reload
- [ ] Visiting a protected URL while logged out redirects to Login and returns to the original URL after authenticating

---

## Phase 10 — Customer Portal

**Goal**: build every Customer Portal screen from App Flow Document 03, Section 1.

- [ ] Build My Tickets (home): list, filters, empty state
- [ ] Build New Ticket: required fields, optional attachments (wired to Phase 4), live KB-article suggestions
- [ ] Build Ticket Detail (requester view): Conversation + Attachments tabs only, the AI-processing state after submission
- [ ] Build Knowledge Base Search and KB Article Detail, including the FAQ/accordion pattern
- [ ] Build Notifications and Account Settings (profile, password, notification preferences, theme toggle)
- [ ] Build the CSAT Survey modal, triggered on next visit to a resolved ticket
- [ ] Confirm mobile bottom-tab navigation and the responsive card-stacking behavior from Document 04
- [ ] Implement Sign Up + email verification flow

**Checkpoint**
- [ ] A brand-new Requester can sign up, verify email, submit a ticket with an attachment, see it processed, get a reply, and complete a CSAT survey entirely through the UI
- [ ] Every screen matches its App Flow Document 03 description and Document 04's light-first treatment
- [ ] Mobile viewport shows the bottom tab bar and stacked ticket cards correctly

---

## Phase 11 — Agent Console

**Goal**: build every Agent/Team Lead screen, including the AI-native UI that distinguishes AgentDesk from a plain ticketing tool.

- [ ] Build Ticket Queue: My Tickets / Team Queue / Unassigned tabs, the inbox-row pattern from Document 04
- [ ] Build Ticket Detail — Agent View: full tab set (Conversation / Internal Notes / AI Insights / Attachments / History), metadata grid, SLA countdown/scrubber
- [ ] Build the AI Insights tab: predicted category/priority, confidence score/tier, similar past tickets
- [ ] Build the AI Draft Response drawer: approve/edit/reject, wired to Phase 5's human-in-the-loop endpoint — confirm the gradient-accented header is the first thing visible on open
- [ ] Build assignment/escalation/merge/reopen modals
- [ ] Build Saved Views
- [ ] Build Knowledge Base (agent-facing): browse + create/edit article from a resolved ticket
- [ ] Build Team Workload and Team Reports, visible to Team Lead only — enforce this in the UI in addition to backend RBAC (the sidebar item should be absent, not merely blocked)
- [ ] Implement `@mention` autocomplete in the comment composer, wired to `comment_mentions`
- [ ] Implement the activity feed with role-coded entries (human actions flat, AI findings gradient, system events muted grey)

**Checkpoint**
- [ ] An Agent can pick up a new AI-routed ticket, review AI Insights, approve/edit/reject a drafted reply, and resolve the ticket entirely through the UI
- [ ] A Team Lead sees Team Workload/Reports in their sidebar; a plain Agent's sidebar does not show those items at all
- [ ] `@mention` autocomplete correctly writes to `comment_mentions` and fires a notification

---

## Phase 12 — Admin Dashboard

**Goal**: build every Admin screen, completing the three-surface product.

- [ ] Build Admin Overview: org-wide metrics, stat-callout row, AI performance snapshot
- [ ] Build User & Team Management: create/invite, assign role/team, deactivate/reactivate, change role/team
- [ ] Build Ticket Configuration: statuses, category tree, priorities (with `color_hex` picker matching Document 04), queues, tags
- [ ] Build SLA Rules
- [ ] Build Automation Rules: the builder flow (trigger → conditions → actions → preview → save → activate), plus a read-only `automation_execution_logs` view for debugging
- [ ] Build Notification Templates & Branding, editing `notification_templates` per trigger/channel, plus portal logo/theme
- [ ] Build Reports & Analytics (full org-wide version of Phase 8's endpoints)
- [ ] Build the Audit Log viewer (searchable, filterable by entity type/actor/date)
- [ ] Build the AI Performance Monitor: classification accuracy, auto-routing acceptance rate, draft approval/edit/reject rate, over time
- [ ] Build Knowledge Base Management (full CRUD, across all categories/authors)
- [ ] Build the Webhooks screen: register/list/delete, plus delivery history
- [ ] Implement First-Time Admin Setup (App Flow Document 03, Section 27), triggered automatically on the very first Admin login when no teams/categories exist yet

**Checkpoint**
- [ ] A brand-new deployment, logged into as the first Admin, walks through First-Time Admin Setup and ends with a usable, configured system
- [ ] Every configuration change is reflected in the Audit Log
- [ ] The AI Performance Monitor's numbers match what Phases 5 and 8 computed for the seeded/test data

---

## Phase 13 — Multi-Channel Intake

**Goal**: implement email-to-ticket and the chat widget, per App Flow Document 03, Sections 11–12.

- [ ] Set up inbound email receiving (IMAP/SMTP polling or a provider webhook)
- [ ] Implement the email parser: sender/subject/body/attachment extraction, malformed-email routing to a manual review queue
- [ ] Implement reply-thread matching (subject-line Ticket ID, thread headers, or sender+recency heuristics) to append to an existing ticket instead of creating a duplicate
- [ ] Wire new (non-reply) parsed emails into the same ticket-creation + AI pipeline path from Phases 4–5
- [ ] Implement the acknowledgment email carrying the ticket's `display_id` for future thread matching
- [ ] Build the chat widget UI: bot greeting, issue collection, live KB-article suggestions
- [ ] Implement chat transcript storage in `conversation_history`, keyed by `session_id` before a ticket exists
- [ ] Implement conversion-to-ticket on no-resolution: run the transcript through the AI pipeline, link `conversation_history.ticket_id`
- [ ] Implement human takeover: an available agent can join a still-active live chat

**Checkpoint**
- [ ] A test email creates a correctly classified ticket; replying to the acknowledgment email appends to the same ticket rather than creating a new one
- [ ] A deliberately malformed email lands in the manual review queue rather than crashing or vanishing silently
- [ ] An unresolved chat conversation converts cleanly into a ticket with the full transcript attached

---

## Phase 14 — Knowledge Base Completion

**Goal**: close the loop on the Knowledge Base feature end-to-end, since pieces of it were built incrementally across Phases 5 and 10–13.

- [ ] Confirm KB article embeddings are generated on publish and used identically to ticket embeddings for suggestion-matching
- [ ] Confirm the draft → review → publish workflow is fully wired from the Agent Console's "flag as reusable" action through to Admin's KB Management screen
- [ ] Confirm published articles surface correctly in: the New Ticket form, the chat widget, and global search (Requester-visible scope limited to `published` only)

**Checkpoint**
- [ ] Resolving a ticket, flagging it reusable, publishing the draft, and seeing it suggested on a new similar ticket works end-to-end
- [ ] A draft (unpublished) article never appears to a Requester, in search or suggestions

---

## Phase 15 — Testing & Quality Assurance

**Goal**: verify the whole system against every Acceptance Criteria item and edge case named across all five prior documents.

- [ ] Test every Acceptance Criteria item from the original company requirements document: ticket creation confirmation, AI classification accuracy threshold, auto-routing, SLA alerts, RBAC enforcement, report export
- [ ] Test every edge case from App Flow Document 03, Sections 6, 27, and 28: empty/error/loading states, AI-unavailable fallback, notification failure, email server unavailable, attachment upload failure, search unavailable, database timeout, auth timeout, rate limiting, duplicate detection, low AI confidence, deleted-user reassignment, reopen-after-SLA-expiry
- [ ] Run a full accessibility pass against Document 04's Accessibility Considerations: contrast ratios, keyboard-only navigation through every core flow, screen-reader labels on status/AI chips, reduced-motion behavior
- [ ] Run a cross-browser/responsive pass: latest Chrome, Firefox, Edge, Safari, plus the mobile/tablet breakpoints from Document 04
- [ ] Load-test search and dashboard endpoints against a synthetically scaled-up dataset; `EXPLAIN ANALYZE` any slow queries to confirm Document 05's indexes are actually being used
- [ ] Run a security pass: rate limiting works, all queries are parameterized (no string-built SQL), no sensitive field (Document 05, Section 8) ever appears in a response body or log, every Admin/Team-Lead-only screen is unreachable by a lower-privileged role via direct URL

**Checkpoint**
- [ ] Every Acceptance Criteria item and every named edge case has a passing test or a documented, deliberate exception
- [ ] A direct search of test-run output confirms no `password_hash`, `token_hash`, or `webhooks.secret` value ever appeared in a response or log
- [ ] Keyboard-only navigation completes ticket submission, ticket resolution, and admin configuration with no mouse

---

## Phase 16 — Deployment & Delivery

**Goal**: package and deliver the prototype for internal review/demo at CubeAISolutions, per TRD Section 16.

- [ ] Finalize Docker images for backend and frontend
- [ ] Stand up the prototype environment (per TRD Section 16 — a single cloud VM by default, or whatever CubeAISolutions IT has since confirmed)
- [ ] Run Alembic migrations against the deployed database, then run the seed script or a curated demo dataset
- [ ] Confirm environment variables are set via the hosting platform's secret store, never committed
- [ ] Confirm `/health` and `/health/ready` respond correctly in the deployed environment
- [ ] Take a full database backup immediately after seeding, and confirm the restore procedure works at least once (TRD Section 19)
- [ ] Prepare a walkthrough covering the three key user journeys from App Flow Document 03, Section 5, as the demo script
- [ ] Prepare a short internal handoff note listing every item still flagged TBD across Documents 01–05 (final LLM/vector-store/classifier choice, success-metric thresholds, hosting/infra ownership), so review isn't blocked on open documentation questions

**Checkpoint (Final Delivery)**
- [ ] The deployed prototype is reachable, seeded, and walkable through all three key journeys with no developer present
- [ ] A fresh backup exists and has been restored at least once successfully
- [ ] Every Checkpoint from Phase 0 through Phase 15 is marked complete
- [ ] The handoff note is written and shared with the CubeAISolutions team
