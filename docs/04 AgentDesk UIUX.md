# Document 04 — UI/UX Design Brief
### AgentDesk — Visual & Interaction Design Guide

This brief replaces the previous version. Direction is now anchored to two concrete references you provided — **Aave** (aave.com) and **Interfere** (interfere.com) — rather than abstract mood words. Interfere in particular is worth calling out: it's a production-issue triage tool with an inbox, priority pills, assignee avatars, and an AI "suggesting a fix" panel — functionally the same category of product as AgentDesk, just for engineering incidents instead of support tickets. Its dashboard patterns map almost directly onto AgentDesk's Ticket Queue and Ticket Detail. Aave contributes the typographic, gradient-driven marketing/hero treatment, which AgentDesk borrows for its Login screen, onboarding, and empty states — the few places where a large, confident typographic statement matters more than density.

*A note on sourcing: this brief is built from the structural and stylistic patterns visible on both sites (page structure, component types, dark/light theme signals, stated style tags) rather than extracted pixel-for-pixel color values — AgentDesk gets its own token set, deliberately in the same family.*

---

## Design Principles

These principles sit above every other section in this document. When a design decision is ambiguous — a new screen, a new component, a case none of the specifics below quite cover — these are what resolve it, in this order of priority:

- **Clarity over decoration.** If a visual choice doesn't help someone understand the screen faster, it doesn't earn a place on it.
- **Typography over graphics.** Hierarchy and personality come from type weight, size, and spacing first — illustration and imagery are the exception, used deliberately (per Iconography Guidelines), not the default way to add visual interest.
- **Whitespace over borders.** Separation between elements should come from space first; a border or divider line is a fallback for the specific cases where space alone can't do the job (e.g. dense table rows).
- **Consistency over novelty.** A new screen reusing an existing pattern well is a better outcome than a new screen introducing something original-looking. Novelty is spent once, deliberately, on the Signature Element — nowhere else.
- **Motion should reinforce understanding, never distract.** If an animation doesn't help someone track what changed or where something went, it doesn't belong (expanded fully in Motion & Interaction below).
- **Every page should feel like part of the same product.** Someone moving from the Customer Portal to the Agent Console to the Admin Dashboard should never feel like they've opened three different tools, even though the color mode and density differ by design.
- **Use visual hierarchy before using color.** Size, weight, and position should establish what matters most on a screen; color reinforces that hierarchy afterward; it should not be the only tool doing the work (this is also why status is never conveyed by color alone — see Accessibility Considerations).
- **Reduce cognitive load whenever possible.** Every screen should ask the person looking at it to hold as little in their head as possible — this is the underlying reason AgentDesk favors flat status pills over free-form text, monospace for anything numeric, and a single consistent AI-signature color instead of case-by-case labeling.

---

## Aesthetic
**Polished, typographic, minimal SaaS — with a clear split between the "product" surfaces and the "first-touch" surfaces.**

