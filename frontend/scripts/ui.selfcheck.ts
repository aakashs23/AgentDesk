/**
 * Self-check for the pure decision logic behind the app shell. Run it with:
 *
 *   npm run selfcheck
 *
 * No test framework — Node strips the types and `assert` does the rest. These
 * are the functions whose failure modes are silent (a sidebar item that stays
 * lit, a surface that renders in the wrong mode) rather than loud.
 */
import assert from 'node:assert/strict'

import {
  applyMention,
  formatDuration,
  matchPeople,
  mentionQuery,
  nextStatuses,
  slaTimeline,
} from '../src/lib/agent.ts'
import { MAX_ATTACHMENT_BYTES, validateFile } from '../src/lib/attachments.ts'
import {
  formatBytes,
  formatTicketId,
  initials,
  needsExactMatch,
  relativeTime,
  resolveTheme,
  surfaceDefault,
} from '../src/lib/ui.ts'

// Doc 04: product surfaces are dark-first, first-touch surfaces light-first.
assert.equal(surfaceDefault('/agent/queue'), 'dark')
assert.equal(surfaceDefault('/admin'), 'dark')
assert.equal(surfaceDefault('/portal/tickets'), 'light')
assert.equal(surfaceDefault('/login'), 'light')

// An explicit preference beats the surface default in both directions.
assert.equal(resolveTheme('system', '/agent/queue'), 'dark')
assert.equal(resolveTheme('light', '/agent/queue'), 'light')
assert.equal(resolveTheme('dark', '/portal/tickets'), 'dark')
assert.equal(resolveTheme('system', '/portal/tickets'), 'light')

// Only an item with something nested under it needs exact matching, otherwise
// /admin would stay highlighted while sitting on /admin/users.
const adminPaths = ['/admin', '/admin/users', '/admin/sla']
assert.equal(needsExactMatch(adminPaths, '/admin'), true)
assert.equal(needsExactMatch(adminPaths, '/admin/users'), false)
// A shared prefix that isn't a path segment must not count as nesting.
assert.equal(needsExactMatch(['/agent/queue', '/agent/queues-archive'], '/agent/queue'), false)

// Doc 05: display_id is a bare integer, formatted at the app layer.
assert.equal(formatTicketId(1042), 'AGT-1042')
assert.equal(formatTicketId(null), '')
assert.equal(formatTicketId(undefined), '')

assert.equal(initials('Demo Team Lead'), 'DL') // first + last, never the middle
assert.equal(initials('Cher'), 'C')
assert.equal(initials('  spaced   out  '), 'SO')
assert.equal(initials(''), '?')

// Attachment gate (Doc 03 §13): type is checked before size, and both messages
// name the offending file. Images pass by prefix; anything else needs the list.
assert.equal(validateFile({ name: 'a.png', type: 'image/png', size: 1024 }), null)
assert.equal(validateFile({ name: 'a.pdf', type: 'application/pdf', size: 1024 }), null)
assert.match(
  validateFile({ name: 'a.exe', type: 'application/x-msdownload', size: 10 }) ?? '',
  /unsupported file type/,
)
assert.match(
  validateFile({ name: 'big.png', type: 'image/png', size: MAX_ATTACHMENT_BYTES + 1 }) ?? '',
  /exceeds the 10MB limit/,
)
// Exactly at the limit is allowed — the server uses the same boundary.
assert.equal(
  validateFile({ name: 'edge.png', type: 'image/png', size: MAX_ATTACHMENT_BYTES }),
  null,
)
// A disallowed type that is also oversized reports the type, not the size.
assert.match(
  validateFile({ name: 'x.exe', type: 'application/x-msdownload', size: 1e9 }) ?? '',
  /unsupported file type/,
)

assert.equal(formatBytes(512), '512 B')
assert.equal(formatBytes(2048), '2.0 KB')
assert.equal(formatBytes(10 * 1024 * 1024), '10 MB')

// Relative time is anchored to an explicit `now` so this never flakes.
const noon = Date.parse('2026-01-01T12:00:00Z')
assert.match(relativeTime('2026-01-01T09:00:00Z', noon), /3 hours ago/)
assert.match(relativeTime('2026-01-01T11:59:30Z', noon), /30 seconds ago/)

