import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, BellOff } from 'lucide-react'
import { useNavigate } from 'react-router'

import { EmptyState, ErrorState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import { api } from '../../lib/api'
import type { Notification } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

/** Human copy per trigger — the stored payload is templated for email, which
 *  reads oddly in-app, so the feed uses its own short summaries. */
const TRIGGER_COPY: Record<string, string> = {
  ticket_assigned: 'Your ticket was assigned',
  ticket_replied: 'New reply on your ticket',
  status_changed: 'Ticket status changed',
  sla_warning: 'Response is due soon',
  sla_breached: 'Response is overdue',
  escalation: 'Your ticket was escalated',
  mention: 'You were mentioned',
  ticket_closed: 'Ticket closed',
  automation_executed: 'An automation ran on your ticket',
}

export function Notifications() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const notifications = useQuery({
    queryKey: ['notifications', 'feed'],
    queryFn: () => api<Notification[]>('/notifications?limit=50'),
  })

  const markRead = useMutation({
    mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: 'PATCH', json: {} }),
    onSuccess: async () => {
      // Refresh both the feed and the top bar's unread badge.
      await queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  function open(notification: Notification) {
    if (!notification.is_read) markRead.mutate(notification.id)
    // Doc 03 §8: clicking a notification deep-links to the relevant ticket.
    if (notification.ticket_id) navigate(`/portal/tickets/${notification.ticket_id}`)
  }

  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="font-display text-h1 font-semibold">Notifications</h1>

      <div className="mt-24">
        {notifications.isPending && <SkeletonRows rows={5} />}

        {notifications.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load notifications"
            onRetry={() => void notifications.refetch()}
          />
        )}

        {notifications.isSuccess && notifications.data.length === 0 && (
          <EmptyState icon={BellOff} title="You're all caught up" />
        )}

        <ul className="flex flex-col gap-8">
          {(notifications.data ?? []).map((notification) => (
            <li key={notification.id}>
              <button
                type="button"
                onClick={() => open(notification)}
                className={cn(
                  'rounded-card border-border flex w-full cursor-pointer flex-col gap-4 border p-16 text-left',
                  'hover:bg-surface transition-colors duration-micro',
                  focusRing,
                )}
              >
                <div className="flex items-center gap-8">
                  {/* Unread is marked with a dot *and* a bolder weight — never
                      colour alone (Doc 04, Accessibility). */}
                  {!notification.is_read && (
                    <span
                      aria-label="Unread"
                      className="bg-brand-start size-[8px] shrink-0 rounded-pill"
                    />
                  )}
                  <span
                    className={cn('text-body text-ink', !notification.is_read && 'font-medium')}
                  >
                    {TRIGGER_COPY[notification.trigger_type] ?? notification.trigger_type}
                  </span>
                </div>
                <time className="text-body-sm text-muted" dateTime={notification.created_at}>
                  {relativeTime(notification.created_at)}
                </time>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
