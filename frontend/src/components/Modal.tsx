import { X } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'
import { Button } from './Button'
import { useDialog } from './useDialog'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  /** Doc 04: 480px for confirmations, 640px for forms. No other widths. */
  size?: 'confirm' | 'form'
  children: ReactNode
  footer?: ReactNode
}

export function Modal({ open, onClose, title, size = 'form', children, footer }: ModalProps) {
  const ref = useDialog(open, onClose)

  return (
    <dialog
      ref={ref}
      aria-labelledby="modal-title"
      className={cn(
        'rounded-card bg-elevated text-ink shadow-overlay m-auto w-[calc(100%-32px)] p-32',
        'dark:border-border dark:border',
        size === 'confirm' ? 'max-w-[480px]' : 'max-w-[640px]',
        // Doc 07 §14: an ink-tinted, lightly blurred scrim rather than flat black.
        'backdrop:bg-ink/60 backdrop:backdrop-blur-[4px]',
        'open:animate-[scale-in_var(--duration-modal)_var(--ease-macro)]',
      )}
    >
      <div className="flex items-start justify-between gap-16">
        <h2 id="modal-title" className="text-h3 font-semibold">
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
      <div className="text-body mt-16">{children}</div>
      {footer && <div className="mt-32 flex justify-end gap-8">{footer}</div>}
    </dialog>
  )
}

export interface ConfirmModalProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmLabel?: string
  destructive?: boolean
}

/**
 * Exists so the "focus defaults to the non-destructive action" rule from Doc 04
 * is encoded once, rather than being remembered at every delete confirmation.
 */
export function ConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  destructive = false,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="confirm"
      footer={
        <>
          {/* autoFocus on Cancel: never open a destructive dialog with the
              destructive button pre-focused (Doc 04, Modals). */}
          <Button autoFocus onClick={onClose}>
            Cancel
          </Button>
          <Button variant={destructive ? 'danger' : 'primary'} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {message}
    </Modal>
  )
}
