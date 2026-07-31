import { cn, statusLabel } from '../lib/ui'

/**
 * Doc 04: status pills are flat fills (never the gradient — that means AI) and
 * always carry a text label, because colour alone is not an accessible signal.
 *
 * The palette has no per-status colours, only the priority/semantic set, so
 * statuses map onto the semantic meanings that already exist rather than
 * inventing new hexes.
 */
const TONES: Record<string, string> = {
  new: 'bg-medium text-white',
  open: 'bg-medium text-white',
  in_progress: 'bg-high text-white',
  on_hold: 'border border-border text-muted',
  resolved: 'bg-success text-white',
  closed: 'border border-border text-muted',
  reopened: 'bg-high text-white',
}

export function StatusPill({ status, className }: { status: string; className?: string }) {
  return (
    <span
      className={cn(
        'rounded-pill text-caption inline-flex items-center px-12 py-4 font-medium tracking-wide uppercase',
        TONES[status] ?? 'border-border text-muted border',
        className,
      )}
    >
      {statusLabel(status)}
    </span>
  )
}

/** Priority colours are admin-configurable (`priorities.color_hex`), so unlike
 *  status this one takes its fill from the database rather than a fixed map. */
export function PriorityPill({
  name,
  colorHex,
  className,
}: {
  name: string
  colorHex: string
  className?: string
}) {
  return (
    <span
      style={{ backgroundColor: colorHex }}
      className={cn(
        'rounded-pill text-caption inline-flex items-center px-12 py-4 font-medium tracking-wide text-white uppercase',
        className,
      )}
    >
      {name}
    </span>
  )
}
