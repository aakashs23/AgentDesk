import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Doc 07 §28: centred, one minimal outlined glyph, a title and a helpful
 * subtitle, and one primary CTA that starts the thing that's missing. The glyph
 * runs at 48px in `muted` rather than §28's #9CA3AF, which lands at 2.5:1.
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
      <Icon aria-hidden size={48} strokeWidth={1.5} className="text-muted" />
      <h2 className="text-h3 mt-24 font-semibold">{title}</h2>
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
      <h2 className="text-h3 mt-24 font-semibold">{title}</h2>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-body text-primary mt-16 cursor-pointer font-medium underline underline-offset-4"
        >
          Retry
        </button>
      )}
    </div>
  )
}
