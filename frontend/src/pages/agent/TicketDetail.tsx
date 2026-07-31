import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  Download,
  GitMerge,
  Lock,
  Paperclip,
  Sparkles,
  TrendingUp,
  UserPlus,
} from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { MentionTextarea } from '../../components/MentionTextarea'
import { Skeleton } from '../../components/Skeleton'
import { SlaScrubber } from '../../components/SlaScrubber'
import { PriorityPill, StatusPill } from '../../components/StatusPill'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import { useUser } from '../../lib/auth'
import {
  byId,
  useCategories,
  usePriorities,
  useStaffDirectory,
  useTicket,
  useTicketAi,
} from '../../lib/queries'
import { toast } from '../../lib/toast'
import type {
  AiDraft,
  Attachment,
  Comment,
  DirectoryUser,
  StatusHistoryEntry,
  Ticket,
} from '../../lib/types'
import { cn, focusRing, formatBytes, relativeTime, statusLabel } from '../../lib/ui'
import { AssignModal, EscalateModal, MergeModal, ReopenModal, StatusActions } from './actions'
import { AiInsightsTab, DraftDrawer } from './insights'

const TABS = [
  { id: 'conversation', label: 'Conversation' },
  { id: 'notes', label: 'Internal Notes' },
  { id: 'insights', label: 'AI Insights' },
  { id: 'attachments', label: 'Attachments' },
  { id: 'history', label: 'History' },
]

type ModalName = 'assign' | 'escalate' | 'merge' | 'reopen' | null

