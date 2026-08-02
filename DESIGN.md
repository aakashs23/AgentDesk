# Design

The visual system of record for AgentDesk. Derived from **Doc 07 — Master UI/UX Design
Specification**, which supersedes Doc 04. Where Doc 07 is silent (type scale, dark
theme, AI provenance) this file decides, and those decisions are marked **[resolved]**.
Doc 07 stays the source for component-level detail (row heights, drawer widths,
toast anatomy); this file holds the tokens code is written against.

Tokens live only in `frontend/src/index.css`. No component invents a value.

## Theme

Light-first on every surface — Portal, Agent Console, Admin. The per-surface split from
Doc 04 (dark console, light portal) is retired. **[resolved]** A full dark scheme is
authored alongside it, not derived by inversion, because iOS and Android both treat
dark as a first-class appearance and the app is `adaptive`.

Color strategy: **restrained**. Neutral surfaces, one blue carrying interaction, one
violet carrying AI provenance, semantics for status. Nothing else is colored.

## Color

### Light (default)

| Role | Value | Use |
|---|---|---|
| `--color-canvas` | `#F9FAFB` | Page background, sidebar |
| `--color-surface` | `#FFFFFF` | Cards, header, modals, drawers, table rows |
| `--color-sunken` | `#F3F4F6` | Inputs at rest, row hover, skeletons, search pill |
| `--color-border` | `#E5E7EB` | Control borders, chart axes |
| `--color-divider` | `#F3F4F6` | Table row rules, header underline |
| `--color-ink` | `#111827` | Primary text |
| `--color-muted` | `#6B7280` | Metadata, labels, table headers, empty-state icons |
| `--color-primary` | `#0066FF` | Interactive text, links, focus rings, borders, active nav |
| `--color-primary-fill` | `#0066FF` | Solids carrying a white label. Identical in dark |
| `--color-primary-hover` | `#0052CC` | Primary button hover |
| `--color-primary-tint` | `rgb(0 102 255 / 0.08)` | Active nav fill, selected row |
| `--color-ai` | `#7C3AED` | AI provenance: text, borders, icons |
| `--color-ai-fill` | `#7C3AED` | AI solids under white text. Identical in dark |
| `--color-ai-tint` | `rgb(124 58 237 / 0.08)` | AI panel and chip fills |
| `--color-critical` | `#EF4444` | Destructive actions, errors (`--color-sla-breach` matches) |
| `--color-high` | `#F59E0B` | High priority (`--color-sla-risk` matches) |
| `--color-success` | `#10B981` | Resolved, success toasts (`--color-low` matches) |
| `--color-medium` | `#6B7280` | Medium priority, SLA timer at rest |

`#9CA3AF` from Doc 07 §28 is **not** used for text or meaningful icons — it lands at
2.5:1 on white. Empty-state icons use `--color-muted`. **[resolved]**

### Dark **[resolved]**

Authored on the same blue-gray neutral family as the ink color, so the two schemes read
as one product. Elevation is tonal (canvas → surface → elevated), with shadow used only
under overlays.

| Role | Value |
|---|---|
| `--color-canvas` | `#0B0E14` |
| `--color-surface` | `#141821` |
| `--color-elevated` | `#1B2029` |
| `--color-sunken` | `#1E232D` |
| `--color-border` | `#262C38` |
| `--color-divider` | `#1E232D` |
| `--color-ink` | `#F3F4F6` |
| `--color-muted` | `#9CA3AF` |
| `--color-primary` | `#5B9BFF` (text/links/borders) |
| `--color-ai` | `#A78BFA` (text/icons/borders) |

Only the blue and the violet change. `#0066FF` and `#7C3AED` fall to ~3.1–3.6:1 as text
on these surfaces, so the text values lighten while the `-fill` pair stays put — a
lightened fill under a white label fails in the other direction.

The semantics (`critical`, `high`, `success`, `medium`, the SLA pair) do **not** change
between schemes: each already clears 4.5:1 as text on the dark surfaces *and* carries
white on its own fill, which is mostly what they are — status pills.

### The AI rule

**Flat violet marks anything the model produced or suggested** — drafted replies,
suggested categories and priorities, confidence chips, the reasoning panel, chat-bot
turns. **[resolved]** It replaces Doc 04's brand gradient, which is retired entirely
along with gradient text. Human-authored content stays neutral. The accent never
appears decoratively, and is always paired with a label, never carrying the meaning
alone.

