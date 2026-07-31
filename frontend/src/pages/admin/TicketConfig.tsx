import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CornerDownRight, Plus, Tag as TagIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { ConfirmModal } from '../../components/Modal'
import { SkeletonRows } from '../../components/Skeleton'
import { Select } from '../../components/Select'
import { StatusPill } from '../../components/StatusPill'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import { nextStatuses } from '../../lib/agent'
import { TICKET_STATUSES, buildCategoryTree, eligibleParents, flattenTree } from '../../lib/admin'
import { useCategories, usePriorities, useQueues, useTeams } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { Category, Priority, Queue, Tag, TicketStatus } from '../../lib/types'
import { cn, focusRing, statusLabel } from '../../lib/ui'

/**
 * Ticket Configuration (Doc 03 §1): statuses, the category tree, priorities,
 * queues and tags. Tabs rather than one long page — an Admin comes here to
 * change one of the five, not to read all five.
 */
export function TicketConfiguration() {
  const [tab, setTab] = useState('categories')

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Ticket Configuration</h1>
      <p className="text-body text-muted mt-8">
        The vocabulary every ticket is classified against — and what the AI pipeline routes on.
      </p>

      <div className="mt-24">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'categories', label: 'Categories' },
            { id: 'priorities', label: 'Priorities' },
            { id: 'queues', label: 'Queues' },
            { id: 'tags', label: 'Tags' },
            { id: 'statuses', label: 'Statuses' },
          ]}
        />
      </div>

      <div className="mt-24">
        {tab === 'categories' && <CategoryPanel />}
        {tab === 'priorities' && <PriorityPanel />}
        {tab === 'queues' && <QueuePanel />}
        {tab === 'tags' && <TagPanel />}
        {tab === 'statuses' && <StatusPanel />}
      </div>
    </div>
  )
}

/** Every panel below is the same shape: a create card, then the live list. */
function Panel({
  title,
  form,
  children,
}: {
  title: string
  form: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <>
      <Card>
        <h2 className="text-h3 font-display font-semibold">{title}</h2>
        {form}
      </Card>
      <div className="mt-24">{children}</div>
    </>
  )
}

// --- Categories -------------------------------------------------------------

