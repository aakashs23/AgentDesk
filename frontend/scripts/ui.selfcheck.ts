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

console.log('ui.selfcheck: all assertions passed')
