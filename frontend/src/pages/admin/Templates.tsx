import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, FileText, Plus } from 'lucide-react'
import { useState } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { ConfirmModal, Modal } from '../../components/Modal'
import { Input } from '../../components/Input'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { Tabs } from '../../components/Tabs'
import { Toggle } from '../../components/Toggle'
import { ApiError, api } from '../../lib/api'
import { humanise } from '../../lib/admin'
import { toast } from '../../lib/toast'
import { NOTIFICATION_TRIGGERS, type NotificationTemplate } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'

// slack/teams have no adapter yet (App Flow §29), so they are not offered.
const CHANNELS = ['email', 'in_app'] as const

/** The variables `notifications/templates.py` interpolates — listed so an Admin
 *  writing copy does not have to guess at the vocabulary. */
const VARIABLES = [
  '{{ticket.display_id}}',
  '{{ticket.subject}}',
  '{{ticket.status}}',
  '{{user.full_name}}',
]

export function TemplatesAndBranding() {
  const [tab, setTab] = useState('templates')

  return (
    <div>
      <h1 className="text-h1 font-semibold">Templates &amp; Branding</h1>
      <p className="text-body text-muted mt-8">
        The copy every notification is rendered from, per trigger and channel.
      </p>

      <div className="mt-24">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'templates', label: 'Notification templates' },
            { id: 'branding', label: 'Branding' },
          ]}
        />
      </div>

      <div className="mt-24">{tab === 'templates' ? <TemplateList /> : <BrandingPanel />}</div>
    </div>
  )
}

