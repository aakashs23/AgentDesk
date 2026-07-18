# Document 01 — PRD (Product Requirements Document)

## App Name
**AgentDesk** *(working title — to be validated with CubeAISolutions)*

## Tagline
An AI-native ticket management platform that classifies, routes, and resolves support tickets autonomously — built from the ground up, not bolted onto ServiceNow or Jira.

## Problem
Support teams drown in manual ticket triage: reading, categorizing, prioritizing, and routing every incoming request by hand. This slows response times, causes misrouted or duplicate tickets, and buries the patterns (recurring issues, SLA risk, root causes) that leadership needs to see.

Existing tools like ServiceNow and Jira Service Management give teams a workflow engine, but intelligence is an afterthought — usually a chatbot bolted on top of a rigid ticketing core. Teams need a system where AI is part of the core pipeline (intake → classification → routing → resolution), not an add-on integration.

This is felt most by:
- **Support agents**, who lose time on tickets that should never have reached them (duplicates, misrouted, easily auto-resolvable)
- **Ops/team leads**, who lack real-time visibility into SLA risk and workload balance
- **End users**, who wait longer than necessary for simple issues
- **Admins/developers**, who need a system they can configure and extend without fighting a third-party platform's constraints

## Core Value Proposition
AgentDesk is a **standalone internal ticketing platform** — its own database, workflow engine, and API — with agentic AI woven directly into the pipeline rather than layered on top. It combines:
- Hybrid retrieval (taxonomy tree + vector embeddings) for context-aware classification
- A hybrid LLM + supervised classifier for routing decisions
- A LangGraph-based multi-agent orchestrator for ticket lifecycle actions
- A Jira/ServiceNow-style dashboard familiar to any support team

This is explicitly **not** an AI agent that wraps or calls into an existing ServiceNow/Jira instance — it is the ticketing system itself, augmented with agentic AI at every layer.

## Target User
CubeAISolutions' internal support and operations organization. Primary personas are **support agents** who triage and resolve day-to-day tickets, **ops/team leads** who monitor workload, SLA compliance, and escalations, **end users** (employees or customers) who submit and track requests, and **developer/admins** who configure workflows, taxonomies, and integrations. All four roles need a system that reduces manual overhead while staying transparent and controllable.

## Core Features (Must Have)

**Multi-Channel Intake**
- Ticket submission via web form, email-to-ticket, and chat widget
- Required fields at submission: Subject, Description, Category, Priority (Attachments optional)
- File attachment support (images, PDFs, docs) at ticket creation
- Data cleaning and PII redaction on incoming ticket content
- Auto-generated unique Ticket ID and auto-acknowledgment to requester

**Hybrid Retrieval & Classification**
- Hierarchical taxonomy tree combined with vector embeddings for similarity/context retrieval
- Hybrid LLM + supervised classifier (XGBoost/DistilBERT) for category and priority assignment
- Auto-tagging and suggested categorization based on ticket content
- User-defined custom tags/labels (manually applied, in addition to AI-suggested tags)

**Routing & Assignment**
- Rule-based auto-assignment (round-robin, load balancing, category-based)
- Manual assignment and reassignment/escalation
- Queue/department grouping

**Multi-Agent Orchestration (LangGraph)**
- Autonomous agents for ticket lifecycle actions: acknowledgment, clarification requests, draft responses, resolution support
- Human-in-the-loop handoff for agent-drafted responses before sending (during prototype phase)

**Ticket Lifecycle & Core Data**
- Configurable statuses (New, Open, In Progress, On Hold, Resolved, Closed, Reopened)
- Status change history/audit trail
- Merge duplicate tickets; split into sub-tasks
- Reopen closed tickets within a configurable time window
- Own Postgres database with pgvector for embeddings; workflow state machine; internal REST API (FastAPI)

**Communication & Collaboration**
- Threaded conversation view (public replies + internal notes)
- @mentions for internal collaboration between agents
- Email and in-app notifications on status changes, replies, and assignment
- Configurable notification triggers (new ticket, assignment, reply, SLA breach) per user/role
- Canned/predefined response templates

**SLA Management**
- SLA policies per priority/category (response and resolution targets)
- Visual SLA countdown on ticket view
- Automatic alerts when SLA is breached or nearing breach

**Search, Filter & Dashboard**
- Full-text search across subject, description, and comments
- Filters by status, priority, category, assignee, date range, tags
- Saved/custom views per user
- Bulk actions (assign, close, tag multiple tickets)
- Jira/ServiceNow-style dashboard: open tickets, avg. resolution time, SLA compliance, agent workload
- Exportable reports (CSV/PDF/Excel) for a custom date range

