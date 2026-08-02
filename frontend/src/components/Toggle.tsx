import { useId } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface ToggleProps {
  checked: boolean
  onChange: (next: boolean) => void
  /** Visible text beside the switch. Omit only when `aria-label` is supplied. */
  label?: string
  'aria-label'?: string
  disabled?: boolean
  className?: string
}

/**
 * The boolean switch for settings — a thing that takes effect the moment it
 * moves. Filters and multi-select stay checkboxes: a switch that only narrows a
 * list overstates what it did.
 *
 * A real `<button role="switch">` rather than a restyled checkbox, so screen
 * readers announce on/off instead of checked, and the 44px hit area is the
 * button while the 44×24 track is only what you see inside it.
 */
export function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
  className,
  ...props
}: ToggleProps) {
  const labelId = useId()

  return (
    <span className={cn('inline-flex items-center gap-12', className)}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={label ? labelId : undefined}
        aria-label={props['aria-label']}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'flex size-[44px] shrink-0 cursor-pointer items-center justify-center',
          'disabled:cursor-not-allowed disabled:opacity-40',
          focusRing,
        )}
      >
        <span
          aria-hidden
          className={cn(
            'rounded-pill relative block h-[24px] w-[44px]',
            'transition-colors duration-micro ease-out',
            checked ? 'bg-primary-fill' : 'bg-border',
          )}
        >
          <span
            className={cn(
              'rounded-pill absolute top-[2px] left-[2px] size-[20px] bg-white',
              'shadow-card transition-transform duration-micro ease-out',
              checked && 'translate-x-[20px]',
            )}
          />
        </span>
      </button>
      {label && (
        <span id={labelId} className="text-body">
          {label}
        </span>
      )}
    </span>
  )
}
