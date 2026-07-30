import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'

import { dismissToast, useToasts, type ToastTone } from '../lib/toast'
import { cn, focusRing } from '../lib/ui'

const ICONS: Record<ToastTone, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  error: AlertCircle,
}

const TONES: Record<ToastTone, string> = {
  info: 'text-muted',
  success: 'text-success',
  error: 'text-critical',
}

/** Mounted once at the app root. */
export function Toaster() {
  const toasts = useToasts()

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-16 bottom-16 z-100 flex flex-col items-center gap-8 md:inset-x-auto md:right-32 md:bottom-32 md:items-end"
    >
      {toasts.map((t) => {
        const Icon = ICONS[t.tone]
        return (
          <div
            key={t.id}
            role="status"
            className={cn(
              'rounded-card border-border bg-elevated text-body text-ink shadow-elevated',
              'pointer-events-auto flex w-full max-w-[420px] items-start gap-12 border p-16',
              'animate-[rise-in_var(--duration-modal)_ease-out]',
            )}
          >
            <Icon aria-hidden size={16} strokeWidth={1.5} className={cn('mt-4', TONES[t.tone])} />
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              onClick={() => dismissToast(t.id)}
              aria-label="Dismiss"
              className={cn('text-muted hover:text-ink cursor-pointer', focusRing)}
            >
              <X size={16} strokeWidth={1.5} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
