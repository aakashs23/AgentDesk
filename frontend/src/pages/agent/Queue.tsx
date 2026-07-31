import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Inbox, MessageSquare } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { Avatar } from '../../components/Avatar'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import { PriorityPill, StatusPill } from '../../components/StatusPill'
import { Tabs } from '../../components/Tabs'

import { api } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { byId, usePriorities, useStaffDirectory } from '../../lib/queries'
import type { Ticket } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

// Doc 03 §1: the Agent Console's home screen. Three tabs, one endpoint — the
// query string is the only difference between them.
const TABS = [
  { id: 'mine', label: 'My Tickets' },
  { id: 'team', label: 'Team Queue' },
  { id: 'unassigned', label: 'Unassigned' },
]

function parseFilters(raw: string | null): Record<string, string> {
  if (!raw) return {}
  try {
    const parsed: unknown = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, string>) : {}
  } catch {
    return {}
  }
}

function queryFor(tab: string, userId: string): string {
  if (tab === 'mine') return `?assignee_id=${userId}&limit=100`
  if (tab === 'unassigned') return '?unassigned=true&limit=100'
  return '?limit=100'
}

export function Queue() {
  const user = useUser()
  // The tab lives in the URL so a saved view can deep-link into one, and a
  // reload after opening a ticket comes back to the same tab.
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'mine'
  const filters = params.get('filters')

  const priorities = usePriorities()
  const staff = useStaffDirectory()
  const priorityById = byId(priorities.data)
  const staffById = byId(staff.data)

  const tickets = useQuery({
    queryKey: ['tickets', 'queue', tab, filters, user?.id],
    enabled: Boolean(user),
    queryFn: () => api<Ticket[]>(`/tickets${queryFor(tab, user!.id)}`),
  })

  // A Saved View is a stored filter set (Doc 03 §18); applying one narrows the
  // tab's result client-side rather than adding a second server round-trip.
  // The JSON arrives from the URL, so a hand-edited link must not white-screen
  // the queue — an unreadable filter is simply no filter.
  const applied: Record<string, string> = parseFilters(filters)
  const visible = (tickets.data ?? []).filter((ticket) =>
    Object.entries(applied).every(
      ([key, value]) => !value || String(ticket[key as keyof Ticket] ?? '') === value,
    ),
  )

  return (
    <div className="mx-auto max-w-[1440px]">
      <div className="flex flex-wrap items-center justify-between gap-16">
        <h1 className="font-display text-h1 font-semibold">Ticket Queue</h1>
        {Object.keys(applied).length > 0 && (
          <button
            type="button"
            onClick={() => setParams({ tab })}
            className={cn('text-body-sm text-brand-start cursor-pointer font-medium', focusRing)}
          >
            Clear saved view
          </button>
        )}
      </div>

      <div className="mt-24">
        <Tabs tabs={TABS} active={tab} onChange={(id) => setParams({ tab: id })} />
      </div>

      <div className="mt-24">
        {tickets.isPending && <SkeletonRows rows={6} />}

        {tickets.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load the queue"
            onRetry={() => void tickets.refetch()}
          />
        )}

        {tickets.isSuccess && visible.length === 0 && (
          <EmptyState
            icon={Inbox}
            title={tab === 'mine' ? 'Nothing assigned to you' : 'This queue is clear'}
            message={
              tab === 'unassigned'
                ? 'Every ticket in your team has an owner.'
                : 'New tickets appear here as the AI pipeline routes them.'
            }
          />
        )}

        <ul className="flex flex-col gap-8">
          {visible.map((ticket) => (
            <QueueRow
              key={ticket.id}
              ticket={ticket}
              priority={ticket.priority_id ? priorityById.get(ticket.priority_id) : undefined}
              assignee={ticket.assignee_id ? staffById.get(ticket.assignee_id) : undefined}
            />
          ))}
        </ul>
      </div>
    </div>
  )
}

/** Doc 04's inbox-style row: avatar chip, title, solid priority pill, counts,
 *  relative timestamp. Dense on purpose — this is the screen agents live in. */
function QueueRow({
  ticket,
  priority,
  assignee,
}: {
  ticket: Ticket
  priority?: { name: string; color_hex: string }
  assignee?: { full_name: string; id: string }
}) {
  return (
    <li>
      <Card interactive className="p-0">
        <Link
          to={`/agent/tickets/${ticket.id}`}
          className={cn('flex items-center gap-12 p-12 md:gap-16', focusRing)}
        >
          {assignee ? (
            <Avatar name={assignee.full_name} seed={assignee.id} size="md" />
          ) : (
            <span
              aria-label="Unassigned"
              title="Unassigned"
              className="border-border text-muted text-caption rounded-pill flex size-[32px] shrink-0 items-center justify-center border border-dashed"
            >
              ?
            </span>
          )}

          <div className="min-w-0 flex-1">
            <p className="text-body text-ink truncate font-medium">{ticket.subject}</p>
            <p className="text-body-sm text-muted mt-4 flex flex-wrap items-center gap-12">
              <span className="text-data font-mono">{ticket.ref}</span>
              <span className="inline-flex items-center gap-4">
                <MessageSquare aria-hidden size={16} strokeWidth={1.5} />
                {ticket.channel}
              </span>
              <time dateTime={ticket.created_at}>{relativeTime(ticket.created_at)}</time>
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-8">
            {priority && <PriorityPill name={priority.name} colorHex={priority.color_hex} />}
            <StatusPill status={ticket.status} />
          </div>
        </Link>
      </Card>
    </li>
  )
}
