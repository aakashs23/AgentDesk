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
        // Hairline border rather than shadow: on near-black surfaces a shadow
        // alone leaves cards illegible (Doc 04, "Definition on dark surfaces").
        'rounded-card border-border bg-surface border p-16 md:p-24',
        interactive &&
          cn(
            'cursor-pointer transition-[transform,box-shadow] duration-card ease-out',
            'hover:shadow-elevated hover:-translate-y-0.5',
            focusRing,
          ),
        className,
      )}
    />
  )
}
