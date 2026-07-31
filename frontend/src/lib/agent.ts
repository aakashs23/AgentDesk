/**
 * The Agent Console's pure decision logic, kept out of the components so it can
 * be asserted in `npm run selfcheck`. Everything here is a function of its
 * arguments — no React, no fetch.
 */
// Explicit extension: `scripts/ui.selfcheck.ts` imports this module under
// Node's nodenext resolution, which requires one.
import type { TicketStatus } from './types.ts'

// --- Status transitions (App Flow §10, mirroring the workflow engine) --------

/**
 * The legal moves, staff-side. This duplicates the backend's `TRANSITIONS` on
 * purpose: the engine stays the authority and rejects anything illegal, this
 * only decides which buttons are worth showing. `closed → reopened` is absent
 * because it goes through `POST /tickets/{id}/reopen`, not the status endpoint,
 * and `reopened → in_progress` is absent because the server does it itself.
 */
const NEXT: Partial<Record<TicketStatus, TicketStatus[]>> = {
  new: ['open'],
  open: ['in_progress'],
  in_progress: ['on_hold', 'resolved'],
  on_hold: ['in_progress'],
  resolved: ['closed'],
}

export function nextStatuses(status: TicketStatus): TicketStatus[] {
  return NEXT[status] ?? []
}

// --- SLA scrubber (Doc 04 "SLA timeline scrubber", App Flow §16) ------------

export type SlaState = 'ok' | 'risk' | 'breach' | 'met'

export interface SlaMark {
  label: string
  /** Position along the bar, 0–1. */
  at: number
  iso: string
}

export interface SlaTimeline {
  marks: SlaMark[]
  /** Where "now" (or resolution, once resolved) sits, 0–1. */
  progress: number
  state: SlaState
}

/** Doc 03 §16 step 4: a warning fires before the breach, so the bar turns
 *  amber over the last quarter of the resolution window rather than only
 *  going red once it is already too late. */
const RISK_FRACTION = 0.75

export function slaTimeline(
  ticket: {
    created_at: string
    response_due_at: string | null
    resolution_due_at: string | null
    resolved_at: string | null
  },
  now = Date.now(),
): SlaTimeline {
  const start = Date.parse(ticket.created_at)
  const response = ticket.response_due_at ? Date.parse(ticket.response_due_at) : null
  const resolution = ticket.resolution_due_at ? Date.parse(ticket.resolution_due_at) : null
  const resolved = ticket.resolved_at ? Date.parse(ticket.resolved_at) : null

  // A resolved ticket's clock stops at resolution — showing a live "now" on a
  // finished ticket would keep pushing it toward a breach it never had.
  const head = resolved ?? now
  const end = Math.max(head, resolution ?? head, response ?? head, start + 1)
  const span = end - start || 1
  const at = (t: number) => Math.min(1, Math.max(0, (t - start) / span))

  const marks: SlaMark[] = [{ label: 'Created', at: 0, iso: ticket.created_at }]
  if (response)
    marks.push({ label: 'Response due', at: at(response), iso: ticket.response_due_at! })
  if (resolution) {
    marks.push({ label: 'Resolution due', at: at(resolution), iso: ticket.resolution_due_at! })
  }

  let state: SlaState = 'ok'
  if (resolution) {
    if (head > resolution) state = 'breach'
    else if (resolved) state = 'met'
    else if (head - start >= (resolution - start) * RISK_FRACTION) state = 'risk'
  } else if (resolved) {
    state = 'met'
  }

  return { marks, progress: at(head), state }
}

// --- @mention autocomplete (writes `comment_mentions` server-side) ----------

/**
 * The backend matches `@someone@example.com` — a full email after the `@`
 * (`app/tickets/service.py::_MENTION_RE`). So the composer must insert an
 * address, not a display name, and this finds the token being typed.
 *
 * Returns null when the caret is not inside a mention: no `@` on this word, or
 * the token already reads as a complete address (nothing left to suggest).
 */
export function mentionQuery(text: string, caret: number): { query: string; start: number } | null {
  const before = text.slice(0, caret)
  const start = before.lastIndexOf('@')
  if (start === -1) return null
  // Must start a word, otherwise the '@' inside a finished address re-triggers.
  if (start > 0 && !/\s/.test(before[start - 1])) return null
  const query = before.slice(start + 1)
  if (/\s/.test(query)) return null
  return { query, start }
}

/** Replaces the in-progress token with the chosen address, plus a trailing
 *  space so the next word doesn't re-open the menu. */
export function applyMention(
  text: string,
  start: number,
  caret: number,
  email: string,
): { text: string; caret: number } {
  const inserted = `@${email} `
  return {
    text: text.slice(0, start) + inserted + text.slice(caret),
    caret: start + inserted.length,
  }
}

/** Name-or-address substring match, so typing either half finds the person. */
export function matchPeople<T extends { full_name: string; email: string }>(
  people: T[],
  query: string,
  limit = 5,
): T[] {
  const q = query.toLowerCase()
  return people
    .filter((p) => p.full_name.toLowerCase().includes(q) || p.email.toLowerCase().includes(q))
    .slice(0, limit)
}

// --- AI confidence tiers (App Flow §14) -------------------------------------

/** What each tier means for the agent — the reason the tier is shown at all. */
export const TIER_COPY: Record<string, { label: string; action: string }> = {
  high: {
    label: 'High confidence',
    action: 'Auto-routed to the predicted category. Correct it if the model got it wrong.',
  },
  medium: {
    label: 'Medium confidence',
    action: 'Suggested, not applied — confirm it or correct it before routing finalises.',
  },
  low: {
    label: 'Low confidence',
    action: 'Manual classification required. Set the category and priority yourself.',
  },
}

/** Seconds → "4h 12m", for resolution-time metrics. */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '—'
  const total = Math.round(seconds / 60)
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}