export function AgentTicketDetail() {
  const { ticketId } = useParams<{ ticketId: string }>()
  const [tab, setTab] = useState('conversation')
  const [modal, setModal] = useState<ModalName>(null)
  const [draft, setDraft] = useState<AiDraft | null>(null)

  const ticket = useTicket(ticketId)
  const categories = useCategories()
  const priorities = usePriorities()
  const staff = useStaffDirectory()
  const insights = useTicketAi(ticketId)

  if (ticket.isPending) {
    return (
      <div className="mx-auto flex max-w-[960px] flex-col gap-16">
        <Skeleton className="h-[32px] w-1/2" />
        <Skeleton className="h-[96px]" />
        <Skeleton className="h-[240px]" />
      </div>
    )
  }
  if (ticket.isError) {
    return (
      <ErrorState
        icon={AlertCircle}
        title="Couldn't load this ticket"
        onRetry={() => void ticket.refetch()}
      />
    )
  }

  const data = ticket.data
  const category = data.category_id ? byId(categories.data).get(data.category_id) : undefined
  const priority = data.priority_id ? byId(priorities.data).get(data.priority_id) : undefined
  const assignee = data.assignee_id ? byId(staff.data).get(data.assignee_id) : undefined
  const pendingDrafts = (insights.data?.drafts ?? []).filter((d) => d.review_status === 'pending')

  return (
    <div className="mx-auto max-w-[960px]">
      <Link
        to="/agent/queue"
        className={cn(
          'text-body-sm text-muted hover:text-ink inline-flex items-center gap-8',
          focusRing,
        )}
      >
        <ArrowLeft aria-hidden size={16} strokeWidth={1.5} />
        Ticket Queue
      </Link>

      <div className="mt-16 flex flex-wrap items-start justify-between gap-16">
        <div className="min-w-0">
          <h1 className="font-display text-h1 font-semibold">{data.subject}</h1>
          <p className="text-data text-muted mt-8 font-mono">{data.ref}</p>
        </div>
        <StatusPill status={data.status} />
      </div>

      {/* A waiting draft is the single most time-sensitive thing on this screen,
          so it sits above the fold rather than only inside the Insights tab. */}
      {pendingDrafts.length > 0 && (
        <button
          type="button"
          onClick={() => setDraft(pendingDrafts[0])}
          className={cn(
            'bg-linear-to-r from-brand-start to-brand-end rounded-card mt-24 flex w-full cursor-pointer items-center gap-12 px-24 py-16 text-left text-white',
            focusRing,
          )}
        >
          <Sparkles aria-hidden size={16} strokeWidth={1.5} />
          <span className="text-body flex-1 font-medium">
            AgentDesk drafted a reply — review before it can be sent
          </span>
          <span className="text-caption tracking-wide uppercase">Open draft</span>
        </button>
      )}

      {/* Doc 04's ticket-header metadata grid. */}
      <dl className="border-border mt-24 grid grid-cols-2 gap-16 border-y py-16 md:grid-cols-4">
        <Meta label="Status" value={statusLabel(data.status)} />
        <Meta
          label="Priority"
          value={
            priority ? <PriorityPill name={priority.name} colorHex={priority.color_hex} /> : 'Unset'
          }
        />
        <Meta label="Category" value={category?.name ?? 'Unclassified'} />
        <Meta
          label="Assignee"
          value={
            assignee ? (
              <span className="flex items-center gap-8">
                <Avatar name={assignee.full_name} seed={assignee.id} size="sm" />
                {assignee.full_name}
              </span>
            ) : data.assignee_id ? (
              // Assigned outside the caller's team directory — say so rather
              // than claiming the ticket has no owner.
              'Another team'
            ) : (
              'Unassigned'
            )
          }
        />
      </dl>

      <Card className="mt-24">
        <SlaScrubber ticket={data} />
      </Card>

      <div className="mt-24 flex flex-wrap items-center gap-8">
        <StatusActions ticket={data} />
        <Button
          size="sm"
          icon={<UserPlus size={16} strokeWidth={1.5} />}
          onClick={() => setModal('assign')}
        >
          {data.assignee_id ? 'Reassign' : 'Assign'}
        </Button>
        <Button
          size="sm"
          icon={<TrendingUp size={16} strokeWidth={1.5} />}
          onClick={() => setModal('escalate')}
        >
          Escalate
        </Button>
        <Button
          size="sm"
          icon={<GitMerge size={16} strokeWidth={1.5} />}
          onClick={() => setModal('merge')}
        >
          Merge
        </Button>
        {data.status === 'closed' && (
          <Button size="sm" onClick={() => setModal('reopen')}>
            Reopen
          </Button>
        )}
        {(data.status === 'resolved' || data.status === 'closed') && (
          <ReusableAction ticket={data} />
        )}
      </div>

      <div className="mt-24">
        <Tabs
          tabs={TABS.map((t) =>
            t.id === 'insights' && pendingDrafts.length > 0
              ? { ...t, badge: <span className="bg-brand-start size-[8px] rounded-pill" /> }
              : t,
          )}
          active={tab}
          onChange={setTab}
        />
      </div>

      <div className="mt-24">
        {tab === 'conversation' && (
          <Thread ticket={data} internal={false} staff={staff.data ?? []} />
        )}
        {tab === 'notes' && <Thread ticket={data} internal staff={staff.data ?? []} />}
        {tab === 'insights' && <AiInsightsTab ticket={data} onOpenDraft={setDraft} />}
        {tab === 'attachments' && <Attachments ticketId={data.id} />}
        {tab === 'history' && <ActivityFeed ticket={data} staff={staff.data ?? []} />}
      </div>

      <AssignModal ticket={data} open={modal === 'assign'} onClose={() => setModal(null)} />
      <EscalateModal ticket={data} open={modal === 'escalate'} onClose={() => setModal(null)} />
      <MergeModal ticket={data} open={modal === 'merge'} onClose={() => setModal(null)} />
      <ReopenModal ticket={data} open={modal === 'reopen'} onClose={() => setModal(null)} />
      <DraftDrawer
        draft={draft}
        ticketId={data.id}
        open={draft !== null}
        onClose={() => setDraft(null)}
      />
    </div>
  )
}

function Meta({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-caption text-muted tracking-wide uppercase">{label}</dt>
      <dd className="text-body text-ink mt-4">{value}</dd>
    </div>
  )
}

/** App Flow §19 step 2: the resolved-ticket prompt that seeds a KB draft. */
function ReusableAction({ ticket }: { ticket: Ticket }) {
  const navigate = useNavigate()
  return (
    <Button
      size="sm"
      icon={<BookOpen size={16} strokeWidth={1.5} />}
      onClick={() => navigate(`/agent/kb/new?ticket=${ticket.id}`)}
    >
      Flag as reusable
    </Button>
  )
}

/**
 * Conversation and Internal Notes are the same thread filtered two ways — the
 * `is_internal` flag is the only difference, so they share one component and
 * one composer rather than diverging over time.
 */
