import type { HTMLAttributes } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /**
   * Doc 04: a static card must not react to hover at all — a hover response on
   * something unclickable falsely advertises an action. Only pass this when the
   * whole card really is a link or button.
   */
  interactive?: boolean
}

export function Card({ interactive = false, className, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={cn(
        // Doc 07 §13: borderless, separated by shadow. On near-black a shadow
        // reads as nothing, so dark swaps it for the hairline it needs instead.
        'rounded-card bg-surface shadow-card p-16 md:p-24',
        'dark:border-border dark:border',
        interactive &&
          cn(
            'cursor-pointer transition-[transform,box-shadow] duration-card ease-out',
            'hover:shadow-overlay hover:-translate-y-0.5',
            focusRing,
          ),
        className,
      )}
    />
  )
}