function CategoryPanel() {
  const categories = useCategories()
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState<Category | null>(null)

  const tree = buildCategoryTree(categories.data ?? [])
  const rows = flattenTree(tree)

  const reparent = useMutation({
    mutationFn: ({ id, parentId }: { id: string; parentId: string | null }) =>
      api<Category>(`/admin/categories/${id}`, {
        method: 'PATCH',
        json: { parent_id: parentId },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast('Category moved', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not move', 'error'),
  })

  const remove = useMutation({
    mutationFn: (category: Category) =>
      api<void>(`/admin/categories/${category.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast('Category deleted', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <Panel title="New category" form={<CategoryCreateForm />}>
      {categories.isPending && <SkeletonRows rows={4} />}
      {categories.isSuccess && rows.length === 0 && (
        <EmptyState
          icon={CornerDownRight}
          title="No categories yet"
          message="The AI classifier picks from this tree — without it, every ticket stays unclassified."
        />
      )}
      <ul className="flex flex-col gap-8">
        {rows.map((node) => (
          <li key={node.id}>
            <Card
              className="flex flex-wrap items-center gap-16 p-16"
              // Indentation is the tree; `depth` is capped at the API's own
              // two-level convention but nothing breaks if it goes deeper.
              style={{ marginLeft: `${Math.min(node.depth, 4) * 24}px` }}
            >
              <div className="min-w-0 flex-1">
                <p className="text-body text-ink truncate font-medium">{node.name}</p>
                {node.depth > 0 && <p className="text-body-sm text-muted">Sub-category</p>}
              </div>
              <Select
                aria-label={`Parent of ${node.name}`}
                className="max-w-[220px]"
                value={node.parent_id ?? ''}
                onChange={(e) => reparent.mutate({ id: node.id, parentId: e.target.value || null })}
              >
                <option value="">Top level</option>
                {eligibleParents(tree, node.id).map((option) => (
                  <option key={option.id} value={option.id}>
                    {'— '.repeat(option.depth)}
                    {option.name}
                  </option>
                ))}
              </Select>
              <Button size="sm" variant="ghost" onClick={() => setDeleting(node)}>
                Delete
              </Button>
            </Card>
          </li>
        ))}
      </ul>

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this category?"
        message="Only possible while no ticket, sub-category, SLA rule or article still points at it."
        confirmLabel="Delete"
        destructive
      />
    </Panel>
  )
}

/** Exported for First-Time Admin Setup step 3 (App Flow §26). */
export function CategoryCreateForm() {
  const categories = useCategories()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [parentId, setParentId] = useState('')

  const create = useMutation({
    mutationFn: () =>
      api<Category>('/admin/categories', {
        method: 'POST',
        json: { name: name.trim(), parent_id: parentId || null },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast('Category created', 'success')
      setName('')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create', 'error'),
  })

  const tree = buildCategoryTree(categories.data ?? [])

  return (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[240px] flex-1">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Billing, Access, Hardware…"
        />
      </div>
      <div className="min-w-[200px]">
        <Select label="Parent" value={parentId} onChange={(e) => setParentId(e.target.value)}>
          <option value="">Top level</option>
          {flattenTree(tree).map((node) => (
            <option key={node.id} value={node.id}>
              {'— '.repeat(node.depth)}
              {node.name}
            </option>
          ))}
        </Select>
      </div>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!name.trim() || create.isPending}
        onClick={() => create.mutate()}
      >
        Add category
      </Button>
    </div>
  )
}

// --- Priorities -------------------------------------------------------------

function PriorityPanel() {
  const priorities = usePriorities()
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState<Priority | null>(null)

  const patch = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<Priority> }) =>
      api<Priority>(`/admin/priorities/${id}`, { method: 'PATCH', json: changes }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['priorities'] })
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  const remove = useMutation({
    mutationFn: (priority: Priority) =>
      api<void>(`/admin/priorities/${priority.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['priorities'] })
      toast('Priority deleted', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  return (
    <Panel title="New priority" form={<PriorityCreateForm />}>
      {priorities.isPending && <SkeletonRows rows={4} />}
      <ul className="flex flex-col gap-8">
        {(priorities.data ?? []).map((priority) => (
          <li key={priority.id}>
            <Card className="flex flex-wrap items-center gap-16 p-16">
              <span
                aria-hidden
                className="rounded-pill size-[20px] shrink-0"
                style={{ backgroundColor: priority.color_hex }}
              />
              <div className="min-w-0 flex-1">
                <p className="text-body text-ink truncate font-medium">{priority.name}</p>
                <p className="text-body-sm text-muted">
                  Rank {priority.rank} — higher is more urgent
                </p>
              </div>
              {/* Native colour input: Doc 04 asks for a picker, the platform has one. */}
              <label className="flex items-center gap-8">
                <span className="text-body-sm text-muted">Colour</span>
                <input
                  type="color"
                  aria-label={`Colour for ${priority.name}`}
                  defaultValue={priority.color_hex}
                  onBlur={(e) =>
                    e.target.value.toLowerCase() !== priority.color_hex.toLowerCase() &&
                    patch.mutate({ id: priority.id, changes: { color_hex: e.target.value } })
                  }
                  className={cn('rounded-control h-[36px] w-[52px] bg-transparent', focusRing)}
                />
              </label>
              <Button size="sm" variant="ghost" onClick={() => setDeleting(priority)}>
                Delete
              </Button>
            </Card>
          </li>
        ))}
      </ul>

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this priority?"
        message="Only possible while no ticket, SLA rule or AI classification still references it."
        confirmLabel="Delete"
        destructive
      />
    </Panel>
  )
}

/** Exported for First-Time Admin Setup step 4 (App Flow §26). */
export function PriorityCreateForm() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [rank, setRank] = useState('3')
  const [color, setColor] = useState('#6366f1')

  const create = useMutation({
    mutationFn: () =>
      api<Priority>('/admin/priorities', {
        method: 'POST',
        json: { name: name.trim(), rank: Number(rank), color_hex: color },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['priorities'] })
      toast('Priority created', 'success')
      setName('')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create', 'error'),
  })

  return (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[200px] flex-1">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Low, Medium, High, Critical"
        />
      </div>
      <div className="w-[120px]">
        <Input
          label="Rank"
          type="number"
          min={1}
          max={100}
          value={rank}
          onChange={(e) => setRank(e.target.value)}
        />
      </div>
      <label className="flex flex-col gap-8">
        <span className="text-body-sm text-muted font-medium">Colour</span>
        <input
          type="color"
          value={color}
          onChange={(e) => setColor(e.target.value)}
          className={cn('rounded-control h-[44px] w-[64px] bg-transparent', focusRing)}
        />
      </label>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!name.trim() || create.isPending}
        onClick={() => create.mutate()}
      >
        Add priority
      </Button>
    </div>
  )
}

// --- Queues -----------------------------------------------------------------

function QueuePanel() {
  const queues = useQueues()
  const teams = useTeams()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [teamId, setTeamId] = useState('')
  const [deleting, setDeleting] = useState<Queue | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['queues'] })

  const create = useMutation({
    mutationFn: () =>
      api<Queue>('/admin/queues', {
        method: 'POST',
        json: { name: name.trim(), team_id: teamId || null },
      }),
    onSuccess: async () => {
      await invalidate()
      toast('Queue created', 'success')
      setName('')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create', 'error'),
  })

  const move = useMutation({
    mutationFn: ({ id, team }: { id: string; team: string | null }) =>
      api<Queue>(`/admin/queues/${id}`, { method: 'PATCH', json: { team_id: team } }),
    onSuccess: async () => {
      await invalidate()
      toast('Queue reassigned — visibility follows the team', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not reassign', 'error'),
  })

  const remove = useMutation({
    mutationFn: (queue: Queue) => api<void>(`/admin/queues/${queue.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await invalidate()
      toast('Queue deleted', 'success')
      setDeleting(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  const form = (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[240px] flex-1">
        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Match a top-level category name for auto-routing"
        />
      </div>
      <div className="min-w-[200px]">
        <Select label="Team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">No team</option>
          {(teams.data ?? []).map((team) => (
            <option key={team.id} value={team.id}>
              {team.name}
            </option>
          ))}
        </Select>
      </div>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!name.trim() || create.isPending}
        onClick={() => create.mutate()}
      >
        Add queue
      </Button>
    </div>
  )

  return (
    <Panel title="New queue" form={form}>
      <p className="text-body-sm text-muted mb-16">
        The routing agent matches a ticket to the queue whose name starts with its top-level
        category, falling back to the first queue — so naming these after your categories is what
        makes auto-routing land correctly.
      </p>
      {queues.isPending && <SkeletonRows rows={3} />}
      <ul className="flex flex-col gap-8">
        {(queues.data ?? []).map((queue) => (
          <li key={queue.id}>
            <Card className="flex flex-wrap items-center gap-16 p-16">
              <div className="min-w-0 flex-1">
                <p className="text-body text-ink truncate font-medium">{queue.name}</p>
              </div>
              <Select
                aria-label={`Team for ${queue.name}`}
                className="max-w-[220px]"
                value={queue.team_id ?? ''}
                onChange={(e) => move.mutate({ id: queue.id, team: e.target.value || null })}
              >
                <option value="">No team</option>
                {(teams.data ?? []).map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name}
                  </option>
                ))}
              </Select>
              <Button size="sm" variant="ghost" onClick={() => setDeleting(queue)}>
                Delete
              </Button>
            </Card>
          </li>
        ))}
      </ul>

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this queue?"
        message="Only possible while it holds no tickets."
        confirmLabel="Delete"
        destructive
      />
    </Panel>
  )
}

// --- Tags -------------------------------------------------------------------

function TagPanel() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const tags = useQuery({ queryKey: ['tags'], queryFn: () => api<Tag[]>('/tags') })

  const create = useMutation({
    mutationFn: () => api<Tag>('/tags', { method: 'POST', json: { name: name.trim() } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tags'] })
      toast('Tag created', 'success')
      setName('')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create', 'error'),
  })

  const form = (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[240px] flex-1">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!name.trim() || create.isPending}
        onClick={() => create.mutate()}
      >
        Add tag
      </Button>
    </div>
  )

  return (
    <Panel title="New tag" form={form}>
      {/* Tags have no delete endpoint — `ticket_tags` rows would be orphaned and
          Doc 05 has no cascade. Staff create them freely from a ticket, which is
          why this panel is a viewer with an add box rather than full CRUD. */}
      {tags.isPending && <SkeletonRows rows={2} />}
      {tags.isSuccess && tags.data.length === 0 && (
        <EmptyState icon={TagIcon} title="No tags yet" message="Agents add these from a ticket." />
      )}
      <div className="flex flex-wrap gap-8">
        {(tags.data ?? []).map((tag) => (
          <span key={tag.id} className="rounded-pill border-border text-body-sm border px-12 py-4">
            {tag.name}
          </span>
        ))}
      </div>
    </Panel>
  )
}

// --- Statuses ---------------------------------------------------------------

/**
 * Read-only, and deliberately so: Doc 05 has no `statuses` table and App Flow
 * §10's transitions are compiled into the workflow engine. Showing the machine
 * is more honest than an editor whose edits the engine would ignore.
 */
function StatusPanel() {
  return (
    <Card>
      <h2 className="text-h3 font-display font-semibold">Ticket statuses</h2>
      <p className="text-body-sm text-muted mt-8">
        Fixed vocabulary — the workflow engine enforces these transitions (App Flow §10) and rejects
        anything else, so they are shown here rather than edited.
      </p>
      <ul className="mt-24 flex flex-col gap-12">
        {TICKET_STATUSES.map((status) => {
          const next = nextStatuses(status as TicketStatus)
          return (
            <li
              key={status}
              className="border-border flex flex-wrap items-center gap-12 border-b py-12 last:border-b-0"
            >
              <StatusPill status={status} />
              <span className="text-body-sm text-muted">
                {next.length === 0
                  ? status === 'closed'
                    ? 'Terminal — reopening goes through its own endpoint'
                    : 'Terminal'
                  : `→ ${next.map(statusLabel).join(', ')}`}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
