import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ScrollText } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { api } from '../../lib/api'
import { describeChange, humanise } from '../../lib/admin'
import { useAllUsers } from '../../lib/queries'
import type { AuditLogEntry } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

const PAGE_SIZE = 50

/**
 * Audit Log viewer (Doc 03 §1). Read-only by construction — `audit_logs` is an
 * immutable trail, so there is no edit affordance anywhere on this screen.
 *
 * Filtering happens server-side rather than in the browser: the table grows
 * without bound, and a client-side filter over one page of it would quietly
 * answer the wrong question.
 */
export function AuditLog() {
  const [entityType, setEntityType] = useState('')
  const [actorId, setActorId] = useState('')
  const [action, setAction] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [page, setPage] = useState(0)

  const users = useAllUsers()
  const entityTypes = useQuery({
    queryKey: ['audit-entity-types'],
    queryFn: () => api<string[]>('/admin/audit-logs/entity-types'),
  })

  const filters = { entityType, actorId, action, start, end }
  const entries = useQuery({
    queryKey: ['audit-logs', filters, page],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      })
      if (entityType) params.set('entity_type', entityType)
      if (actorId) params.set('actor_id', actorId)
      if (action) params.set('action', action.trim())
      if (start) params.set('start', `${start}T00:00:00Z`)
      if (end) params.set('end', `${end}T23:59:59Z`)
      return api<AuditLogEntry[]>(`/admin/audit-logs?${params}`)
    },
  })

  // Any filter change invalidates the page number — page 3 of a different query
  // is a different, meaningless slice.
  const filter =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value)
      setPage(0)
    }

  const actorName = (id: string | null) =>
    id ? (users.data?.find((u) => u.id === id)?.full_name ?? 'Removed user') : 'System'

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Audit Log</h1>
      <p className="text-body text-muted mt-8">
        Every ticket and configuration change, with who made it. Append-only — nothing here can be
        edited or removed.
      </p>

      <div className="mt-24 flex flex-wrap items-end gap-16">
        <Select
          label="Entity"
          value={entityType}
          onChange={(e) => filter(setEntityType)(e.target.value)}
        >
          <option value="">All entities</option>
          {(entityTypes.data ?? []).map((type) => (
            <option key={type} value={type}>
              {humanise(type)}
            </option>
          ))}
        </Select>
        <Select label="Actor" value={actorId} onChange={(e) => filter(setActorId)(e.target.value)}>
          <option value="">Anyone</option>
          {(users.data ?? []).map((user) => (
            <option key={user.id} value={user.id}>
              {user.full_name}
            </option>
          ))}
        </Select>
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Action</span>
          <input
            type="search"
            value={action}
            onChange={(e) => filter(setAction)(e.target.value)}
            placeholder="created, updated…"
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] border px-12',
              'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
              focusRing,
            )}
          />
        </label>
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">From</span>
          <input
            type="date"
            value={start}
            max={end || undefined}
            onChange={(e) => filter(setStart)(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] border px-12',
              focusRing,
            )}
          />
        </label>
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">To</span>
          <input
            type="date"
            value={end}
            min={start || undefined}
            onChange={(e) => filter(setEnd)(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] border px-12',
              focusRing,
            )}
          />
        </label>
      </div>

      <div className="mt-24">
        {entries.isPending && <SkeletonRows rows={8} />}
        {entries.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load the audit log"
            onRetry={() => void entries.refetch()}
          />
        )}
        {entries.isSuccess && entries.data.length === 0 && (
          <EmptyState
            icon={ScrollText}
            title="Nothing matches those filters"
            message={page > 0 ? 'You may have paged past the end.' : undefined}
          />
        )}

        <ul className="flex flex-col gap-8">
          {(entries.data ?? []).map((entry) => (
            <li key={entry.id}>
              <Card className="flex flex-wrap items-start gap-16 p-16">
                <Avatar name={actorName(entry.actor_id)} size="sm" />
                <div className="min-w-[240px] flex-1">
                  <p className="text-body text-ink">
                    <span className="font-medium">{actorName(entry.actor_id)}</span> {entry.action}{' '}
                    {humanise(entry.entity_type).toLowerCase()}
                  </p>
                  <p className="text-body-sm text-muted mt-4 break-words">
                    {describeChange(entry)}
                  </p>
                </div>
                {entry.entity_type === 'ticket' && (
                  <Link
                    to={`/agent/tickets/${entry.entity_id}`}
                    className={cn('text-body-sm text-brand-start font-medium', focusRing)}
                  >
                    View ticket
                  </Link>
                )}
                <time
                  dateTime={entry.created_at}
                  title={new Date(entry.created_at).toLocaleString()}
                  className="text-body-sm text-muted min-w-[120px] text-right"
                >
                  {relativeTime(entry.created_at)}
                </time>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      {/* No total count comes back, so paging is "is this page full?" rather
          than a page count — cheaper than a second COUNT query per view. */}
      <div className="mt-24 flex items-center justify-between gap-16">
        <Button disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
          Previous
        </Button>
        <span className="text-body-sm text-muted">Page {page + 1}</span>
        <Button
          disabled={(entries.data?.length ?? 0) < PAGE_SIZE}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
