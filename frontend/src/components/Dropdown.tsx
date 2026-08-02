import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface DropdownProps {
  /** Rendered inside a button; the wrapper owns the click handling. */
  trigger: ReactNode
  label: string
  align?: 'start' | 'end'
  children: (close: () => void) => ReactNode
}

/** Doc 04: opens on click (never hover — hover menus break on touch). */
export function Dropdown({ trigger, label, align = 'start', children }: DropdownProps) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
        className={cn('rounded-control cursor-pointer', focusRing)}
      >
        {trigger}
      </button>
      {open && (
        <div
          role="menu"
          className={cn(
            'rounded-card border-border bg-elevated shadow-overlay absolute z-50 mt-8 min-w-[224px] border p-4',
            'animate-[fade-in_var(--duration-dropdown)_ease-out]',
            align === 'end' ? 'right-0' : 'left-0',
          )}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  )
}

export function DropdownItem({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      role="menuitem"
      {...props}
      className={cn(
        'rounded-control text-body text-ink flex w-full cursor-pointer items-center gap-8 px-12 py-8 text-left',
        'hover:bg-sunken transition-colors duration-micro',
        focusRing,
        className,
      )}
    />
  )
}
