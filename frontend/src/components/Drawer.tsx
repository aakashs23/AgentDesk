import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'
import { useDialog } from './useDialog'

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  /**
   * Rendered above the title, pinned so it is the first thing visible on open.
   * The AI Draft Response drawer uses this for its provenance header — the
   * "this is AI-generated" signal must never be scrolled past.
   */
  header?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function Drawer({ open, onClose, title, header, children, footer }: DrawerProps) {
  const ref = useDialog(open, onClose)

  return (
    <dialog
      ref={ref}
      aria-labelledby="drawer-title"
      className={cn(
        // `open:flex` (not a bare `flex`): an unconditional `display` utility
        // beats the browser's own `dialog:not([open]) { display: none }` rule
        // (author CSS always wins over the UA stylesheet), which left this
        // dialog laid out and pointer-intercepting in normal page flow even
        // while "closed". Scoping to `open:` restores native hidden-by-default.
        'border-border bg-elevated text-ink shadow-overlay open:flex open:flex-col border backdrop:bg-ink/60 backdrop:backdrop-blur-[4px]',
        // Mobile: a bottom sheet at ~85% height. Desktop/tablet: a right-hand
        // panel at ~40% viewport width, per Doc 04's Responsive rules.
        'mt-auto mb-0 ml-auto h-[85dvh] max-h-[85dvh] w-full max-w-full rounded-t-card',
        'md:my-0 md:h-dvh md:max-h-dvh md:w-2/5 md:rounded-none',
        'open:animate-[slide-in-bottom_var(--duration-drawer)_var(--ease-drawer)]',
        'md:open:animate-[slide-in-right_var(--duration-drawer)_var(--ease-drawer)]',
      )}
    >
      {header}
      <div className="border-border flex items-start justify-between gap-16 border-b p-24">
        <h2 id="drawer-title" className="text-h3 font-semibold">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className={cn('text-muted hover:text-ink cursor-pointer', focusRing)}
        >
          <X size={20} strokeWidth={1.5} />
        </button>
      </div>
      <div className="text-body flex-1 overflow-y-auto p-24">{children}</div>
      {footer && <div className="border-border flex justify-end gap-8 border-t p-24">{footer}</div>}
    </dialog>
  )
}
