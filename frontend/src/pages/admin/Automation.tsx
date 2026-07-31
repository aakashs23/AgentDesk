import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, Workflow } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { ConfirmModal, Modal } from '../../components/Modal'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import {
  ACTION_PARAM,
  ACTION_TYPES,
  CONDITION_FIELDS,
  CONDITION_OPS,
  TRIGGERS,
  humanise,
  ruleProblem,
  type ActionType,
  type ConditionField,
  type RuleAction,
  type RuleCondition,
} from '../../lib/admin'
import { byId, useCategories, usePriorities, useQueues, useStaffDirectory } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { AutomationLog, AutomationRule, Ticket } from '../../lib/types'
import { cn, focusRing, formatTicketId, relativeTime } from '../../lib/ui'

export function AutomationRules() {
  const [tab, setTab] = useState('rules')

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Automation Rules</h1>
      <p className="text-body text-muted mt-8">
        Trigger → conditions → actions, evaluated at write time. A lower priority number wins a
        conflict.
      </p>

      <div className="mt-24">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'rules', label: 'Rules' },
            { id: 'logs', label: 'Execution log' },
          ]}
        />
      </div>

      <div className="mt-24">{tab === 'rules' ? <RuleList /> : <ExecutionLog />}</div>
    </div>
  )
}

// --- Rules ------------------------------------------------------------------

