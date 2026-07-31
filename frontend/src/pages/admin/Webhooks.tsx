import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Copy, Plus, Webhook as WebhookIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { ConfirmModal, Modal } from '../../components/Modal'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { ApiError, api } from '../../lib/api'
import { TRIGGERS, humanise } from '../../lib/admin'
import { toast } from '../../lib/toast'
import type { Webhook, WebhookDelivery } from '../../lib/types'
import { cn, relativeTime } from '../../lib/ui'

export function Webhooks() {
  const queryClient = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<Webhook | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const webhooks = useQuery({
    queryKey: ['webhooks'],
    queryFn: () => api<Webhook[]>('/webhooks'),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['webhooks'] })

  const toggle = useMutation({
    mutationFn: (webhook: Webhook) =>
      api<Webhook>(`/webhooks/${webhook.id}`, {
        method: 'PATCH',
        json: { is_active: !webhook.is_active },
      }),
    onSuccess: async () => {
      await invalidate()
      toast('Webhook updated', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not update', 'error'),
  })

  const remove = useMutation({
    mutationFn: (webhook: Webhook) => api<void>(`/webhooks/${webhook.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await invalidate()
      toast('Webhook removed', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not remove', 'error'),
  })

  return (
    <div className="mx-auto max-w-[1440px]">
      <div className="flex flex-wrap items-center justify-between gap-16">
        <div>
          <h1 className="font-display text-h1 font-semibold">Webhooks</h1>
          <p className="text-body text-muted mt-8">
            Outbound events, signed with a per-webhook secret so the receiver can verify them.
          </p>
        </div>
        <Button
          variant="primary"
          icon={<Plus size={16} strokeWidth={1.5} />}
          onClick={() => setCreating(true)}
        >
          Register webhook
        </Button>
      </div>

      <div className="mt-24">
        {webhooks.isPending && <SkeletonRows rows={3} />}
        {webhooks.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load webhooks"
            onRetry={() => void webhooks.refetch()}
          />
        )}
        {webhooks.isSuccess && webhooks.data.length === 0 && (
          <EmptyState
            icon={WebhookIcon}
            title="No webhooks registered"
            message="Register one to push ticket events into another system."
          />
        )}

        <ul className="flex flex-col gap-8">
          {(webhooks.data ?? []).map((webhook) => (
            <li key={webhook.id}>
              <Card className="p-16">
                <div className="flex flex-wrap items-center gap-16">
                  <div className="min-w-[240px] flex-1">
                    <p className="text-body text-ink font-medium">{humanise(webhook.event_type)}</p>
                    <p className="text-body-sm text-muted mt-4 truncate font-mono">
                      {webhook.target_url}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'rounded-pill text-caption px-12 py-4 font-medium tracking-wide uppercase',
                      webhook.is_active
                        ? 'bg-success text-white'
                        : 'border-border text-muted border',
                    )}
                  >
                    {webhook.is_active ? 'Active' : 'Paused'}
                  </span>
                  <Button size="sm" onClick={() => toggle.mutate(webhook)}>
                    {webhook.is_active ? 'Pause' : 'Activate'}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => setExpanded(expanded === webhook.id ? null : webhook.id)}
                    aria-expanded={expanded === webhook.id}
                  >
                    Deliveries
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(webhook)}>
                    Remove
                  </Button>
                </div>
                {expanded === webhook.id && <Deliveries webhookId={webhook.id} />}
              </Card>
            </li>
          ))}
        </ul>
      </div>

      {creating && <RegisterModal onClose={() => setCreating(false)} />}

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Remove this webhook?"
        message="Its delivery history goes with it. Pause it instead if you only want to stop sending."
        confirmLabel="Remove"
        destructive
      />
    </div>
  )
}

function RegisterModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [eventType, setEventType] = useState<string>(TRIGGERS[0])
  const [url, setUrl] = useState('')
  const [secret, setSecret] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () =>
      api<Webhook>('/webhooks', {
        method: 'POST',
        json: { event_type: eventType, target_url: url.trim() },
      }),
    onSuccess: async (webhook) => {
      await queryClient.invalidateQueries({ queryKey: ['webhooks'] })
      // The plaintext secret comes back exactly once (Doc 05 Sensitive Fields),
      // so the modal stays open holding it rather than closing on success.
      setSecret(webhook.secret ?? null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not register', 'error'),
  })

  return (
    <Modal open onClose={onClose} title={secret ? 'Copy the signing secret' : 'Register a webhook'}>
      {secret ? (
        <div className="flex flex-col gap-16">
          <p className="text-body-sm text-muted">
            This is shown once and never again. Configure the receiver with it now — if it is lost,
            the webhook has to be re-registered.
          </p>
          <div className="border-border rounded-card flex items-center gap-12 border p-16">
            <code className="text-body-sm min-w-0 flex-1 break-all">{secret}</code>
            <Button
              size="sm"
              icon={<Copy size={14} strokeWidth={1.5} />}
              onClick={() => {
                void navigator.clipboard.writeText(secret)
                toast('Secret copied', 'success')
              }}
            >
              Copy
            </Button>
          </div>
          <div className="flex justify-end">
            <Button variant="primary" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-16">
          <Select label="Event" value={eventType} onChange={(e) => setEventType(e.target.value)}>
            {TRIGGERS.map((trigger) => (
              <option key={trigger} value={trigger}>
                {humanise(trigger)}
              </option>
            ))}
          </Select>
          <Input
            label="Target URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/hooks/agentdesk"
            hint="Must be a public http(s) endpoint — internal addresses are refused."
          />
          <div className="flex justify-end gap-8">
            <Button onClick={onClose}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!url.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              Register
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}

function Deliveries({ webhookId }: { webhookId: string }) {
  const deliveries = useQuery({
    queryKey: ['webhook-deliveries', webhookId],
    queryFn: () => api<WebhookDelivery[]>(`/webhooks/${webhookId}/deliveries?limit=50`),
  })

  if (deliveries.isPending) return <SkeletonRows rows={3} />
  if (deliveries.isSuccess && deliveries.data.length === 0) {
    return (
      <p className="text-body-sm text-muted mt-16">
        Nothing delivered yet — the first matching event will appear here.
      </p>
    )
  }

  return (
    <div className="border-border mt-16 overflow-x-auto border-t pt-16">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-border border-b">
            {['Event', 'Status', 'Attempts', 'When'].map((column) => (
              <th
                key={column}
                scope="col"
                className="text-caption text-muted px-8 py-8 tracking-wide uppercase"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(deliveries.data ?? []).map((delivery) => (
            <tr key={delivery.id} className="border-border border-b last:border-b-0">
              <td className="text-body-sm px-8 py-8 whitespace-nowrap">
                {humanise(delivery.event_type)}
              </td>
              <td className="px-8 py-8">
                <span
                  className={cn(
                    'text-data font-mono',
                    delivery.response_status && delivery.response_status < 300
                      ? 'text-success'
                      : 'text-critical',
                  )}
                >
                  {delivery.response_status ?? 'no response'}
                </span>
              </td>
              <td className="text-body-sm px-8 py-8 font-mono">{delivery.attempt_count}</td>
              <td className="text-body-sm text-muted px-8 py-8 whitespace-nowrap">
                <time dateTime={delivery.created_at}>{relativeTime(delivery.created_at)}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
