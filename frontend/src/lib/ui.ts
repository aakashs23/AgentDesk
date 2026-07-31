export type ClassValue = string | false | null | undefined

export function cn(...parts: ClassValue[]) {
  return parts.filter(Boolean).join(' ')
}

/**
 * Doc 04, Accessibility: a visible 2px ring in the gradient's start colour on
 * every interactive element. Defined once so no component can drift.
 */
export const focusRing =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-start'

/** Doc 04 minimum tap target on touch-accessible controls. */
export const tapTarget = 'min-h-[44px] min-w-[44px]'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ThemeMode = 'light' | 'dark'

/**
 * Doc 04 assigns mode per surface, not per OS setting: Agent Console and Admin
 * Dashboard are dark-first, Customer Portal and Login are light-first.
 */
export function surfaceDefault(pathname: string): ThemeMode {
  return pathname.startsWith('/agent') || pathname.startsWith('/admin') ? 'dark' : 'light'
}

/** A stored `system` preference resolves to the surface default; an explicit
 *  light/dark preference overrides it everywhere. */
export function resolveTheme(preference: ThemePreference, pathname: string): ThemeMode {
  return preference === 'system' ? surfaceDefault(pathname) : preference
}

/**
 * `/admin` is a prefix of `/admin/users`, so a plain prefix match would light
 * up two sidebar items at once. An item needs exact matching only when another
 * item nests underneath it.
 */
export function needsExactMatch(allPaths: string[], to: string) {
  return allPaths.some((p) => p !== to && p.startsWith(`${to}/`))
}

/**
 * `tickets.display_id` is a bare integer in the database and is formatted at
 * the app layer as `AGT-1042` (Doc 05, tickets table).
 */
export function formatTicketId(displayId: number | null | undefined) {
  return displayId === null || displayId === undefined ? '' : `AGT-${displayId}`
}

/**
 * Doc 04 forbids conveying status by colour alone, so every status renders as a
 * text label; this just supplies the human-readable form of the DB value.
 */
export const STATUS_LABELS: Record<string, string> = {
  new: 'New',
  open: 'Open',
  in_progress: 'In Progress',
  on_hold: 'On Hold',
  resolved: 'Resolved',
  closed: 'Closed',
  reopened: 'Reopened',
}

export function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status
}

// Descending units with the divisor that carries into the next one up.
const TIME_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['second', 60],
  ['minute', 60],
  ['hour', 24],
  ['day', 7],
  ['week', 4.35],
  ['month', 12],
  ['year', Number.POSITIVE_INFINITY],
]

/** Compact relative time for ticket rows and activity ("3 hours ago"). */
export function relativeTime(iso: string, now = Date.now()) {
  const format = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  let value = (new Date(iso).getTime() - now) / 1000
  for (const [unit, step] of TIME_UNITS) {
    if (Math.abs(value) < step) return format.format(Math.round(value), unit)
    value /= step
  }
  return format.format(Math.round(value), 'year')
}

/** Human-readable file size for the attachment list. */
export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`
}

export function initials(fullName: string) {
  const parts = fullName.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}
