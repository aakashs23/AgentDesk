/**
 * The Admin Dashboard's pure decision logic, kept out of the components so
 * `npm run selfcheck` can assert it. Everything here is a function of its
 * arguments — no React, no fetch.
 */
// Explicit extension: `scripts/ui.selfcheck.ts` imports this module under
// Node's nodenext resolution, which requires one.
import type { Category } from './types.ts'

// --- Category tree (Doc 05: adjacency list, nested client-side) --------------

export interface CategoryNode extends Category {
  children: CategoryNode[]
  depth: number
}

/**
 * Nest the flat adjacency list `GET /categories` returns.
 *
 * A row whose `parent_id` points at something absent is treated as a root
 * rather than dropped: the Admin has to be able to see — and re-parent — a
 * category the API scoped away, otherwise it is invisible and un-fixable.
 */
export function buildCategoryTree(categories: Category[]): CategoryNode[] {
  const nodes = new Map<string, CategoryNode>(
    categories.map((c) => [c.id, { ...c, children: [], depth: 0 }]),
  )
  const roots: CategoryNode[] = []
  for (const node of nodes.values()) {
    const parent = node.parent_id ? nodes.get(node.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const stamp = (list: CategoryNode[], depth: number) => {
    list.sort((a, b) => a.name.localeCompare(b.name))
    for (const node of list) {
      node.depth = depth
      stamp(node.children, depth + 1)
    }
  }
  stamp(roots, 0)
  return roots
}

/** Depth-first flattening, so the tree renders as indented table rows. */
export function flattenTree(roots: CategoryNode[]): CategoryNode[] {
  return roots.flatMap((node) => [node, ...flattenTree(node.children)])
}

/**
 * Which categories may be a given category's parent. Its own subtree is
 * excluded — the API rejects a cycle with a 422, and offering the option only
 * to have it refused is a worse experience than not offering it.
 */
export function eligibleParents(roots: CategoryNode[], categoryId: string | null): CategoryNode[] {
  const banned = new Set<string>()
  if (categoryId) {
    const mark = (node: CategoryNode) => {
      banned.add(node.id)
      node.children.forEach(mark)
    }
    const find = (list: CategoryNode[]): CategoryNode | undefined =>
      list.find((n) => n.id === categoryId) ?? find(list.flatMap((n) => n.children))
    const self = find(roots)
    if (self) mark(self)
  }
  return flattenTree(roots).filter((node) => !banned.has(node.id))
}

// --- Ticket statuses (App Flow §10) -----------------------------------------

/**
 * Statuses are a fixed vocabulary owned by the workflow engine, not a
 * configurable table — Doc 05 has no `statuses` table, and every transition in
 * App Flow §10 is compiled into the engine. The Ticket Configuration screen
 * therefore *displays* them rather than editing them, which is what this list
 * is for.
 */
export const TICKET_STATUSES = [
  'new',
  'open',
  'in_progress',
  'on_hold',
  'resolved',
  'closed',
  'reopened',
] as const

// --- Automation builder vocabulary (mirrors app/workflow/automation.py) ------

export const TRIGGERS = [
  'ticket_created',
  'status_changed',
  'comment_added',
  'tag_added',
  'sla_warning',
  'sla_breached',
] as const

export const CONDITION_FIELDS = [
  'category_id',
  'priority_id',
  'queue_id',
  'assignee_id',
  'requester_id',
  'status',
  'channel',
  'subject',
  'description',
] as const

export const CONDITION_OPS = ['eq', 'ne', 'in', 'contains'] as const

export const ACTION_TYPES = ['assign', 'set_priority', 'add_tag', 'notify', 'escalate'] as const

export type ConditionField = (typeof CONDITION_FIELDS)[number]
export type ActionType = (typeof ACTION_TYPES)[number]

export interface RuleCondition {
  field: ConditionField
  op: (typeof CONDITION_OPS)[number]
  value: string
}

export interface RuleAction {
  type: ActionType
  [key: string]: unknown
}

/**
 * The extra key each action carries, matching `_execute_actions`'s dispatch.
 * `escalate` takes none — it routes to the team lead by itself.
 */
export const ACTION_PARAM: Record<ActionType, string | null> = {
  assign: 'assignee_id',
  set_priority: 'priority_id',
  add_tag: 'tag',
  notify: 'user_id',
  escalate: null,
}

/**
 * Why a draft rule is not savable yet, or null when it is. The API validates
 * all of this too; this only decides whether the Save button is live, so the
 * Admin finds out before the round trip rather than after it.
 */
export function ruleProblem(draft: {
  name: string
  trigger_type: string
  conditions: RuleCondition[]
  actions: RuleAction[]
}): string | null {
  if (!draft.name.trim()) return 'Give the rule a name'
  if (!TRIGGERS.includes(draft.trigger_type as (typeof TRIGGERS)[number])) {
    return 'Choose a trigger'
  }
  if (draft.conditions.some((c) => !String(c.value ?? '').trim())) {
    return 'Every condition needs a value'
  }
  if (draft.actions.length === 0) return 'A rule with no actions would do nothing'
  for (const action of draft.actions) {
    const param = ACTION_PARAM[action.type]
    if (param && !String(action[param] ?? '').trim()) {
      return `The ${action.type.replaceAll('_', ' ')} action is missing its target`
    }
  }
  return null
}

// --- Audit log (Doc 03 §1: "searchable log of ticket and admin changes") -----

export interface AuditEntry {
  entity_type: string
  action: string
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
}

/**
 * One line describing what actually changed, built by diffing the two JSONB
 * states. A raw before/after dump is unreadable at 50 rows a page, and the
 * fields that did *not* change are exactly the noise.
 */
export function describeChange(entry: AuditEntry): string {
  const before = entry.before_state ?? {}
  const after = entry.after_state ?? {}
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])]
  const changed = keys.filter((k) => String(before[k] ?? '') !== String(after[k] ?? ''))
  if (changed.length === 0) return '—'
  return changed
    .map((key) => {
      const from = before[key]
      const to = after[key]
      const label = key.replaceAll('_', ' ')
      if (from === undefined || from === null) return `${label} → ${to}`
      if (to === undefined || to === null) return `${label} was ${from}`
      return `${label}: ${from} → ${to}`
    })
    .join(', ')
}