function Thread({
  ticket,
  internal,
  staff,
}: {
  ticket: Ticket
  internal: boolean
  staff: DirectoryUser[]
}) {
  const user = useUser()
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')
  const staffById = byId(staff)

  const comments = useQuery({
    queryKey: ['comments', ticket.id],
    queryFn: () => api<Comment[]>(`/tickets/${ticket.id}/comments`),
  })

  const post = useMutation({
    mutationFn: (text: string) =>
      api<Comment>(`/tickets/${ticket.id}/comments`, {
        method: 'POST',
        json: { body: text, is_internal: internal },
      }),
    onSuccess: async () => {
      setBody('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['comments', ticket.id] }),
        // A public staff reply moves open → in_progress server-side (§10).
        queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] }),
      ])
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not post', 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (body.trim()) post.mutate(body.trim())
  }

  const visible = (comments.data ?? []).filter((c) => c.is_internal === internal)

  return (
    <div className="flex flex-col gap-16">
      {!internal && (
        <Card>
          <div className="flex items-center gap-12">
            <Avatar name="Requester" seed={ticket.requester_id} size="sm" />
            <span className="text-body-sm text-ink font-medium">Requester</span>
            <time className="text-body-sm text-muted" dateTime={ticket.created_at}>
              {relativeTime(ticket.created_at)}
            </time>
          </div>
          <p className="text-body mt-12 whitespace-pre-wrap">{ticket.description}</p>
        </Card>
      )}

      {comments.isPending && <Skeleton className="h-[96px]" />}

      {comments.isSuccess && visible.length === 0 && (
        <p className="text-body text-muted py-24 text-center">
          {internal ? 'No internal notes yet.' : 'No replies yet.'}
        </p>
      )}

      {visible.map((comment) => {
        const author = comment.author_id ? staffById.get(comment.author_id) : undefined
        const mine = comment.author_id === user?.id
        const name = mine ? 'You' : (author?.full_name ?? 'Requester')
        return (
          <Card key={comment.id} className={cn(internal && 'border-dashed')}>
            <div className="flex flex-wrap items-center gap-12">
              <Avatar name={name} seed={comment.author_id ?? 'system'} size="sm" />
              <span className="text-body-sm text-ink font-medium">{name}</span>
              {/* An AI-authored reply keeps the gradient signature even after a
                  human approved it — the agent should still know where it came
                  from when re-reading the thread months later. */}
              {comment.is_ai_generated && <AiBadge />}
              {comment.is_internal && (
                <span className="text-caption text-muted inline-flex items-center gap-4 tracking-wide uppercase">
                  <Lock aria-hidden size={16} strokeWidth={1.5} />
                  Internal
                </span>
              )}
              <time className="text-body-sm text-muted" dateTime={comment.created_at}>
                {relativeTime(comment.created_at)}
              </time>
            </div>
            <p className="text-body mt-12 whitespace-pre-wrap">{comment.body}</p>
          </Card>
        )
      })}

      <form onSubmit={onSubmit} className="flex flex-col gap-8">
        <label htmlFor="composer" className="text-body-sm text-muted font-medium">
          {internal ? 'Add an internal note' : 'Reply to the requester'}
          {' — type @ to mention a teammate'}
        </label>
        <MentionTextarea
          id="composer"
          value={body}
          onChange={setBody}
          people={staff}
          placeholder={internal ? 'Only staff can read this…' : 'Your reply…'}
        />
        <div className="flex justify-end">
          <Button type="submit" variant="primary" disabled={!body.trim() || post.isPending}>
            {post.isPending ? 'Posting…' : internal ? 'Add note' : 'Send reply'}
          </Button>
        </div>
      </form>
    </div>
  )
}

function AiBadge() {
  return (
    <span className="rounded-pill bg-linear-to-r from-brand-start to-brand-end text-caption inline-flex items-center gap-4 px-12 py-4 font-medium tracking-wide text-white uppercase">
      <Sparkles aria-hidden size={16} strokeWidth={1.5} />
      AI-drafted
    </span>
  )
}

function Attachments({ ticketId }: { ticketId: string }) {
  const attachments = useQuery({
    queryKey: ['attachments', ticketId],
    queryFn: () => api<Attachment[]>(`/tickets/${ticketId}/attachments`),
  })

  if (attachments.isPending) return <Skeleton className="h-[64px]" />
  if (attachments.isError) {
    return (
      <ErrorState
        icon={AlertCircle}
        title="Couldn't load attachments"
        onRetry={() => void attachments.refetch()}
      />
    )
  }
  if (attachments.data.length === 0) return <EmptyState icon={Paperclip} title="No attachments" />

  return (
    <ul className="flex flex-col gap-8">
      {attachments.data.map((file) => (
        <li
          key={file.id}
          className="rounded-control border-border flex items-center gap-12 border p-12"
        >
          <Paperclip aria-hidden size={16} strokeWidth={1.5} className="text-muted shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-body-sm text-ink truncate">{file.file_name}</p>
            <p className="text-caption text-muted">{formatBytes(file.size_bytes)}</p>
          </div>
          <a
            href={`/api/v1/attachments/${file.id}`}
            download={file.file_name}
            aria-label={`Download ${file.file_name}`}
            className={cn('text-muted hover:text-ink', focusRing)}
          >
            <Download size={16} strokeWidth={1.5} />
          </a>
        </li>
      ))}
    </ul>
  )
}