- **Product surfaces** (Agent Console, Admin Dashboard, Ticket Detail) follow **Interfere's** language: dark-mode-first, dense but clean, status conveyed through solid pill badges and avatar-initial chips, an AI-reasoning panel visually distinct from human activity.
- **First-touch surfaces** (Login, onboarding, empty states, the Customer Portal's simpler screens) follow **Aave's** language: big confident typographic statements, generous whitespace, a soft gradient accent, large stat callouts.

Both references share three traits worth locking in everywhere: **typographic** (hierarchy comes from type weight/size, not decoration), **clean/minimal** (no clutter, no unnecessary chrome), and **interactive** (small, deliberate motion on hover/load — both reference sites use a motion library for exactly this, not for flash).

---

## Color Palette

**Dark mode** (default for Agent Console, Admin Dashboard, Ticket Detail — matches Interfere's near-black product surface):

| Role | Hex |
|---|---|
| Canvas | `#0B0B0F` |
| Surface (cards, panels, table rows) | `#16161D` |
| Elevated surface (modals, drawers, dropdowns) | `#1C1C25` |
| Border / divider | `#2A2A35` |
| Ink (primary text) | `#F4F4F6` |
| Muted text (metadata, timestamps) | `#9A9AA5` |

**Light mode** (default for Customer Portal, Login, onboarding — matches Aave's white-based marketing site):

| Role | Hex |
|---|---|
| Canvas | `#FFFFFF` |
| Surface | `#F7F7F9` |
| Border / divider | `#E7E7EB` |
| Ink (primary text) | `#0B0B0F` |
| Muted text | `#6B6B76` |

**Brand gradient** (the one color idea both reference sites share, and AgentDesk's most deliberate visual choice):

| Stop | Hex | Usage |
|---|---|---|
| Gradient start | `#4F7CFF` | Signal blue |
| Gradient end | `#8B5CF6` | Violet |

Used **only** for: the Login/hero headline (gradient text fill), primary CTA buttons, the active-state nav indicator, and — most importantly — **as the marker for anything the AI generated or suggested**. A ticket's AI-drafted reply, an AI-suggested category, an AI confidence chip: all carry the gradient. Everything a human wrote or decided stays flat, solid color. This single rule is what turns "we used a gradient because the references did" into a functional signal instead of decoration.

**Semantic / status colors** (flat fills, not gradient — status needs to be instantly, unambiguously readable, which is exactly how Interfere treats its own priority pills):

| Meaning | Hex |
|---|---|
| Critical / Urgent | `#F05252` |
| High | `#F5A623` |
| Medium | `#8A93A6` |
| Low | `#34D399` |
| SLA breach | `#F05252` |
| SLA at-risk | `#F5A623` |
| Resolved / success | `#34D399` |

**Avatar-initial chips** (assignee indicators, directly mirroring Interfere's "LS / PF / JK" pattern): solid-fill circles, initials in white, colors drawn from a small rotating set adjacent to the brand gradient (blues/violets/teals) so they read as "part of the system" without competing with status colors.

---

## Typography

| Token | Size | Weight | Face | Usage |
|---|---|---|---|---|
| Hero / Display | 40–56px (responsive) | 600–700 | Space Grotesk | Login headline, onboarding "System Ready" screen, empty-state headlines — gradient text fill permitted here only |
| H1 | 32px | 600 | Space Grotesk | Admin Overview page title, stat-callout numbers |
| H2 | 24px | 600 | Space Grotesk | Section headers |
| H3 | 18px | 600 | Inter | Card titles, modal headers |
| Body | 15px | 400 | Inter | Default UI text, table cells, comments |
| Body Small | 13px | 400 | Inter | Metadata, helper text |
| Data / Mono | 13px | 500 | IBM Plex Mono | Ticket IDs, SLA countdowns, durations (e.g. "36 min 47s"), audit diffs — mirrors the code-block/mono treatment Interfere uses for its technical detail views |
| Caption | 12px | 500 | Inter, uppercase, letter-spaced | Table column headers, chip labels |

- **Space Grotesk** for anything typographic-hero-driven — geometric, confident, close in spirit to what both reference sites use for their headline type.
- **Inter** for everything dense (this doesn't change from the previous draft — it's still the right tool for tables and forms at small sizes).
- **IBM Plex Mono** for anything numeric/technical, same rationale as before, reinforced by Interfere's own use of monospace for code and precise durations.

---

## Layout & Grid System

**Desktop (≥1280px)**
- 12-column grid, 24px gutters, content max-width between 1280px and 1440px depending on screen — Ticket Queue, Audit Log, and Reports can use the full 1440px since they're genuinely data-wide; forms and Ticket Detail cap around 960px so paragraphs and label/value pairs don't stretch uncomfortably wide.
- Sidebar: 260px expanded, 72px collapsed to an icon-only rail (see Component Behavior below).
- Content padding: 32px from the outer edge of the content area.
- Dashboard widget spacing: 24px gap between cards in a metric row.
- Form spacing: 16px between individual fields within a group, 32px between distinct field groups (e.g. "Ticket Details" versus "Assignment").

**Tablet (768–1279px)**
- Grid reduces to 8 columns; sidebar defaults to the collapsed 72px rail, expandable on demand rather than permanently hidden.
- Content padding reduces to 24px.
- Dashboard cards reflow from a 4-across row to 2-across.

**Mobile (<768px)**
- Single column; the sidebar concept is replaced entirely — a bottom tab bar for the Customer Portal, an off-canvas drawer for Agent Console/Admin Dashboard.
- Content padding reduces to 16px.
- Dashboard cards stack fully, one per row.

**Consistent spacing between structural elements** (values pull directly from the Spacing System below, so no individual page invents its own number):
- Between page sections: 48px desktop / 32px mobile.
- Between cards in a grid: 24px desktop / 16px mobile.
- Between form groups: 32px; between individual fields in a group: 16px.
- Between table rows: no gap — rows are separated by a 1px hairline border, with 12px of vertical padding inside each row.
- Between navigation items: 4px between individual items, 24px between nav groups/sections.

This system exists so a page built months from now uses the same 24px card gap as the very first dashboard screen, without anyone needing to remember to check.

---

## Design Tokens — Spacing System

| Token | Value | Primary usage |
|---|---|---|
| `space-4` | 4px | Icon-to-label gap; tight inline spacing inside a chip |
| `space-8` | 8px | Gap between a label and its input; spacing between small stacked elements |
| `space-12` | 12px | Table row vertical padding; spacing inside a compact card |
| `space-16` | 16px | Spacing between form fields; gap between cards on mobile; standard card padding |
| `space-24` | 24px | Card padding (desktop); gap between dashboard cards; spacing between nav groups |
| `space-32` | 32px | Modal padding; page content padding (desktop); spacing between form groups |
| `space-48` | 48px | Spacing between major page sections |
| `space-64` | 64px | Spacing above/below a page's typographic hero moment (Login, onboarding) |
| `space-96` | 96px | The most generous whitespace in the product — used once per screen at most, reserved for Aave-inspired hero sections only |

Every page draws its spacing exclusively from this scale — no arbitrary pixel values (no one-off "18px" or "27px" gap invented for a single screen). If a layout seems to need something between two tokens, that's a signal to reconsider the layout, not to add a new value.

---

## Component Style

- **Corners**: 10px on cards, panels, and modals (slightly softer than a purely enterprise tool — matches the "clean/polished" read of both references); 8px on buttons and inputs; fully pill-shaped (999px) on status chips and avatar-initial circles.
- **Definition on dark surfaces**: since Canvas and Surface are both near-black, cards are separated from the page with a 1px hairline border (`#2A2A35`) rather than relying on shadow alone — this is exactly how a dark, dense product UI like Interfere's stays legible without looking murky.
- **Shadows/glow**: soft, low-opacity shadows for anything with true elevation (modals, dropdowns, the AI Draft drawer). Primary CTA buttons and the Login hero get a subtle glow in the brand gradient color at low opacity behind them — the one place a "premium SaaS" glow effect is earned, rather than applied everywhere.
- **Code/diff-style callouts**: for anything showing "what the AI changed or found" (e.g. a reclassification, a suggested SLA rule match), use a bordered monospace block with a subtle diff treatment (removed line muted/strikethrough, added line in the brand gradient's start color) — directly inspired by Interfere's own finding callouts.

---

## Component Behavior

Component Style (above) defines how things look. This section defines how they behave — the states every component needs, so a button on the Login screen and a button in the Admin Dashboard respond identically.

**Buttons**
- Default: solid fill (primary) or outline (secondary), per Component Style.
- Hover: brightness increases by a small, consistent amount (roughly 8%); cursor becomes a pointer.
- Active/pressed: brightness decreases slightly (roughly 5% darker than default), confirming the click registered.
- Disabled: 40% opacity, no hover/active response, cursor becomes not-allowed.
- Focus: a visible 2px focus ring in the gradient's start color (`#4F7CFF`), offset 2px from the button's edge — never removed, even after a mouse interaction.

**Cards**
- Static cards (a metric tile with no click action): no hover response at all — a static card that reacts to hover falsely suggests it's clickable.
- Clickable cards (a ticket row, a Knowledge Base article card): hover lifts the card slightly (2px translateY) with a soft shadow increase; cursor becomes a pointer.

**Tables**
- Row hover: background shifts to a barely-there tint of the elevated-surface color, not a strong highlight.
- Row selected (e.g. a bulk-action checkbox checked): background uses a low-opacity tint of the gradient's start color, persisting until deselected.
- Sticky header: column headers stay pinned during vertical scroll on any table taller than the viewport.
- Sorting indicator: an arrow appears next to the active sort column's label; inactive columns show no icon until hovered, at which point a faint arrow previews the available sort.

**Sidebar**
- Expanded: full labels and icons, 260px wide.
- Collapsed: icons only, 72px wide, with a tooltip on hover revealing the label.
- Active item: a solid left-edge accent bar in the gradient's start color, plus a subtly elevated background — never color alone, per Accessibility Considerations.
- Nested navigation: child items indent 16px from their parent and appear only when that parent section is expanded; only one top-level section stays expanded at a time, so the sidebar never grows indefinitely.

**Inputs**
- Default: 1px border in the border/divider color.
- Focus: border becomes the gradient's start color, plus the same 2px focus ring used on buttons.
- Validation (inline, on blur — not on every keystroke): success shows a small checkmark in the resolved/success green; error shows the field border in the Critical red plus a short, specific message beneath the field, never a vague "invalid input."
- Disabled: reduced-opacity text and border; no focus state possible.

**Dropdowns**
- Open on click, not hover, to stay predictable and touch-friendly; close on selection, an outside click, or Escape.
- Use the Elevated surface color and the soft shadow already defined in Component Style.

**Drawers**
- Slide in from the right on desktop/tablet, from the bottom on mobile; dismissible via an explicit close control, an outside click, or Escape.
- The AI Draft Response drawer specifically always opens with its gradient-accented header visible first, so the "this is AI-generated" signal is the first thing seen, never something scrolled past.

**Modals**
- Center-anchored, background dimmed at low opacity; focus is trapped inside the modal until dismissed.
- Confirmation modals (delete, deactivate) always default focus to the non-destructive action (Cancel), never to the destructive one.

**Tabs**
- Active tab is underlined in the gradient's start color; inactive tabs use muted text with no underline.
- Switching tabs never triggers a full page reload or loses the parent view's scroll position.

**Accordions**
- Closed by default, except when a single item should be pre-expanded for relevance (e.g. the closest FAQ match during ticket creation).
- Expand/collapse animates height only, never fades content in separately from the height change (see Animation Timing below).

**Tooltips**
- Appear on hover (desktop) or long-press (touch), after a short delay (roughly 400ms) so they don't flash on every incidental mouse pass.
- Reserved for supplementary information only — never for content required to complete a task, consistent with the "icons should not replace labels" rule in Iconography Guidelines.

---

## Border Radius
10px on cards, panels, and modals; 8px on buttons and inputs; fully rounded (999px) on chips, badges, and avatars.

---

## Shadows
Flat, hairline-bordered surfaces for dense views (Ticket Queue, Audit Log, Reports) — no shadow noise across dozens of rows. Soft, low-opacity elevation shadows reserved for modals, drawers, and dropdowns. A subtle brand-gradient glow is permitted behind primary CTA buttons and the Login hero only.

---

## Dark / Light Mode
- **Agent Console & Admin Dashboard**: dark by default (matches Interfere), light available and user-toggleable from Account Settings.
- **Customer Portal**: light by default (matches Aave's white-based site) — an occasional visitor submitting or checking a ticket doesn't need a "product" feel, they need something approachable and quick to read.
- **Login screen**: light, typographic, gradient-accented — the one screen every persona sees regardless of their eventual mode preference, so it's designed once, in the Aave-inspired style, rather than themed per role.

---

## Reference Apps

- **Interfere** (interfere.com) — primary reference for all product/dashboard surfaces. Directly informs: the Ticket Queue's inbox-style list, the Ticket Detail header's metadata grid (priority, assignee, status), avatar-initial assignee chips, the AI Insights/Draft Response panel styled as a distinct "reasoning" callout, and an activity feed that visually separates human actions, AI findings, and automation/system events — Interfere itself redesigned its own timeline for exactly that distinction, which is precisely what AgentDesk's audit trail needs.
- **Aave** (aave.com) — primary reference for first-touch surfaces. Directly informs: the Login screen's large typographic headline with gradient text, the Admin Overview's stat-callout row (large numbers, small labels underneath — same device as Aave's "$3.46T / lifetime deposits" bar), and an FAQ/accordion pattern reusable for Knowledge Base article browsing.
- **Linear** — secondary reference, still relevant for information density and restraint in the Ticket Queue table view; doesn't conflict with the Interfere direction.

---

## Key UI Patterns

- **Inbox-style ticket row** (Ticket Queue): avatar-initial chip, title, solid-fill priority pill, affected-user/comment count, relative timestamp — direct pattern match to Interfere's Inbox list.
- **Ticket header metadata grid** (Ticket Detail): Title / Priority / Assignee / Status / Category laid out as label-value pairs, matching Interfere's own ticket header block.
- **SLA timeline scrubber**: a horizontal bar marking Created → Response Due → Resolution Due → Now, adapted from Interfere's H-2/H-1/Now/Fix/H+1 incident scrubber, repurposed here for SLA visualization instead of incident timing.
- **AI reasoning panel**: a bordered, gradient-accented callout for AI-drafted replies or classification reasoning — visually distinct from the plain conversation thread, echoing Interfere's "Suggesting a fix…" block.
- **Diff-style change callouts**: monospace, bordered blocks for showing what the AI changed or found (reclassification, matched SLA rule), styled like a code diff.
- **Activity feed with role-coded entries**: human actions in flat ink color, AI findings/suggestions in the brand gradient, system/automation events in muted grey — one visual system, three meanings, always distinguishable at a glance.
- **Stat-callout row** (Admin Overview): large Space Grotesk/mono numbers with a small caption label underneath, direct pattern match to Aave's stats bar.
- **Typographic hero** (Login, onboarding "System Ready," empty states): one large gradient-fill headline, minimal supporting copy, generous whitespace — Aave's hero treatment, scaled down from a marketing homepage to a single focused moment.
- **FAQ/accordion**: reusable for Knowledge Base browsing and any Help section, matching Aave's FAQ pattern.

---

## Motion & Interaction
Both reference sites use a motion library deliberately, not decoratively — AgentDesk follows the same restraint:
- **Page load**: hero/headline and stat-callout numbers fade/slide in once, on first render only — never on every navigation.
- **Hover**: cards lift slightly (subtle translateY + shadow increase); buttons and pills brighten by a small, consistent amount.
- **List entrance**: ticket queue rows stagger in briefly on first load of a filtered view, not on every re-render.
- **"AI is working" state**: a soft shimmer/pulse on the AI reasoning panel while a classification or draft response is being generated — the same idea as Interfere's live "Suggesting a fix…" indicator.
- **Reduced motion**: every animation above is skipped when `prefers-reduced-motion` is set — nothing here is load-bearing for understanding the interface.

### Motion Principles
- Motion supports usability — it should always answer "where did that go" or "what just happened," never exist for its own sake.
- Motion should never become decoration; if removing an animation wouldn't change whether the interface is understandable, it's a candidate for removal, not addition.
- Animation should reinforce hierarchy — the most important state change (a ticket resolving, an AI suggestion arriving) gets the most deliberate motion; routine interactions get the least.
- Avoid repeated entrance animations — a list that already animated in once should not re-animate on every re-render or every time its parent tab is revisited.
- Avoid distracting movement — no continuous floating, bouncing, or ambient motion anywhere in the product; AgentDesk is a place someone reads carefully, not a place they're entertained.
- Respect `prefers-reduced-motion` everywhere, without exception.

### Animation Timing

| Interaction | Duration | Easing |
|---|---|---|
| Micro-interactions (checkbox, toggle, icon state change) | 150ms | ease-out |
| Buttons (hover/active) | 180ms | ease-in-out |
| Cards (hover lift) | 200ms | ease-out |
| Dropdowns (open/close) | 180ms | ease-out |
| Modals (open/close) | 220ms | ease-out |
| Drawers (slide in/out) | 250ms | ease-out |
| Page transitions | 250ms | ease-in-out |
| **Maximum allowed duration** | **300ms** | — |

Entrances — something appearing for the first time — use ease-out: fast to start, settling gently. Interactions the user is actively driving (hover, drag, toggle) use ease-in-out, so the response feels connected to the input rather than automatic. Nothing in the product animates longer than 300ms; beyond that threshold, motion stops feeling responsive and starts feeling like a delay.

### Scroll Animations

**Allowed** — and only ever once, the first time the element enters the viewport:
- Hero headline (Login, onboarding)
- Hero illustration, where one exists
- KPI/stat-callout cards (Admin Overview)
- Dashboard sections, on first load
- Empty states
- Marketing-style sections, if AgentDesk ever gains a public-facing page
- Feature cards
- FAQ accordion items
- AI Insight panel, on first appearance
- Charts, as they enter the viewport

**Not allowed**, under any circumstance:
- Every paragraph fading in individually — this slows reading down rather than helping it
- Table rows animating repeatedly on every scroll or re-render
- Buttons animating while the page scrolls past them
- Continuous floating or ambient animation
- Scroll-jacking (hijacking the user's scroll input to control pacing)
- Long parallax effects
- Any decorative animation that doesn't correspond to something the user actually needs to notice

The rule of thumb: an element animates once, the first time it's seen, and then behaves like ordinary static content for the rest of the session.

### Loading States
- **Skeleton loaders**: the default for anything with a predictable shape (a ticket list, a table, a dashboard card) — matching the eventual content's layout so nothing "jumps" when real data arrives.
- **AI generation shimmer**: a distinct, gradient-tinted shimmer (the brand gradient at low opacity) specifically for moments where the AI is actively producing something — classifying a ticket, drafting a reply — visually distinguishing "the system is loading data" from "the AI is thinking."
- **Progressive loading**: for long lists (Ticket Queue, Audit Log), render the first visible page immediately and fetch further pages as the user scrolls, rather than blocking on the full dataset.
- **Optimistic UI updates**: actions with a very high success likelihood (marking a ticket resolved, adding a tag) update the UI immediately and reconcile silently with the server response; a failure rolls back with a clear inline message rather than a jarring page-level error.
- **Success transitions**: a brief, single state change (a checkmark replacing a spinner for under a second) rather than a persistent "Success!" banner the user has to dismiss.
- Traditional spinning loaders are avoided wherever a skeleton or shimmer can substitute — a spinner communicates "wait" with no information, while a skeleton communicates "this is roughly what's coming."

---

## Responsive Design

Beyond the breakpoints themselves (Layout & Grid System, above), this section defines how each part of the interface actually adapts — not just when it resizes, but what changes structurally.

**Navigation**
- Desktop: full sidebar, expanded by default, every item labeled.
- Tablet: sidebar defaults to the collapsed 72px icon rail, expandable on demand.
- Mobile: the sidebar concept is replaced — a bottom tab bar for the Customer Portal, an off-canvas drawer (triggered from the top bar) for Agent Console and Admin Dashboard.

**Tables**
- Desktop: full table, every column visible, sticky header, inline row actions on hover.
- Tablet: lower-priority columns (e.g. "Requester" on an Agent's own queue view, where the assignee matters more) collapse behind an expandable row rather than disappearing entirely.
- Mobile: tables transform into stacked cards — one ticket per card, preserving the inbox-row pattern (avatar chip, title, priority pill, timestamp) rather than forcing a horizontally-scrolling table, which is difficult to use on a touch screen.

**Cards**
- Desktop: multi-column grid, typically 3–4 across for dashboard metrics.
- Tablet: 2-across.
- Mobile: single column, full width.

**Drawers**
- Desktop/tablet: slide in from the right, roughly 40% of viewport width; the parent content stays visible and dimmed behind it.
- Mobile: slide up from the bottom, full width, roughly 85% of viewport height — behaving like a bottom sheet rather than a side panel, which is the more touch-friendly convention.

**Sidebar collapse**
- The transition between expanded and collapsed states is a width animation only, never a fade — a fade would momentarily hide navigation the user might be mid-click on.

**Modal sizing**
- Desktop: fixed max-width (480px for confirmations, 640px for forms), centered.
- Mobile: modals expand to near-full-width with margin; confirmation modals specifically become full-bleed bottom sheets rather than centered boxes, keeping destructive-action confirmations reachable by thumb.

---

## Mobile Responsiveness
- **Customer Portal**: fully responsive, mobile-first where it matters — sidebar collapses into a bottom tab bar (My Tickets, New Ticket, Knowledge Base, Notifications), consistent with App Flow Document 03.
- **Agent Console / Admin Dashboard**: responsive down to tablet width; below that, the sidebar becomes an off-canvas drawer and dense tables reflow into stacked cards, each retaining the inbox-row pattern (avatar chip, title, priority pill, timestamp) rather than a squeezed horizontal table.
- Minimum 44px tap targets on any touch-accessible control, across all three surfaces.

---

## Iconography Guidelines

- **Preferred icon library**: Lucide — open, consistent, line-based, broad coverage, and easy to theme; its geometric character sits naturally alongside Inter and Space Grotesk.
- **Stroke weight**: 1.5px throughout. Heavier strokes read as playful, which conflicts with the typographic-minimal direction; thinner strokes disappear at small sizes inside a dense table.
- **Sizes**: 16px for inline/table icons, 20px for navigation and toolbar icons, 24px for empty-state and standalone icons — no other sizes, so icons never look subtly mismatched next to one another.
- **When icons should be used**: to reinforce a label the user already has (a bell for notifications, a paperclip for attachments), to indicate an action available on hover (assign, escalate, delete), or as the sole content of a very well-established, universally recognized control (a close "×," a chevron for expand/collapse).
- **When icons should NOT replace labels**: any primary navigation item; any button whose action isn't universally obvious (an icon-only "Escalate" button is a guessing game — "Escalate" with a small icon beside it is not); and anything a screen reader user needs to understand without depending on a tooltip.
- **Avatar rules**: solid-fill initials circles (per Color Palette) are the default for every user in the system — no photo uploads during the prototype phase, so every avatar looks consistent regardless of whether a user has set a profile picture.
- **Illustration style**: minimal, single-color line illustrations (using the Ink color, never the brand gradient) for onboarding or empty-state artwork — illustration isn't the place for maximalism here; it should read as an extension of the typography, not a separate visual language.
- **Empty-state artwork**: a small, simple line illustration paired with the typographic hero treatment (per Key UI Patterns) — the illustration supports the headline, it doesn't replace the need for one.

---

## Accessibility Considerations
- **Contrast**: all text/background pairs meet WCAG AA (4.5:1 body, 3:1 large text/UI). The brand gradient is used as a background (with white/ink text) or for large display type — never as small body-size text directly on Canvas, where a gradient would risk failing contrast in its lighter stop.
- **Color is never the only signal**: priority/status pills always carry a text label, not color alone; the AI-vs-human distinction in the activity feed is reinforced with a small icon (a spark/asterisk glyph for AI entries), not gradient color alone.
- **Keyboard focus**: visible 2px focus ring in the gradient's start color (`#4F7CFF`) on every interactive element; all core flows fully keyboard-operable.
- **Reduced motion**: respected everywhere, per the Motion & Interaction section above.
- **Text resizing**: layouts hold up under browser-level zoom without clipping, particularly in the dense dark-mode table views.
- **Screen reader labeling**: status pills, SLA scrubber positions, and AI reasoning panels all carry descriptive `aria-label`s (e.g. "AI-suggested category: Billing, 92 percent confidence") rather than relying on color or icon alone.

---

## AI Design Consistency Rules

This section exists specifically for whichever AI coding agent implements AgentDesk's frontend — including future sessions that don't share this conversation's context. When a design decision is ambiguous, these rules resolve it before anything else does:

- **Never invent new colors.** Every color used in the product comes from the palette defined above (Color Palette, Semantic colors, or the brand gradient). If a screen seems to need a color that isn't there, that's a signal to reconsider the design, not to add a hex value.
- **Never invent additional gradients.** There is exactly one gradient in this product, and it carries exactly one meaning (see Signature Element below). A second gradient — even a subtle one — breaks that meaning.
- **Never introduce a new border radius.** Every rounded corner uses one of the three values defined in Border Radius (10px, 8px, or 999px) — no exceptions for "just this one card."
- **Never introduce new shadow styles.** Use the elevation levels already defined in Shadows: flat/hairline for dense views, soft elevation for overlays, gradient glow reserved for primary CTAs and the Login hero only.
- **Never introduce new typography scales.** Every heading, body, and data size comes from the Typography table above. A screen that seems to need something between H2 and H3 should use H3 with a weight change, not a new intermediate size.
- **Reuse existing components before creating new ones.** Before building a new pattern, check Key UI Patterns and Component Behavior first — most needs (a list of things, a status, a confirmation, a panel of details) are already covered.
- **Follow the spacing system exactly.** Every margin, padding, and gap uses a token from the Spacing System — no arbitrary pixel values.
- **Use existing interaction patterns.** A new feature's hover, focus, and loading states should match the equivalent existing component's behavior (Component Behavior) rather than inventing new ones.
- **Every new page should feel like it was designed by the same team.** If a new screen looks like it belongs to a different product, that's the signal to return to this document, not to ship it.

---

## Avoid

The following are explicitly out of bounds anywhere in AgentDesk, regardless of how a future request is phrased:

- Glassmorphism (frosted-glass blur panels)
- Neumorphism (soft-embossed, same-color-on-same-color shadows)
- Material Design styling (Google's specific elevation, ripple, and FAB conventions — a different design language from this one)
- Bootstrap-style defaults (default form controls, default card styling, default spacing)
- Heavy, multi-layer drop shadows
- Neon or oversaturated colors
- Oversaturated or multi-hue "rainbow" gradients — the brand gradient is a deliberate two-stop blue-to-violet, nothing louder
- Randomly-timed or randomly-triggered animations
- Floating widgets that hover persistently over content (chat bubbles, floating action buttons that aren't a deliberate, singular exception)
- Decorative effects that don't correspond to a piece of information (background blobs, unnecessary illustration, ambient particle effects)
- Inconsistent spacing (any value outside the Spacing System)
- More than two font families in the interface at once (Space Grotesk + Inter, with IBM Plex Mono reserved strictly for data — never a third display or body face)
- Multiple CTA colors (the brand gradient is the only primary-action treatment; a second "primary" color competing for attention undermines the AI-signature rule)
- Different border radii on similar components (a 10px card next to a 12px card is a bug, not a variation)

---

## Signature Element
**The brand gradient is reserved for exactly one meaning across the entire product: this was touched by the AI.** A gradient-filled headline on the Login screen is the one deliberate exception (first impression, not a functional signal), but everywhere inside the actual product — Ticket Detail, the Draft Response drawer, AI Insight chips, the activity feed — gradient means "the model produced or influenced this," full stop, and flat solid color means a human did. That rule is what makes borrowing a gradient-heavy aesthetic from two marketing-forward reference sites still make sense for an internal, AI-native ops tool: the gradient isn't decoration carried over from the references, it's the exact visual vocabulary AgentDesk needs to keep its human-in-the-loop design (locked in since the TRD, Document 02) legible at a glance.
