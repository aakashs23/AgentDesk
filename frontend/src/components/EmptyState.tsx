import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Doc 04's empty-state treatment: a small single-colour line illustration in the
 * ink colour (never the gradient) supporting a typographic headline — the
 * illustration accompanies the headline, it does not replace it.
 */
export function EmptyState({
  icon: Icon,
  title,
  message,
  action,
}: {
  icon: LucideIcon
  title: string
  message?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center py-64 text-center">
      <Icon aria-hidden size={24} strokeWidth={1.5} className="text-ink" />
      <h2 className="font-display text-h2 mt-24 font-semibold">{title}</h2>
      {message && <p className="text-body text-muted mt-8 max-w-[420px]">{message}</p>}
      {action && <div className="mt-24">{action}</div>}
    </div>
  )
}

/** Doc 03 §6 pairs every empty state with an error state carrying a Retry. */
export function ErrorState({
  icon: Icon,
  title,
  onRetry,
}: {
  icon: LucideIcon
  title: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center py-64 text-center">
      <Icon aria-hidden size={24} strokeWidth={1.5} className="text-critical" />
      <h2 className="font-display text-h3 mt-24 font-semibold">{title}</h2>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-body text-brand-start mt-16 cursor-pointer font-medium underline underline-offset-4"
        >
          Retry
        </button>
      )}
    </div>
  )
}