// --- Activity feed ----------------------------------------------------------

type EntryKind = 'human' | 'ai' | 'system'

interface Entry {
  id: string
  at: string
  kind: EntryKind
  text: string
}

/**
 * Doc 04's role-coded activity feed: human actions flat, AI findings in the
 * gradient, system/automation events muted grey. One visual system, three
 * meanings.
 *
 * Assembled client-side from what the caller may already read. Status history
 * is Team Lead+ only (Doc 05 §6), so a plain Agent's feed is built from
 * comments and the ticket's own timestamps — narrower, never broken.
 */
function ActivityFeed({ ticket, staff }: { ticket: Ticket; staff: DirectoryUser[] }) {
  const user = useUser()
  const canReadHistory = user?.role === 'team_lead' || user?.role === 'admin'
  const staffById = byId(staff)

  const comments = useQuery({
    queryKey: ['comments', ticket.id],
    queryFn: () => api<Comment[]>(`/tickets/${ticket.id}/comments`),
  })
  const insights = useTicketAi(ticket.id)
  const history = useQuery({
    queryKey: ['status-history', ticket.id],
    enabled: canReadHistory,
    queryFn: () => api<StatusHistoryEntry[]>(`/tickets/${ticket.id}/status-history`),
  })

  const entries: Entry[] = [
    { id: 'created', at: ticket.created_at, kind: 'system' as EntryKind, text: 'Ticket created' },
    ...(history.data ?? []).map((row) => ({
      id: row.id,
      at: row.changed_at,
      // An unattributed change is the automation engine or the SLA monitor
      // acting, not a person — that distinction is the point of the colour code.
      kind: (row.changed_by ? 'human' : 'system') as EntryKind,
      text: `${statusLabel(row.old_status ?? 'new')} → ${statusLabel(row.new_status)}${
        row.changed_by ? ` by ${staffById.get(row.changed_by)?.full_name ?? 'a teammate'}` : ''
      }`,
    })),
    ...(comments.data ?? []).map((comment) => ({
      id: comment.id,
      at: comment.created_at,
      kind: (comment.is_ai_generated ? 'ai' : 'human') as EntryKind,
      text: comment.is_ai_generated
        ? 'AI-drafted reply sent after review'
        : comment.is_internal
          ? 'Internal note added'
          : 'Reply posted',
    })),
    ...(insights.data?.classification
      ? [
          {
            id: insights.data.classification.id,
            at: insights.data.classification.created_at,
            kind: 'ai' as EntryKind,
            text: `Classified with ${Math.round(insights.data.classification.confidence)}% confidence (${insights.data.classification.confidence_tier})`,
          },
        ]
      : []),
  ].sort((a, b) => Date.parse(a.at) - Date.parse(b.at))

  return (
    <>
      {!canReadHistory && (
        <p className="text-body-sm text-muted mb-16">
          Status-change history is visible to team leads; this feed shows the activity you can
          access.
        </p>
      )}
      <ol className="flex flex-col gap-12">
        {entries.map((entry) => (
          <li key={entry.id} className="flex items-start gap-12">
            <span
              aria-hidden
              className={cn(
                'rounded-pill mt-[6px] size-[8px] shrink-0',
                entry.kind === 'ai' && 'bg-linear-to-r from-brand-start to-brand-end',
                entry.kind === 'human' && 'bg-ink',
                entry.kind === 'system' && 'bg-muted',
              )}
            />
            <div className="min-w-0">
              <p
                className={cn(
                  'text-body-sm',
                  entry.kind === 'ai' && 'text-gradient font-medium',
                  entry.kind === 'human' && 'text-ink',
                  entry.kind === 'system' && 'text-muted',
                )}
              >
                {/* The label repeats what the colour says, because Doc 04
                    forbids colour as the only carrier of meaning. */}
                <span className="sr-only">
                  {entry.kind === 'ai' ? 'AI: ' : entry.kind === 'system' ? 'System: ' : ''}
                </span>
                {entry.text}
              </p>
              <time className="text-caption text-muted" dateTime={entry.at}>
                {relativeTime(entry.at)}
              </time>
            </div>
          </li>
        ))}
      </ol>
    </>
  )
}
