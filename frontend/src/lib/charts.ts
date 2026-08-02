/**
 * Shared Recharts styling — Doc 07 §19.
 *
 * "Remove heavy gridlines": the grid is horizontal-only and dashed, the axis
 * lines and tick marks are gone entirely, and the numbers do the work. Defined
 * once because three screens draw charts and a fourth will; the alternative is
 * four subtly different sets of axes.
 */

export const chartGrid = {
  stroke: 'var(--color-border)',
  strokeDasharray: '3 3',
  vertical: false,
} as const

export const chartAxis = {
  tick: { fill: 'var(--color-muted)', fontSize: 12 },
  axisLine: false,
  tickLine: false,
} as const

/** §19: white surface at Elevation 2, exact values on hover. */
export const chartTooltip = {
  contentStyle: {
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-card)',
    boxShadow: 'var(--shadow-card)',
    color: 'var(--color-ink)',
  },
} as const

/** Bar charts get a hover band; lines don't, so it stays opt-in. */
export const chartCursor = { fill: 'var(--color-sunken)' } as const

export const chartLegend = { wrapperStyle: { color: 'var(--color-muted)' } } as const