function RuleList() {
  const queryClient = useQueryClient()
  const [building, setBuilding] = useState(false)
  const [editing, setEditing] = useState<AutomationRule | null>(null)
  const [deleting, setDeleting] = useState<AutomationRule | null>(null)

  const rules = useQuery({
    queryKey: ['automation-rules'],
    queryFn: () => api<AutomationRule[]>('/admin/automation-rules'),
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['automation-rules'] })

  const toggle = useMutation({
    mutationFn: (rule: AutomationRule) =>
      api<AutomationRule>(`/admin/automation-rules/${rule.id}`, {
        method: 'PATCH',
        json: { is_active: !rule.is_active },
      }),
    onSuccess: async (rule) => {
      await invalidate()
      // §25 steps 7–8: activation is its own act, and it is audited.
      toast(rule.is_active ? 'Rule activated' : 'Rule paused', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not update', 'error'),
  })

  const remove = useMutation({
    mutationFn: (rule: AutomationRule) =>
      api<void>(`/admin/automation-rules/${rule.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await invalidate()
      toast('Rule deleted', 'success')
      setDeleting(null)
    },
    // 409 = the rule has execution history; the message says to pause it instead.
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <>
      <div className="flex justify-end">
        <Button
          variant="primary"
          icon={<Plus size={16} strokeWidth={1.5} />}
          onClick={() => setBuilding(true)}
        >
          New rule
        </Button>
      </div>

      <div className="mt-24">
        {rules.isPending && <SkeletonRows rows={4} />}
        {rules.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load rules"
            onRetry={() => void rules.refetch()}
          />
        )}
        {rules.isSuccess && rules.data.length === 0 && (
          <EmptyState
            icon={Workflow}
            title="No automation rules"
            message="Rules run on every matching write — start with something narrow and preview it first."
            action={
              <Button variant="primary" onClick={() => setBuilding(true)}>
                New rule
              </Button>
            }
          />
        )}

        <ul className="flex flex-col gap-8">
          {(rules.data ?? []).map((rule) => (
            <li key={rule.id}>
              <Card className="flex flex-wrap items-center gap-16 p-16">
                <div className="min-w-[240px] flex-1">
                  <p className="text-body text-ink font-medium">{rule.name}</p>
                  <p className="text-body-sm text-muted mt-4">
                    On {humanise(rule.trigger_type).toLowerCase()} · {rule.conditions.length}{' '}
                    condition{rule.conditions.length === 1 ? '' : 's'} · {rule.actions.length}{' '}
                    action
                    {rule.actions.length === 1 ? '' : 's'} · priority {rule.priority}
                  </p>
                </div>
                <span
                  className={cn(
                    'rounded-pill text-caption px-12 py-4 font-medium tracking-wide uppercase',
                    rule.is_active ? 'bg-success text-white' : 'border-border text-muted border',
                  )}
                >
                  {rule.is_active ? 'Active' : 'Paused'}
                </span>
                <Button size="sm" onClick={() => toggle.mutate(rule)}>
                  {rule.is_active ? 'Pause' : 'Activate'}
                </Button>
                <Button size="sm" onClick={() => setEditing(rule)}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleting(rule)}>
                  Delete
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      {(building || editing) && (
        <RuleBuilder
          rule={editing}
          onClose={() => {
            setBuilding(false)
            setEditing(null)
          }}
        />
      )}

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this rule?"
        message="A rule that has already run cannot be deleted — pause it instead, so its execution history stays readable."
        confirmLabel="Delete"
        destructive
      />
    </>
  )
}

// --- The builder (App Flow §25) ---------------------------------------------

interface Draft {
  name: string
  trigger_type: string
  conditions: RuleCondition[]
  actions: RuleAction[]
  priority: number
}

function toDraft(rule: AutomationRule | null): Draft {
  if (!rule) {
    return { name: '', trigger_type: 'ticket_created', conditions: [], actions: [], priority: 100 }
  }
  return {
    name: rule.name,
    trigger_type: rule.trigger_type,
    conditions: rule.conditions as RuleCondition[],
    actions: rule.actions as RuleAction[],
    priority: rule.priority,
  }
}

/**
 * §25's seven steps in one modal: name, trigger, conditions, actions, preview,
 * save, activate. The preview (step 5) is the reason this is not just a form —
 * it calls `/admin/automation-rules/preview` and shows real tickets the draft
 * would have matched, before anything is written.
 */
function RuleBuilder({ rule, onClose }: { rule: AutomationRule | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft>(() => toDraft(rule))
  const [preview, setPreview] = useState<Ticket[] | null>(null)

  const problem = ruleProblem(draft)

  const previewRule = useMutation({
    mutationFn: () =>
      api<Ticket[]>('/admin/automation-rules/preview', {
        method: 'POST',
        json: { conditions: draft.conditions },
      }),
    onSuccess: setPreview,
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not preview', 'error'),
  })

  const save = useMutation({
    mutationFn: (activate: boolean) => {
      const payload = { ...draft, is_active: activate }
      return rule
        ? api<AutomationRule>(`/admin/automation-rules/${rule.id}`, {
            method: 'PATCH',
            json: payload,
          })
        : api<AutomationRule>('/admin/automation-rules', { method: 'POST', json: payload })
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['automation-rules'] })
      toast(saved.is_active ? 'Rule saved and activated' : 'Rule saved, paused', 'success')
      onClose()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  const update = (patch: Partial<Draft>) => {
    setDraft((current) => ({ ...current, ...patch }))
    setPreview(null) // a changed draft's old preview is a lie
  }

  return (
    <Modal open onClose={onClose} title={rule ? 'Edit rule' : 'New rule'}>
      <div className="flex flex-col gap-24">
        <Input
          label="Rule name"
          value={draft.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="Escalate critical billing tickets"
        />

        <div className="flex flex-wrap gap-16">
          <div className="min-w-[220px] flex-1">
            <Select
              label="Trigger"
              value={draft.trigger_type}
              onChange={(e) => update({ trigger_type: e.target.value })}
            >
              {TRIGGERS.map((trigger) => (
                <option key={trigger} value={trigger}>
                  {humanise(trigger)}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-[140px]">
            <Input
              label="Priority"
              type="number"
              min={1}
              max={999}
              value={String(draft.priority)}
              onChange={(e) => update({ priority: Number(e.target.value) || 100 })}
              hint="Lower wins"
            />
          </div>
        </div>

        <ConditionEditor
          conditions={draft.conditions}
          onChange={(conditions) => update({ conditions })}
        />
        <ActionEditor actions={draft.actions} onChange={(actions) => update({ actions })} />

        {/* §25 step 5 */}
        <div>
          <div className="flex flex-wrap items-center justify-between gap-12">
            <h3 className="text-body font-medium">Preview</h3>
            <Button size="sm" disabled={previewRule.isPending} onClick={() => previewRule.mutate()}>
              Show matching tickets
            </Button>
          </div>
          {preview && (
            <div className="border-border rounded-card mt-12 border p-16">
              {preview.length === 0 ? (
                <p className="text-body-sm text-muted">
                  No existing ticket matches these conditions. That is fine for a narrow rule — and
                  a warning sign for one you expected to be broad.
                </p>
              ) : (
                <ul className="flex flex-col gap-8">
                  {preview.map((ticket) => (
                    <li key={ticket.id} className="text-body-sm flex gap-12">
                      <span className="text-muted font-mono">
                        {ticket.ref || formatTicketId(ticket.display_id)}
                      </span>
                      <span className="truncate">{ticket.subject}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {problem && <p className="text-body-sm text-muted">{problem}</p>}
      </div>

      <div className="mt-24 flex flex-wrap justify-end gap-8">
        <Button onClick={onClose}>Cancel</Button>
        <Button disabled={Boolean(problem) || save.isPending} onClick={() => save.mutate(false)}>
          Save paused
        </Button>
        <Button
          variant="primary"
          disabled={Boolean(problem) || save.isPending}
          onClick={() => save.mutate(true)}
        >
          Save &amp; activate
        </Button>
      </div>
    </Modal>
  )
}

/** Fields that name a row get a picker; the rest get a text box. Typing a raw
 *  uuid into a free-text condition is the most reliable way to build a rule
 *  that silently never matches. */
function ValueInput({
  field,
  value,
  onChange,
}: {
  field: ConditionField
  value: string
  onChange: (value: string) => void
}) {
  const categories = useCategories()
  const priorities = usePriorities()
  const queues = useQueues()
  const staff = useStaffDirectory()

  const options: { id: string; label: string }[] | null =
    field === 'category_id'
      ? (categories.data ?? []).map((c) => ({ id: c.id, label: c.name }))
      : field === 'priority_id'
        ? (priorities.data ?? []).map((p) => ({ id: p.id, label: p.name }))
        : field === 'queue_id'
          ? (queues.data ?? []).map((q) => ({ id: q.id, label: q.name }))
          : field === 'assignee_id'
            ? (staff.data ?? []).map((u) => ({ id: u.id, label: u.full_name }))
            : null

  if (!options) {
    return (
      <input
        value={value}
        aria-label="Condition value"
        onChange={(e) => onChange(e.target.value)}
        placeholder={field === 'status' ? 'in_progress' : 'value'}
        className={cn(
          'rounded-control border-border bg-canvas text-ink h-[44px] min-w-[160px] flex-1 border px-12',
          focusRing,
        )}
      />
    )
  }

  return (
    <Select
      aria-label="Condition value"
      className="min-w-[160px] flex-1"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Choose…</option>
      {options.map((option) => (
        <option key={option.id} value={option.id}>
          {option.label}
        </option>
      ))}
    </Select>
  )
}

function ConditionEditor({
  conditions,
  onChange,
}: {
  conditions: RuleCondition[]
  onChange: (conditions: RuleCondition[]) => void
}) {
  const set = (index: number, patch: Partial<RuleCondition>) =>
    onChange(conditions.map((c, i) => (i === index ? { ...c, ...patch } : c)))

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-12">
        <h3 className="text-body font-medium">Conditions</h3>
        <Button
          size="sm"
          onClick={() => onChange([...conditions, { field: 'category_id', op: 'eq', value: '' }])}
        >
          Add condition
        </Button>
      </div>
      <p className="text-body-sm text-muted mt-4">
        All conditions must hold. No conditions means the rule fires on every trigger.
      </p>

      <div className="mt-12 flex flex-col gap-8">
        {conditions.map((condition, index) => (
          <div key={index} className="flex flex-wrap items-center gap-8">
            <Select
              aria-label="Condition field"
              className="max-w-[180px]"
              value={condition.field}
              onChange={(e) => set(index, { field: e.target.value as ConditionField, value: '' })}
            >
              {CONDITION_FIELDS.map((field) => (
                <option key={field} value={field}>
                  {humanise(field.replace(/_id$/, ''))}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Condition operator"
              className="max-w-[120px]"
              value={condition.op}
              onChange={(e) => set(index, { op: e.target.value as RuleCondition['op'] })}
            >
              {CONDITION_OPS.map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </Select>
            <ValueInput
              field={condition.field}
              value={condition.value}
              onChange={(value) => set(index, { value })}
            />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange(conditions.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}

function ActionEditor({
  actions,
  onChange,
}: {
  actions: RuleAction[]
  onChange: (actions: RuleAction[]) => void
}) {
  const priorities = usePriorities()
  const staff = useStaffDirectory()
  const priorityById = byId(priorities.data)

  const set = (index: number, patch: Partial<RuleAction>) =>
    onChange(actions.map((a, i) => (i === index ? { ...a, ...patch } : a)))

  const targetInput = (action: RuleAction, index: number) => {
    const param = ACTION_PARAM[action.type]
    if (!param) {
      return <span className="text-body-sm text-muted">Routes to the team lead</span>
    }
    if (param === 'tag') {
      return (
        <input
          value={String(action.tag ?? '')}
          aria-label="Tag name"
          onChange={(e) => set(index, { tag: e.target.value })}
          placeholder="tag name"
          className={cn(
            'rounded-control border-border bg-canvas text-ink h-[44px] min-w-[160px] flex-1 border px-12',
            focusRing,
          )}
        />
      )
    }
    const options =
      param === 'priority_id'
        ? [...priorityById.values()].map((p) => ({ id: p.id, label: p.name }))
        : (staff.data ?? []).map((u) => ({ id: u.id, label: u.full_name }))
    return (
      <Select
        aria-label="Action target"
        className="min-w-[160px] flex-1"
        value={String(action[param] ?? '')}
        onChange={(e) => set(index, { [param]: e.target.value })}
      >
        <option value="">Choose…</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </Select>
    )
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-12">
        <h3 className="text-body font-medium">Actions</h3>
        <Button size="sm" onClick={() => onChange([...actions, { type: 'assign' }])}>
          Add action
        </Button>
      </div>
      <p className="text-body-sm text-muted mt-4">
        When two rules write the same field, the lower priority number wins and the loser is
        recorded in the Audit Log.
      </p>

      <div className="mt-12 flex flex-col gap-8">
        {actions.map((action, index) => (
          <div key={index} className="flex flex-wrap items-center gap-8">
            <Select
              aria-label="Action type"
              className="max-w-[180px]"
              value={action.type}
              onChange={(e) =>
                onChange(
                  actions.map((a, i) => (i === index ? { type: e.target.value as ActionType } : a)),
                )
              }
            >
              {ACTION_TYPES.map((type) => (
                <option key={type} value={type}>
                  {humanise(type)}
                </option>
              ))}
            </Select>
            {targetInput(action, index)}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onChange(actions.filter((_, i) => i !== index))}
            >
              Remove
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}

// --- Execution log ----------------------------------------------------------

const LOG_STATUS_STYLE: Record<string, string> = {
  success: 'bg-success text-white',
  failed: 'bg-critical text-white',
  skipped: 'border border-border text-muted',
}

/** Read-only debugging view over `automation_execution_logs` — one row per
 *  evaluation, including the ones that matched nothing. */
function ExecutionLog() {
  const [status, setStatus] = useState('')
  const rules = useQuery({
    queryKey: ['automation-rules'],
    queryFn: () => api<AutomationRule[]>('/admin/automation-rules'),
  })
  const logs = useQuery({
    queryKey: ['automation-logs'],
    queryFn: () => api<AutomationLog[]>('/admin/automation-logs?limit=200'),
  })

  const ruleName = (id: string) =>
    rules.data?.find((rule) => rule.id === id)?.name ?? 'Deleted rule'
  const visible = (logs.data ?? []).filter((log) => !status || log.execution_status === status)

  return (
    <>
      <div className="flex flex-wrap items-end gap-16">
        <Select label="Result" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All results</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="skipped">Skipped</option>
        </Select>
      </div>

      <div className="mt-24">
        {logs.isPending && <SkeletonRows rows={5} />}
        {logs.isSuccess && visible.length === 0 && (
          <EmptyState icon={Workflow} title="No executions recorded" />
        )}
        <ul className="flex flex-col gap-8">
          {visible.map((log) => (
            <li key={log.id}>
              <Card className="flex flex-wrap items-center gap-16 p-16">
                <span
                  className={cn(
                    'rounded-pill text-caption px-12 py-4 font-medium tracking-wide uppercase',
                    LOG_STATUS_STYLE[log.execution_status] ?? 'border-border border',
                  )}
                >
                  {log.execution_status}
                </span>
                <div className="min-w-[200px] flex-1">
                  <p className="text-body text-ink font-medium">
                    {ruleName(log.automation_rule_id)}
                  </p>
                  {log.error_message && (
                    <p className="text-body-sm text-critical mt-4">{log.error_message}</p>
                  )}
                </div>
                {log.ticket_id && (
                  <Link
                    to={`/agent/tickets/${log.ticket_id}`}
                    className={cn('text-body-sm text-brand-start font-medium', focusRing)}
                  >
                    View ticket
                  </Link>
                )}
                <time
                  dateTime={log.created_at}
                  className="text-body-sm text-muted min-w-[120px] text-right"
                >
                  {relativeTime(log.created_at)}
                </time>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
