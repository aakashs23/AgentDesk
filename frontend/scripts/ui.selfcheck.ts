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
  formatTicketId,
  initials,
  needsExactMatch,
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

console.log('ui.selfcheck: all assertions passed')
