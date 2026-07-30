import type { ReactNode } from 'react'

import { cn } from '../lib/ui'

export interface TooltipProps {
  label: string
  side?: 'right' | 'bottom'
  children: ReactNode
}

/**
 * CSS-only — hover/focus-within with a delay is the whole behaviour, so there
 * is no state to manage. Long-press on touch falls out of `:hover` for free.
 *
 * Doc 04: supplementary information only. Anything required to complete a task
 * needs a visible label instead.
 */
export function Tooltip({ label, side = 'right', children }: TooltipProps) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className={cn(
          'rounded-control border-border bg-elevated text-ink text-body-sm shadow-elevated',
          'pointer-events-none absolute z-50 w-max border px-8 py-4 opacity-0',
          // Doc 04: ~400ms delay in, none out — so it doesn't flash on every
          // incidental mouse pass, but disappears immediately on leave.
          'transition-opacity duration-micro delay-0',
          'group-hover:opacity-100 group-hover:delay-[400ms] group-focus-within:opacity-100',
          side === 'right'
            ? 'top-1/2 left-full ml-8 -translate-y-1/2'
            : 'top-full left-1/2 mt-8 -translate-x-1/2',
        )}
      >
        {label}
      </span>
    </span>
  )
}
