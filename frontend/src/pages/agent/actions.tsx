import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { ConfirmModal, Modal } from '../../components/Modal'
import { ApiError, api } from '../../lib/api'
import { nextStatuses } from '../../lib/agent'
import { useUser } from '../../lib/auth'
import { useDebounced } from '../../lib/hooks'
import { useStaffDirectory } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { Ticket } from '../../lib/types'
import { cn, focusRing, formatTicketId, statusLabel } from '../../lib/ui'

/**
 * Every ticket action is the same shape: POST/PATCH, refresh the ticket and
 * whatever it feeds, toast the outcome. Written once so an action can't quietly
 * skip the cache invalidation and leave the screen showing a stale status.
 */
function useTicketAction<TVars>(
  ticketId: string,
  request: (vars: TVars) => Promise<unknown>,
  success: string,
  onDone?: () => void,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] }),
        queryClient.invalidateQueries({ queryKey: ['tickets'] }),
        queryClient.invalidateQueries({ queryKey: ['status-history', ticketId] }),
      ])
      toast(success, 'success')
      onDone?.()
    },
    onError: (error) =>
      toast(error instanceof ApiError ? error.message : 'That action failed', 'error'),
  })
}

// --- Status control (App Flow §10) ------------------------------------------

/**
 * Only the legal next moves are offered. An illegal transition is refused by
 * the workflow engine anyway; not rendering the button is how the agent learns
 * the lifecycle instead of discovering it through error toasts.
 */
export function StatusActions({ ticket }: { ticket: Ticket }) {
  const move = useTicketAction(
    ticket.id,
    (status: string) => api(`/tickets/${ticket.id}/status`, { method: 'PATCH', json: { status } }),
    'Status updated',
  )
  const options = nextStatuses(ticket.status)

  if (options.length === 0) return null

  return (
    <div className="flex flex-wrap gap-8">
      {options.map((status) => (
        <Button
          key={status}
          size="sm"
          variant={status === 'resolved' ? 'primary' : 'secondary'}
          disabled={move.isPending}
          onClick={() => move.mutate(status)}
        >
          Mark {statusLabel(status)}
        </Button>
      ))}
    </div>
  )
}

// --- Assign / reassign ------------------------------------------------------

export function AssignModal({
  ticket,
  open,
  onClose,
}: {
  ticket: Ticket
  open: boolean
  onClose: () => void
}) {
  const user = useUser()
  const staff = useStaffDirectory(open)
  const [selected, setSelected] = useState<string | null>(ticket.assignee_id)

  const assign = useTicketAction(
    ticket.id,
    (assigneeId: string) =>
      api(`/tickets/${ticket.id}/assign`, {
        method: 'POST',
        json: { assignee_id: assigneeId },
      }),
    'Ticket assigned',
    onClose,
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={ticket.assignee_id ? 'Reassign ticket' : 'Assign ticket'}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!selected || assign.isPending}
            onClick={() => selected && assign.mutate(selected)}
          >
            Assign
          </Button>
        </>
      }
    >
      {user && (
        <Button
          className="mb-16 w-full"
          disabled={assign.isPending || ticket.assignee_id === user.id}
          onClick={() => assign.mutate(user.id)}
        >
          Assign to me
        </Button>
      )}

      <ul className="max-h-[320px] overflow-y-auto">
        {(staff.data ?? []).map((person) => (
          <li key={person.id}>
            <label
              className={cn(
                'rounded-control flex cursor-pointer items-center gap-12 px-12 py-8',
                'hover:bg-surface transition-colors duration-micro',
                selected === person.id && 'bg-surface',
              )}
            >
              <input
                type="radio"
                name="assignee"
                value={person.id}
                checked={selected === person.id}
                onChange={() => setSelected(person.id)}
                className={cn('accent-brand-start', focusRing)}
              />
              <Avatar name={person.full_name} seed={person.id} size="sm" />
              <span className="min-w-0">
                <span className="text-body text-ink block truncate">{person.full_name}</span>
                <span className="text-body-sm text-muted block truncate">{person.email}</span>
              </span>
            </label>
          </li>
        ))}
      </ul>

      {staff.isSuccess && staff.data.length === 0 && (
        <p className="text-body-sm text-muted">No other staff in your team yet.</p>
      )}
    </Modal>
  )
}