// --- First-Time Admin Setup (App Flow §26) ----------------------------------

export interface SetupCounts {
  teams: number
  categories: number
  priorities: number
  slaRules: number
  staff: number
}

export interface SetupStep {
  id: keyof SetupCounts
  label: string
  done: boolean
  /** §26 step 6: automation rules can be skipped and added later. */
  optional?: boolean
}

/**
 * The §26 checklist. Step order is the document's, and each step is "done" once
 * the thing it creates exists — so an Admin who configured half the system in a
 * previous session resumes where they stopped rather than starting over.
 */
export function setupSteps(counts: SetupCounts): SetupStep[] {
  return [
    { id: 'teams', label: 'Create teams', done: counts.teams > 0 },
    {
      id: 'categories',
      label: 'Create categories and sub-categories',
      done: counts.categories > 0,
    },
    { id: 'priorities', label: 'Configure priorities', done: counts.priorities > 0 },
    { id: 'slaRules', label: 'Configure SLA rules', done: counts.slaRules > 0 },
    { id: 'staff', label: 'Invite agents and team leads', done: counts.staff > 0 },
  ]
}

/**
 * Whether the system is configured enough for the Customer Portal to be usable
 * (§26 step 8, "System Ready"). Deliberately not "every step done": inviting
 * staff can wait, but a ticket submitted with no category and no SLA policy
 * gets no deadline and no queue.
 */
export function isSystemReady(counts: SetupCounts): boolean {
  return counts.teams > 0 && counts.categories > 0 && counts.priorities > 0 && counts.slaRules > 0
}

/** Percentage complete, for the wizard's progress bar. */
export function setupProgress(counts: SetupCounts): number {
  const steps = setupSteps(counts)
  return Math.round((steps.filter((s) => s.done).length / steps.length) * 100)
}

// --- Formatting -------------------------------------------------------------

/** `sla_policies` stores minutes; an Admin thinks in hours past about 90. */
export function formatMinutes(minutes: number): string {
  if (minutes < 90) return `${minutes}m`
  const hours = minutes / 60
  if (hours < 48) return Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
  const days = hours / 24
  return Number.isInteger(days) ? `${days}d` : `${days.toFixed(1)}d`
}

/** A 0–1 rate as a percentage, or an em dash when there was nothing to measure. */
export function formatRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%`
}

/** snake_case API vocabulary → the sentence case the screens display. */
export function humanise(value: string): string {
  const spaced = value.replaceAll('_', ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
