import type { SelectHTMLAttributes } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  /** Renders the field inside its own label; omit for a bare inline control. */
  label?: string
}

/**
 * The one select style the app uses — Doc 04's control height, border and focus
 * ring, defined once so no screen can drift. The admin configuration screens are
 * mostly dropdowns, which is what made this worth extracting.
 */
export function Select({ label, className, ...props }: SelectProps) {
  const select = (
    <select
      {...props}
      className={cn(
        'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
        focusRing,
        className,
      )}
    />
  )
  if (!label) return select
  return (
    <label className="flex flex-col gap-8">
      <span className="text-body-sm text-muted font-medium">{label}</span>
      {select}
    </label>
  )
}