// --- Escalate ---------------------------------------------------------------

export function EscalateModal({
  ticket,
  open,
  onClose,
}: {
  ticket: Ticket
  open: boolean
  onClose: () => void
}) {
  const escalate = useTicketAction(
    ticket.id,
    () => api(`/tickets/${ticket.id}/escalate`, { method: 'POST', json: {} }),
    'Escalated to a team lead',
    onClose,
  )

  return (
    <ConfirmModal
      open={open}
      onClose={onClose}
      onConfirm={() => escalate.mutate(undefined)}
      title="Escalate this ticket?"
      message="The ticket is reassigned to a team lead and they are notified. Use this when it needs authority or expertise you don't have."
      confirmLabel="Escalate"
    />
  )
}

// --- Merge ------------------------------------------------------------------

interface TicketHit {
  id: string
  display_id: number | null
  subject: string
}

/** Doc 03 §20: pick the ticket this one merges *into*, then confirm. */
export function MergeModal({
  ticket,
  open,
  onClose,
}: {
  ticket: Ticket
  open: boolean
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [target, setTarget] = useState<TicketHit | null>(null)
  const term = useDebounced(query.trim())

  const results = useQuery({
    queryKey: ['merge-search', term],
    enabled: open && term.length > 1,
    queryFn: () =>
      api<{ tickets: TicketHit[] }>(`/search/tickets?q=${encodeURIComponent(term)}&limit=10`).then(
        (r) => r.tickets.filter((t) => t.id !== ticket.id),
      ),
  })

  const merge = useTicketAction(
    ticket.id,
    (targetId: string) =>
      api(`/tickets/${ticket.id}/merge`, {
        method: 'POST',
        json: { target_ticket_id: targetId },
      }),
    'Ticket merged',
    onClose,
  )

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Merge into another ticket"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!target || merge.isPending}
            onClick={() => target && merge.mutate(target.id)}
          >
            Merge
          </Button>
        </>
      }
    >
      <p className="text-body-sm text-muted mb-16">
        {ticket.ref} closes as a duplicate and its conversation moves to the ticket you pick.
      </p>

      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search tickets…"
        aria-label="Search for the ticket to merge into"
        className={cn(
          'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
          'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
          focusRing,
        )}
      />

      <ul className="mt-16 max-h-[240px] overflow-y-auto">
        {(results.data ?? []).map((hit) => (
          <li key={hit.id}>
            <button
              type="button"
              onClick={() => setTarget(hit)}
              aria-pressed={target?.id === hit.id}
              className={cn(
                'rounded-control flex w-full cursor-pointer items-center justify-between gap-12 px-12 py-8 text-left',
                'hover:bg-surface transition-colors duration-micro',
                target?.id === hit.id && 'bg-surface',
                focusRing,
              )}
            >
              <span className="text-body text-ink truncate">{hit.subject}</span>
              <span className="text-data text-muted shrink-0 font-mono">
                {formatTicketId(hit.display_id)}
              </span>
            </button>
          </li>
        ))}
        {term.length > 1 && results.isSuccess && results.data.length === 0 && (
          <li className="text-body-sm text-muted px-12 py-8">No other tickets match.</li>
        )}
      </ul>
    </Modal>
  )
}

// --- Reopen -----------------------------------------------------------------

export function ReopenModal({
  ticket,
  open,
  onClose,
}: {
  ticket: Ticket
  open: boolean
  onClose: () => void
}) {
  const reopen = useTicketAction(
    ticket.id,
    () => api(`/tickets/${ticket.id}/reopen`, { method: 'POST', json: {} }),
    'Ticket reopened',
    onClose,
  )

  return (
    <ConfirmModal
      open={open}
      onClose={onClose}
      onConfirm={() => reopen.mutate(undefined)}
      title="Reopen this ticket?"
      // App Flow §10/§16 — worth saying out loud, because it changes the SLA
      // numbers this ticket will be reported against.
      message="A reopen starts a fresh resolution timer rather than resuming the original clock."
      confirmLabel="Reopen"
    />
  )
}
