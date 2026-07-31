import { slaTimeline, type SlaState } from '../lib/agent'
import type { Ticket } from '../lib/types'
import { cn, relativeTime } from '../lib/ui'

// Doc 04 defines exactly two SLA colours; `ok`/`met` stay on the neutral border
// so the amber and red mean something when they do appear.
const FILLS: Record<SlaState, string> = {
  ok: 'bg-medium',
  risk: 'bg-sla-risk',
  breach: 'bg-sla-breach',
  met: 'bg-success',
}

const CAPTIONS: Record<SlaState, string> = {
  ok: 'Within SLA',
  risk: 'Approaching the resolution target',
  breach: 'Resolution target breached',
  met: 'Resolved within target',
}

/**
 * Doc 04's SLA timeline scrubber: Created → Response Due → Resolution Due →
 * Now on one horizontal bar. Flat semantic fills, never the gradient — the SLA
 * clock is the system's, not the model's.
 */
export function SlaScrubber({ ticket }: { ticket: Ticket }) {
  const { marks, progress, state } = slaTimeline(ticket)

  if (marks.length === 1) {
    return <p className="text-body-sm text-muted">No SLA policy matched this ticket yet.</p>
  }

  return (
    <div>
      <div className="flex items-baseline justify-between gap-16">
        <p className="text-caption text-muted tracking-wide uppercase">SLA</p>
        {/* Never colour alone (Doc 04 Accessibility) — the caption says it too. */}
        <p
          className={cn(
            'text-body-sm font-medium',
            state === 'breach' && 'text-sla-breach',
            state === 'risk' && 'text-sla-risk',
            state === 'met' && 'text-success',
            state === 'ok' && 'text-muted',
          )}
        >
          {CAPTIONS[state]}
        </p>
      </div>

      <div
        role="img"
        aria-label={`${CAPTIONS[state]}. ${marks
          .map((m) => `${m.label} ${relativeTime(m.iso)}`)
          .join(', ')}.`}
        className="bg-surface rounded-pill relative mt-12 h-[8px] w-full"
      >
        <div
          className={cn('rounded-pill absolute inset-y-0 left-0', FILLS[state])}
          style={{ width: `${progress * 100}%` }}
        />
        {marks.slice(1).map((mark) => (
          <span
            key={mark.label}
            aria-hidden
            className="bg-ink absolute top-1/2 h-[14px] w-[2px] -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${mark.at * 100}%` }}
          />
        ))}
      </div>

      <dl className="mt-12 flex flex-wrap gap-x-24 gap-y-8">
        {marks.map((mark) => (
          <div key={mark.label}>
            <dt className="text-caption text-muted tracking-wide uppercase">{mark.label}</dt>
            <dd className="text-body-sm text-ink">
              <time dateTime={mark.iso}>{relativeTime(mark.iso)}</time>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