**Access & Administration**
- Role-based access control (Requester, Agent, Team Lead, Admin)
- Admin can create/manage users, teams, and permissions
- Password reset and account recovery
- Admin configuration of ticket statuses, categories, priorities, SLA rules
- Configurable attachment size limits
- Automation rule configuration (triggers, conditions, actions) for workflow automation
- Audit logs of admin/configuration changes

## Nice to Have
- Self-service chatbot for ticket deflection before a ticket is even created
- SLA breach prediction (proactive risk scoring, not just threshold alerts)
- Trend and root-cause detection agent across historical tickets
- Duplicate ticket clustering (beyond manual merge)
- Auto-resolution for simple, well-understood issue types
- ROI/analytics dashboard tailored for leadership reporting
- Knowledge base / FAQ suggestions surfaced during ticket creation
- CSAT survey after ticket closure
- Third-party integrations: Slack, MS Teams, email inbox sync
- SSO/OAuth login
- Webhooks for event-based automation
- Multi-language/localization support

## Out of Scope
- **Wrapping or integrating with an existing ServiceNow/Jira instance** — AgentDesk is a standalone system, not an agent layer on top of third-party platforms
- Native mobile applications (mobile-responsive web only)
- Multi-tenant/white-label capability
- Production-grade deployment, scaling, and hardening (current phase is prototyping within a 3-month internship timeline)
- Full CRM integration
- Formal SOC2/compliance certification work
- Final, validated success-metric thresholds (see below — placeholders pending real ticket data)

## User Stories
- As a **requester**, I want to submit a ticket through a simple form so that I can get help without knowing which team to route it to.
- As a **requester**, I want to receive an automatic acknowledgment so that I know my ticket was received.
- As a **support agent**, I want tickets to arrive pre-classified and pre-prioritized so that I can focus on resolution instead of triage.
- As a **support agent**, I want duplicate tickets automatically flagged or merged so that I'm not doing redundant work.
- As a **support agent**, I want canned responses and AI-drafted replies so that I can respond faster to common issues.
- As an **ops/team lead**, I want a real-time dashboard of SLA status and agent workload so that I can rebalance assignments before breaches happen.
- As an **ops/team lead**, I want escalation alerts when a ticket is nearing SLA breach so that I can intervene early.
- As a **developer/admin**, I want to configure ticket categories, priorities, and SLA rules so that the system reflects our actual support structure.
- As a **developer/admin**, I want an internal REST API so that I can extend or integrate AgentDesk with other internal tools later.
- As a **developer/admin**, I want an audit trail of configuration changes so that I can track who changed what and when.

## Success Metrics
*Note: numeric targets below are illustrative placeholders. They should be recalibrated against CubeAISolutions' real historical ticket data once available — this is an explicit open item from the planning phase.*

- Reduction in average ticket triage time (manual classification/routing time saved vs. baseline)
- Classification/routing accuracy of the hybrid LLM + classifier model (e.g. target >85% agreement with human-assigned category)
- Percentage of tickets auto-resolved or deflected without agent intervention
- SLA compliance rate (% of tickets resolved within target response/resolution windows)
- Reduction in duplicate tickets reaching agents
- Agent-reported time saved per week (qualitative/survey-based during prototype phase)
- Successful end-to-end demo of the six-layer pipeline (intake → retrieval → classification/routing → orchestration → ticket core → dashboard) by end of internship

## Non-Functional Requirements
- Page load times under 2 seconds
- Horizontal scalability to accommodate growing ticket volume
- TLS encryption for data in transit
- Encryption at rest for stored data
- Daily automated backups
- Responsive UI (mobile/tablet friendly)
- Role-based security enforced across all access points
- Support for latest versions of modern browsers (Chrome, Firefox, Edge, Safari)
- Audit logging of ticket and admin/configuration changes
- Multi-language support (future scope)

## Acceptance Criteria
- Ticket is created successfully with all required fields and a confirmation is returned to the requester
- AI classification accuracy exceeds 85% agreement with human-assigned category
- Auto-routing correctly assigns tickets per configured rules
- SLA alerts trigger at the correct threshold (e.g. nearing/at breach)
- Role-based access control is enforced (e.g. an Agent cannot access Admin configuration settings)
- Reports export correctly in CSV/PDF/Excel formats