// --- Agent Console (Phase 11) ---

// App Flow §10: only the legal moves are offered. Reopen goes through its own
// endpoint and reopened → in_progress is the server's to make, so neither
// appears as a button.
assert.deepEqual(nextStatuses('new'), ['open'])
assert.deepEqual(nextStatuses('in_progress'), ['on_hold', 'resolved'])
assert.deepEqual(nextStatuses('resolved'), ['closed'])
assert.deepEqual(nextStatuses('closed'), [])
assert.deepEqual(nextStatuses('reopened'), [])

// SLA scrubber. Anchored to an explicit `now` so none of this can flake.
const created = '2026-01-01T00:00:00Z'
const t = (hours: number) => Date.parse(created) + hours * 3600_000
const ticket = {
  created_at: created,
  response_due_at: '2026-01-01T02:00:00Z',
  resolution_due_at: '2026-01-01T10:00:00Z',
  resolved_at: null,
}

// One hour in: 10% of the way to the resolution target, comfortably fine.
const early = slaTimeline(ticket, t(1))
assert.equal(early.state, 'ok')
assert.equal(early.marks.length, 3) // Created, Response due, Resolution due
assert.ok(early.progress > 0 && early.progress < 0.2)

// Past 75% of the window the bar warns before, not after, the breach.
assert.equal(slaTimeline(ticket, t(8)).state, 'risk')
assert.equal(slaTimeline(ticket, t(11)).state, 'breach')

// A resolved ticket's clock stops at resolution — it must not keep drifting
// toward a breach it never had.
const resolved = { ...ticket, resolved_at: '2026-01-01T03:00:00Z' }
assert.equal(slaTimeline(resolved, t(99)).state, 'met')
// Resolved after the target is still a breach, however late the read happens.
assert.equal(slaTimeline({ ...ticket, resolved_at: '2026-01-02T00:00:00Z' }, t(99)).state, 'breach')

// No SLA policy matched: one mark, and nothing claims a breach.
const noPolicy = slaTimeline(
  { created_at: created, response_due_at: null, resolution_due_at: null, resolved_at: null },
  t(99),
)
assert.equal(noPolicy.marks.length, 1)
assert.equal(noPolicy.state, 'ok')

// Every mark stays inside the bar.
for (const mark of slaTimeline(ticket, t(99)).marks) {
  assert.ok(mark.at >= 0 && mark.at <= 1, `${mark.label} at ${mark.at}`)
}

// @mention: the token is only live while the caret sits inside it.
assert.deepEqual(mentionQuery('hey @dem', 8), { query: 'dem', start: 4 })
assert.equal(mentionQuery('hey there', 9), null)
// A completed address contains an '@' that must not re-open the menu.
assert.equal(mentionQuery('hey @a@b.com and', 16), null)
// An '@' mid-word (an email pasted without the mention prefix) is not a mention.
assert.equal(mentionQuery('mail a@b', 8), null)

// Insertion replaces the token and leaves the caret after a trailing space, so
// the backend sees exactly `@address` — the form comment_mentions matches.
const applied = applyMention('hey @dem', 4, 8, 'demo@agentdesk.dev')
assert.equal(applied.text, 'hey @demo@agentdesk.dev ')
assert.equal(applied.caret, applied.text.length)
// Text after the caret survives the insertion.
assert.equal(applyMention('hi @de rest', 3, 6, 'x@y.dev').text, 'hi @x@y.dev  rest')

const people = [
  { full_name: 'Demo Agent', email: 'agent@agentdesk.dev' },
  { full_name: 'Team Lead', email: 'lead@agentdesk.dev' },
]
assert.equal(matchPeople(people, 'lead').length, 1) // matches the name
assert.equal(matchPeople(people, 'agentdesk').length, 2) // matches both addresses
assert.equal(matchPeople(people, '').length, 2) // an empty query lists everyone

assert.equal(formatDuration(null), '—')
assert.equal(formatDuration(90), '2m') // rounds to the nearest minute
assert.equal(formatDuration(3600 * 4 + 720), '4h 12m')

console.log('ui.selfcheck: all assertions passed')
