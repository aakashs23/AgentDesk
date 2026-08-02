# Product

## Register

product

## Platform

adaptive

Web ships first (React + Vite SPA, responsive to mobile web). Native iOS and Android
are planned, so design decisions stay portable: no affordance that only works with a
mouse, no navigation metaphor that can't become a tab bar or navigation rail, and a
dark theme authored as a real scheme rather than an invert, since HIG and Material 3
both treat dark as first-class.

## Users

Four roles use AgentDesk, as documented in Doc 01: **requesters** (employees or
customers who submit and track requests), **support agents** who triage and resolve,
**team leads** who watch workload, SLA risk, and escalations, and **admins** who
configure taxonomies, queues, SLA rules, and automation.

Requesters are the design centre. The Customer Portal is the front door and the volume
surface, and its users are the least practiced — they arrive once with a problem, not
daily with a workflow. When two roles' needs conflict, the requester's clarity wins.
Agents, leads, and admins are served with density and speed, but not at the cost of
making the front door harder to read.

## Product Purpose

AgentDesk is a standalone ticket management platform with its own database, workflow
engine, and API, with agentic AI in the intake → classification → routing → resolution
pipeline rather than layered on top of it. It exists because triage is manual work that
buries the patterns leadership needs to see: recurring issues, SLA risk, root causes.

Success is a ticket that reaches the right person without anyone having read it first,
and an agent who trusts the system enough to accept its suggestion — while every
AI decision stays visible, attributable, and reversible by a human.

## Positioning

The ticketing system itself, made intelligent — not an AI agent wrapped around
ServiceNow or Jira.

## Brand Personality

Premium, minimal, engineered. The voice projects professional competence and
reliability without decoration; there is no playfulness, no mascot, no illustration
doing the work that hierarchy should do. Confidence is expressed through stark
contrast, exact alignment, and restraint with color — the interface should read as
something built by people who take the work seriously, and then get out of the way.

## Anti-references

- **Tech-stack branding.** No React logos or framework marks anywhere in the UI.
- **Decorative gradients, shading, and depth.** Graphics stay flat, geometric, vector.
  The one violet accent is a signal, not an effect.
- **Gradient text headlines and marketing-hero treatments inside the product.** The
  Aave-flavoured first-touch language from Doc 04 is retired; Login and empty states
  get the same engineered restraint as the queue.
- **Enterprise-ITSM density for its own sake.** ServiceNow's wall of chrome is the
  thing this product is defined against; density is earned per screen, not assumed.
- **Playful or extraneous decorative elements** of any kind.

## Design Principles

1. **Engineered reduction.** Every component serves a distinct functional purpose.
   Hierarchy comes from spatial tension and exact typography, not from adding things.
2. **The front door sets the standard.** A screen a requester sees once must be
   legible without training. That constraint improves the agent surfaces too.
3. **AI provenance is never ambiguous.** Anything the model produced or suggested
   carries the flat violet accent and says so; anything a human wrote or decided stays
   neutral. Human-in-the-loop approval is mandatory — nothing auto-sends.
4. **One vocabulary across three surfaces and, later, two operating systems.** Moving
   from Portal to Agent Console to Admin should never feel like three tools. Tokens are
   the only place a color, radius, or spacing value is decided.
5. **Density serves speed, not appearance.** Compact rows and dense panels are for
   people doing the same task fifty times a day; they are not a default aesthetic.

## Accessibility & Inclusion

Minimum 4.5:1 contrast for all text against its background. Focus rings are
non-negotiable: 3px solid brand primary, offset 2px, on every interactive element.
Native semantic elements (`<button>`, `<nav>`, `<main>`, `<dialog>`) rather than
div-based reconstructions. Status is never conveyed by color alone — pills carry text,
and the AI accent is always paired with a label.

Minimum target size is 40×40px on web. Native raises this floor: 44×44pt on iOS,
48×48dp with 8dp separation on Android — build to the higher number where a component
is expected to port.

Reduced motion is honoured globally; nothing in the product is load-bearing on
animation.
