import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ListChecks, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { SkeletonRows } from '../../components/Skeleton'
import { ApiError, api } from '../../lib/api'
import { usePriorities } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { SavedView, TicketStatus } from '../../lib/types'
import { STATUS_LABELS, cn, focusRing, statusLabel } from '../../lib/ui'

/**
 * Saved Views (Doc 03 §18) — a named filter set, stored per user. The backend
 * keeps `filters` as opaque JSON, so the shape is decided here: the same keys
 * the Queue narrows on, which is what lets a view be applied by handing the
 * JSON straight to the queue's `?filters=`.
 */
interface ViewFilters {
  status?: string
  priority_id?: string
}

export function SavedViews() {
  const queryClient = useQueryClient()
  const priorities = usePriorities()
  const [name, setName] = useState('')
  const [filters, setFilters] = useState<ViewFilters>({})

  const views = useQuery({
    queryKey: ['saved-views'],
    queryFn: () => api<SavedView[]>('/saved-views'),
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['saved-views'] })

  const create = useMutation({
    mutationFn: () =>
      api<SavedView>('/saved-views', {
        method: 'POST',
        // Empty selects would otherwise be stored as "" and match nothing.
        json: {
          name: name.trim(),
          filters: Object.fromEntries(Object.entries(filters).filter(([, v]) => v)),
        },
      }),
    onSuccess: async () => {
      setName('')
      setFilters({})
      await refresh()
      toast('View saved', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  const remove = useMutation({
    mutationFn: (id: string) => api(`/saved-views/${id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await refresh()
      toast('View deleted', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="font-display text-h1 font-semibold">Saved Views</h1>
      <p className="text-body text-muted mt-8">
        Name a filter set once and reopen it from here — views are private to you.
      </p>

      <Card className="mt-24">
        <h2 className="text-h3 font-display font-semibold">New view</h2>
        <div className="mt-16 grid gap-16 md:grid-cols-3">
          <Input
            label="Name"
            value={name}
            placeholder="My critical tickets"
            onChange={(e) => setName(e.target.value)}
          />
          <label className="flex flex-col gap-8">
            <span className="text-body-sm text-muted font-medium">Status</span>
            <select
              value={filters.status ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
              className={cn(
                'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
                focusRing,
              )}
            >
              <option value="">Any status</option>
              {Object.keys(STATUS_LABELS).map((status) => (
                <option key={status} value={status}>
                  {statusLabel(status)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-8">
            <span className="text-body-sm text-muted font-medium">Priority</span>
            <select
              value={filters.priority_id ?? ''}
              onChange={(e) => setFilters((f) => ({ ...f, priority_id: e.target.value }))}
              className={cn(
                'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
                focusRing,
              )}
            >
              <option value="">Any priority</option>
              {(priorities.data ?? []).map((priority) => (
                <option key={priority.id} value={priority.id}>
                  {priority.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-16 flex justify-end">
          <Button
            variant="primary"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Save view
          </Button>
        </div>
      </Card>

      <div className="mt-32">
        {views.isPending && <SkeletonRows rows={3} />}

        {views.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load your views"
            onRetry={() => void views.refetch()}
          />
        )}

        {views.isSuccess && views.data.length === 0 && (
          <EmptyState
            icon={ListChecks}
            title="No saved views yet"
            message="Save the filter combination you keep retyping and it will live here."
          />
        )}

        <ul className="flex flex-col gap-8">
          {(views.data ?? []).map((view) => (
            <li
              key={view.id}
              className="rounded-card border-border flex items-center gap-12 border p-16"
            >
              <div className="min-w-0 flex-1">
                <Link
                  to={`/agent/queue?tab=team&filters=${encodeURIComponent(JSON.stringify(view.filters))}`}
                  className={cn('text-body text-ink font-medium hover:underline', focusRing)}
                >
                  {view.name}
                </Link>
                <p className="text-body-sm text-muted mt-4">{describe(view.filters)}</p>
              </div>
              <button
                type="button"
                onClick={() => remove.mutate(view.id)}
                aria-label={`Delete ${view.name}`}
                className={cn('text-muted hover:text-critical cursor-pointer', focusRing)}
              >
                <Trash2 size={16} strokeWidth={1.5} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function describe(filters: Record<string, unknown>): string {
  const parts = Object.entries(filters).map(([key, value]) =>
    key === 'status' ? statusLabel(String(value) as TicketStatus) : `${key}: ${String(value)}`,
  )
  return parts.length ? parts.join(' · ') : 'No filters — every ticket you can see'
}