function TemplateList() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<NotificationTemplate | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<NotificationTemplate | null>(null)

  const templates = useQuery({
    queryKey: ['notification-templates'],
    queryFn: () => api<NotificationTemplate[]>('/notification-templates'),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['notification-templates'] })

  const toggle = useMutation({
    mutationFn: (template: NotificationTemplate) =>
      api<NotificationTemplate>(`/notification-templates/${template.id}`, {
        method: 'PATCH',
        json: { is_active: !template.is_active },
      }),
    onSuccess: async (template) => {
      await invalidate()
      // Doc 05: an inactive template falls back to the system default copy —
      // deactivating never means "send nothing".
      toast(
        template.is_active ? 'Template active' : 'Template off — system default copy is used',
        'success',
      )
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not update', 'error'),
  })

  const remove = useMutation({
    mutationFn: (template: NotificationTemplate) =>
      api<void>(`/notification-templates/${template.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await invalidate()
      toast('Template deleted', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <>
      <div className="flex justify-end">
        <Button
          variant="primary"
          icon={<Plus size={16} strokeWidth={1.5} />}
          onClick={() => setCreating(true)}
        >
          New template
        </Button>
      </div>

      <div className="mt-24">
        {templates.isPending && <SkeletonRows rows={5} />}
        {templates.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load templates"
            onRetry={() => void templates.refetch()}
          />
        )}
        {templates.isSuccess && templates.data.length === 0 && (
          <EmptyState
            icon={FileText}
            title="No templates"
            message="Notifications fall back to built-in copy until you add one."
          />
        )}

        {(templates.data ?? []).length > 0 && (
          <Card className="overflow-hidden p-0">
            <ul>
              {(templates.data ?? []).map((template) => (
                <li
                  key={template.id}
                  className="border-divider flex flex-wrap items-center gap-16 p-16 not-last:border-b"
                >
                  <div className="min-w-[240px] flex-1">
                    <p className="text-body text-ink font-medium">
                      {humanise(template.trigger_type)}
                    </p>
                    <p className="text-body-sm text-muted mt-4 truncate">
                      {template.channel} · {template.subject_template ?? template.body_template}
                    </p>
                  </div>
                  <Toggle
                    checked={template.is_active}
                    onChange={() => toggle.mutate(template)}
                    label={template.is_active ? 'Active' : 'Off'}
                  />
                  <Button size="sm" onClick={() => setEditing(template)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(template)}>
                    Delete
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {(editing || creating) && (
        <TemplateEditor
          template={editing}
          onClose={() => {
            setEditing(null)
            setCreating(false)
          }}
        />
      )}

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this template?"
        message="That trigger falls back to the built-in copy."
        confirmLabel="Delete"
        destructive
      />
    </>
  )
}

function TemplateEditor({
  template,
  onClose,
}: {
  template: NotificationTemplate | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [trigger, setTrigger] = useState(template?.trigger_type ?? NOTIFICATION_TRIGGERS[0])
  const [channel, setChannel] = useState(template?.channel ?? 'email')
  const [subject, setSubject] = useState(template?.subject_template ?? '')
  const [body, setBody] = useState(template?.body_template ?? '')

  const save = useMutation({
    mutationFn: () => {
      // The API fixes trigger/channel at creation: a PATCH may only change copy.
      const payload = template
        ? { subject_template: subject || null, body_template: body }
        : {
            trigger_type: trigger,
            channel,
            subject_template: channel === 'email' ? subject || null : null,
            body_template: body,
          }
      return template
        ? api<NotificationTemplate>(`/notification-templates/${template.id}`, {
            method: 'PATCH',
            json: payload,
          })
        : api<NotificationTemplate>('/notification-templates', { method: 'POST', json: payload })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['notification-templates'] })
      toast('Template saved', 'success')
      onClose()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  return (
    <Modal open onClose={onClose} title={template ? 'Edit template' : 'New template'}>
      <div className="flex flex-col gap-16">
        <Select
          label="Trigger"
          value={trigger}
          disabled={Boolean(template)}
          onChange={(e) => setTrigger(e.target.value as (typeof NOTIFICATION_TRIGGERS)[number])}
        >
          {NOTIFICATION_TRIGGERS.map((t) => (
            <option key={t} value={t}>
              {humanise(t)}
            </option>
          ))}
        </Select>
        <Select
          label="Channel"
          value={channel}
          disabled={Boolean(template)}
          onChange={(e) => setChannel(e.target.value)}
        >
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {humanise(c)}
            </option>
          ))}
        </Select>

        {channel === 'email' && (
          <Input
            label="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            hint="In-app notifications have no subject line."
          />
        )}

        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Body</span>
          <textarea
            rows={8}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary w-full border p-12',
              'focus:border-primary transition-colors duration-micro',
              focusRing,
            )}
          />
        </label>

        <div className="flex flex-wrap gap-8">
          {VARIABLES.map((variable) => (
            <button
              key={variable}
              type="button"
              onClick={() => setBody((current) => `${current}${variable}`)}
              className={cn(
                'rounded-pill border-border text-body-sm text-muted hover:text-ink border px-12 py-4 font-mono',
                focusRing,
              )}
            >
              {variable}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-24 flex justify-end gap-8">
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="primary"
          disabled={!body.trim() || save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </Button>
      </div>
    </Modal>
  )
}

/**
 * Branding is read-only, and says why. Doc 05 defines no settings/branding
 * table and the schema invariant forbids adding one, so a logo upload or a
 * portal accent picker would have nowhere to persist to. What the product does
 * guarantee is stated instead — Doc 07 is light on every surface, and each
 * user's own override lives on `users.theme_preference`.
 */
function BrandingPanel() {
  return (
    <Card>
      <h2 className="text-h3 font-semibold">Portal appearance</h2>
      <p className="text-body-sm text-muted mt-8">
        Fixed in this build. Every surface is light by default; dark is a personal choice, not a
        tenant setting, and each person switches it in their own Account Settings.
      </p>
      <ul className="text-body-sm mt-16 flex flex-col gap-8">
        <li className="border-divider flex items-center justify-between border-b py-8">
          <span>Customer Portal</span>
          <span className="text-muted">Light</span>
        </li>
        <li className="border-divider flex items-center justify-between border-b py-8">
          <span>Agent Console</span>
          <span className="text-muted">Light</span>
        </li>
        <li className="flex items-center justify-between py-8">
          <span>Admin Dashboard</span>
          <span className="text-muted">Light</span>
        </li>
        <li className="border-divider flex items-center justify-between border-t py-8">
          <span>Dark mode</span>
          <span className="text-muted">Per person, in Account Settings</span>
        </li>
      </ul>
      <p className="text-body-sm text-muted mt-16">
        A tenant logo and custom accent need a settings table that the backend schema does not
        define; adding one is a schema change, not a screen.
      </p>
    </Card>
  )
}
