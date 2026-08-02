import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Inbox, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import { PriorityPill, StatusPill } from '../../components/StatusPill'
import { Tabs } from '../../components/Tabs'
import { api } from '../../lib/api'
import { byId, usePriorities } from '../../lib/queries'
import type { Ticket, TicketStatus } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

// Doc 03 §1: "filterable by status". Grouped rather than one tab per status —
// seven tabs would not fit a phone, and a requester thinks in open vs. done.
interface StatusFilter {
  id: string
  label: string
  /** null means "no filter". */
  statuses: TicketStatus[] | null
}

const FILTERS: StatusFilter[] = [
  { id: 'all', label: 'All', statuses: null },
  {
    id: 'active',
    label: 'Active',
    statuses: ['new', 'open', 'in_progress', 'on_hold', 'reopened'],
  },
  { id: 'resolved', label: 'Resolved', statuses: ['resolved'] },
  { id: 'closed', label: 'Closed', statuses: ['closed'] },
]

export function MyTickets() {
  const [filter, setFilter] = useState<string>('all')
  const navigate = useNavigate()
  const priorities = usePriorities()
  const priorityById = byId(priorities.data)

  // Fetched unfiltered and narrowed client-side: the list is one requester's own
  // tickets, so it is small, and switching tabs then costs no request.
  const tickets = useQuery({
    queryKey: ['tickets', 'mine'],
    queryFn: () => api<Ticket[]>('/tickets?limit=100'),
  })

  const active = FILTERS.find((f) => f.id === filter) ?? FILTERS[0]
  const visible = (tickets.data ?? []).filter(
    (t) => active.statuses === null || active.statuses.includes(t.status),
  )

  return (
    <div className="mx-auto max-w-[960px]">
      <div className="flex flex-wrap items-center justify-between gap-16">
        <h1 className="text-h1 font-semibold">My Tickets</h1>
        <Button variant="primary" onClick={() => navigate('/portal/tickets/new')}>
          <Plus aria-hidden size={16} strokeWidth={1.5} />
          New Ticket
        </Button>
      </div>

      <div className="mt-24">
        <Tabs
          tabs={FILTERS.map((f) => ({ id: f.id, label: f.label }))}
          active={filter}
          onChange={setFilter}
        />
      </div>

      <div className="mt-24">
        {tickets.isPending && <SkeletonRows rows={5} />}

        {tickets.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load your tickets"
            onRetry={() => void tickets.refetch()}
          />
        )}

        {tickets.isSuccess && visible.length === 0 && (
          <EmptyState
            icon={Inbox}
            title={filter === 'all' ? 'You have no tickets yet' : 'Nothing here'}
            message={
              filter === 'all'
                ? 'When you raise a request, it will show up here so you can follow its progress.'
                : 'No tickets match this filter.'
            }
            action={
              filter === 'all' ? (
                <Button variant="primary" onClick={() => navigate('/portal/tickets/new')}>
                  Create your first ticket
                </Button>
              ) : undefined
            }
          />
        )}

        {/* One surface, divided rows — the same list shape the agent queue uses,
            just roomier, because a requester reads a handful of these, not fifty. */}
        {visible.length > 0 && (
          <Card className="overflow-hidden p-0">
            <ul>
              {visible.map((ticket) => {
                const priority = ticket.priority_id
                  ? priorityById.get(ticket.priority_id)
                  : undefined
                return (
                  <li key={ticket.id} className="border-divider not-last:border-b">
                    <Link
                      to={`/portal/tickets/${ticket.id}`}
                      className={cn(
                        'hover:bg-sunken transition-colors duration-micro flex flex-col gap-8 p-16 md:p-24',
                        focusRing,
                      )}
                    >
                      <div className="flex items-start justify-between gap-12">
                        <span className="text-body text-ink font-medium">{ticket.subject}</span>
                        <StatusPill status={ticket.status} className="shrink-0" />
                      </div>
                      <div className="text-body-sm text-muted flex flex-wrap items-center gap-12">
                        <span className="text-data font-mono">{ticket.ref}</span>
                        {priority && (
                          <PriorityPill name={priority.name} colorHex={priority.color_hex} />
                        )}
                        <time dateTime={ticket.created_at}>{relativeTime(ticket.created_at)}</time>
                      </div>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