## Typography

One UI family plus mono. Space Grotesk is dropped. **[resolved]** Fixed rem steps, no
fluid clamps — the ratio is ~1.12 and users view at consistent DPI.

- `--font-sans`: `Inter, system-ui, sans-serif` — everything.
- `--font-mono`: `'IBM Plex Mono', ui-monospace, monospace` — ticket IDs, timestamps,
  durations, metrics, SLA counters. Anything numeric that gets compared column to column.

Token names are semantic rather than sized (`body`, not `sm`), which is why the
Doc 04 → Doc 07 rescale changed values without touching a single call site.

| Token | Size | Weight / use |
|---|---|---|
| `--text-caption` | 12px | Table headers (500, uppercase), captions, inline error text |
| `--text-body-sm` | 13px | Form labels (500), dense metadata |
| `--text-data` | 13px | Mono — ids, timestamps, durations, SLA counters |
| `--text-body` | 14px | Body, inputs, buttons, table cells |
| `--text-h3` | 18px | Card and empty-state titles (600) |
| `--text-h2` | 20px | Section headings (600) |
| `--text-h1` | 24px | Page titles (600) |
| `--text-hero` | 32px | Dashboard metrics, Login headline (600) |

Line height 1.5 for prose, 1.35 for headings, 1.2 for data. Prose caps at 70ch.
Headings use `text-wrap: balance`, long prose `text-wrap: pretty`.

On native, these map to Dynamic Type styles (iOS) and Material roles (Android) rather
than shipping as fixed points.

## Space & shape

4pt baseline grid. Tokens: `4 8 12 16 24 32 48 64`. Dashboard gutter 24px, page padding
32px, content wrapper capped at 1152px.

Radii — exactly four: `--radius-sm` 4px (chips, tags, small badges), `--radius-md` 8px
(buttons, inputs, sidebar items), `--radius-lg` 16px (cards, modals, drawers, popovers),
`--radius-pill` 9999px (avatars, search, status pills).

Elevation:
- `--shadow-card`: `0 4px 6px -1px rgb(0 0 0 / .05), 0 2px 4px -1px rgb(0 0 0 / .03)`
- `--shadow-overlay`: `0 25px 50px -12px rgb(0 0 0 / .25)`

Cards are borderless in light (shadow does the separating) and border-only in dark,
where shadows read as nothing. Never nest a card in a card.

## Layout

- **Sidebar** 260px, canvas-colored, persistent ≥1024px, drawer below. Items 32px tall,
  `--radius-md`. Active state is a `--color-primary-tint` fill with primary-colored
  label — **not** a left border stripe.
- **Header** 64px, surface-colored, 1px divider beneath, sticky, `backdrop-filter:
  blur(12px)` once content scrolls under it. Holds breadcrumbs, the search pill that
  opens the command palette, and a 32px avatar.
- **Tables** 48px compact / 64px comfortable rows, sticky headers, full-row click,
  `--color-sunken` on hover.
- **Forms** single column, labels 8px above the input, inputs sized to their data.
- Breakpoints `sm` 640 / `md` 768 (sidebar collapses) / `lg` 1024 / `xl` 1280. Grids
  step 3 → 2 → 1.

## Motion

Fast, purposeful, interruptible. Nothing is load-bearing on animation.

- Micro (buttons, toggles, hovers): 150ms `ease-out`
- Macro (modals, popovers): 250ms `cubic-bezier(.16, 1, .3, 1)`; modals scale 0.95 → 1
- Drawers: 300ms `cubic-bezier(.2, .8, .2, 1)` from the right edge
- Fades: linear
- Dropdowns: 150ms close delay on mouse-leave

Skeletons (`--color-sunken`, left-to-right shimmer) mean data is loading. Anything over
300ms shows a loading state. `prefers-reduced-motion` disables all of it globally.

## Components

Every interactive component defines default, hover, focus, active, disabled, loading,
and error. Variants: primary / secondary / ghost / danger. Sizes: sm / md / lg.
Buttons 36px standard, 44px large. Icons are outlined, 1.5–2px stroke, 16/20/24px.
Doc 07 §11–30 holds the rest.

## Accessibility

4.5:1 minimum on all text. Focus ring 3px `--color-primary`, 2px offset, on every
interactive element, never removed. Native semantic elements throughout. Status is never
color alone. Targets 40×40px on web, 44pt iOS, 48dp Android.
