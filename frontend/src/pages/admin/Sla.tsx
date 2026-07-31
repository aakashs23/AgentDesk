import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Timer } from 'lucide-react'
import { useState } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { ConfirmModal } from '../../components/Modal'
import { PriorityPill } from '../../components/StatusPill'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { ApiError, api } from '../../lib/api'
import { formatMinutes } from '../../lib/admin'
import { byId, useCategories, usePriorities, useSlaRules } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { SlaRule } from '../../lib/types'

/**
 * SLA Rules (Doc 03 §1, §16). One policy per (category, priority) pair, with a
 * category-less row acting as the default for that priority — which is exactly
 * how `timers.policy_for` resolves a match, most specific first.
 */
export function SlaRules() {
  const rules = useSlaRules()
  const categories = useCategories()
  const priorities = usePriorities()
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState<SlaRule | null>(null)

  const categoryById = byId(categories.data)
  const priorityById = byId(priorities.data)

  const remove = useMutation({
    mutationFn: (rule: SlaRule) => api<void>(`/admin/sla-rules/${rule.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sla-rules'] })
      toast('SLA rule deleted', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">SLA Rules</h1>
      <p className="text-body text-muted mt-8">
        Response and resolution targets per category and priority. The most specific match wins; a
        rule with no category is the default for that priority.
      </p>

      <Card className="mt-24">
        <h2 className="text-h3 font-display font-semibold">New rule</h2>
        <SlaRuleForm />
      </Card>

      <p className="text-body-sm text-muted mt-24">
        Editing a rule does not retime tickets already running against it — timers are set once, at
        classification (App Flow §16).
      </p>

      <div className="mt-16">
        {rules.isPending && <SkeletonRows rows={4} />}
        {rules.isSuccess && rules.data.length === 0 && (
          <EmptyState
            icon={Timer}
            title="No SLA rules yet"
            message="Without one, a ticket gets no response or resolution deadline at all."
          />
        )}

        <ul className="flex flex-col gap-8">
          {(rules.data ?? []).map((rule) => {
            const priority = priorityById.get(rule.priority_id)
            return (
              <li key={rule.id}>
                <Card className="flex flex-wrap items-center gap-16 p-16">
                  <div className="min-w-[200px] flex-1">
                    <p className="text-body text-ink font-medium">
                      {rule.category_id
                        ? (categoryById.get(rule.category_id)?.name ?? 'Unknown category')
                        : 'All categories'}
                    </p>
                    <p className="text-body-sm text-muted mt-4">
                      {rule.category_id ? 'Specific rule' : 'Default for this priority'}
                    </p>
                  </div>
                  {priority ? (
                    <PriorityPill name={priority.name} colorHex={priority.color_hex} />
                  ) : (
                    <span className="text-body-sm text-muted">Unknown priority</span>
                  )}
                  <Timing rule={rule} />
                  <Button size="sm" variant="ghost" onClick={() => setDeleting(rule)}>
                    Delete
                  </Button>
                </Card>
              </li>
            )
          })}
        </ul>
      </div>

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this SLA rule?"
        message="New tickets matching it will fall back to the default rule, or to no deadline at all."
        confirmLabel="Delete"
        destructive
      />
    </div>
  )
}

/** Inline-editable targets: two number fields that PATCH on blur, because
 *  retuning a threshold is the single most common edit on this screen. */
function Timing({ rule }: { rule: SlaRule }) {
  const queryClient = useQueryClient()
  const patch = useMutation({
    mutationFn: (changes: Partial<SlaRule>) =>
      api<SlaRule>(`/admin/sla-rules/${rule.id}`, { method: 'PATCH', json: changes }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sla-rules'] })
      toast('Target updated', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not update', 'error'),
  })

  const field = (label: string, key: 'response_minutes' | 'resolution_minutes') => (
    <label className="flex flex-col gap-4">
      <span className="text-caption text-muted tracking-wide uppercase">{label}</span>
      <span className="flex items-center gap-8">
        <input
          type="number"
          min={1}
          max={20160}
          aria-label={`${label} in minutes`}
          defaultValue={rule[key]}
          onBlur={(e) => {
            const value = Number(e.target.value)
            if (value && value !== rule[key]) patch.mutate({ [key]: value })
          }}
          className="rounded-control border-border bg-canvas text-data h-[36px] w-[88px] border px-8 font-mono"
        />
        <span className="text-body-sm text-muted">{formatMinutes(rule[key])}</span>
      </span>
    </label>
  )

  return (
    <div className="flex flex-wrap gap-16">
      {field('Response', 'response_minutes')}
      {field('Resolution', 'resolution_minutes')}
    </div>
  )
}

/** Exported for First-Time Admin Setup step 5 (App Flow §26). */
export function SlaRuleForm() {
  const categories = useCategories()
  const priorities = usePriorities()
  const queryClient = useQueryClient()
  const [categoryId, setCategoryId] = useState('')
  const [priorityId, setPriorityId] = useState('')
  const [response, setResponse] = useState('60')
  const [resolution, setResolution] = useState('480')

  const create = useMutation({
    mutationFn: () =>
      api<SlaRule>('/admin/sla-rules', {
        method: 'POST',
        json: {
          category_id: categoryId || null,
          priority_id: priorityId,
          response_minutes: Number(response),
          resolution_minutes: Number(resolution),
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['sla-rules'] })
      toast('SLA rule created', 'success')
    },
    // A 409 is the API refusing a second rule on the same pair — its message
    // says which, so it goes through unchanged.
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create', 'error'),
  })

  const ready = Boolean(priorityId) && Number(response) > 0 && Number(resolution) > 0

  return (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[200px] flex-1">
        <Select label="Category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories (default)</option>
          {(categories.data ?? []).map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
      </div>
      <div className="min-w-[180px]">
        <Select label="Priority" value={priorityId} onChange={(e) => setPriorityId(e.target.value)}>
          <option value="">Choose a priority…</option>
          {(priorities.data ?? []).map((priority) => (
            <option key={priority.id} value={priority.id}>
              {priority.name}
            </option>
          ))}
        </Select>
      </div>
      <div className="w-[150px]">
        <Input
          label="Response (min)"
          type="number"
          min={1}
          max={20160}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
          hint={formatMinutes(Number(response) || 0)}
        />
      </div>
      <div className="w-[150px]">
        <Input
          label="Resolution (min)"
          type="number"
          min={1}
          max={20160}
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
          hint={formatMinutes(Number(resolution) || 0)}
        />
      </div>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!ready || create.isPending}
        onClick={() => create.mutate()}
      >
        Add rule
      </Button>
    </div>
  )
}
