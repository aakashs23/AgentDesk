import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, Download, Paperclip, Sparkles } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { PriorityPill, StatusPill } from '../../components/StatusPill'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { byId, useCategories, usePriorities, useTicket } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { Attachment, Comment, CsatResponse } from '../../lib/types'
import { cn, focusRing, formatBytes, relativeTime, statusLabel } from '../../lib/ui'
import { CsatModal } from './CsatModal'

// Doc 03 §2: requesters see Conversation and Attachments only — no Internal
// Notes, no AI Insights, no History.
const TABS = [
  { id: 'conversation', label: 'Conversation' },
  { id: 'attachments', label: 'Attachments' },
]

export function TicketDetail() {
  const { ticketId } = useParams<{ ticketId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const [tab, setTab] = useState('conversation')
  const [csatOpen, setCsatOpen] = useState(false)

  const ticket = useTicket(ticketId)
  const categories = useCategories()
  const priorities = usePriorities()

  // Was the requester just redirected here from the New Ticket form?
  const justCreated = searchParams.get('created') === '1'

  const comments = useQuery({
    queryKey: ['comments', ticketId],
    enabled: Boolean(ticketId),
    queryFn: () => api<Comment[]>(`/tickets/${ticketId}/comments`),
    // While the AI pipeline is still classifying, the ticket gains its category
    // and an acknowledgement shortly after creation — poll briefly so the page
    // fills in without the requester reloading.
    refetchInterval: justCreated ? 4000 : false,
  })

  const csat = useQuery({
    queryKey: ['csat', ticketId],
    enabled: Boolean(ticketId) && ticket.data?.status === 'resolved',
    queryFn: () => api<CsatResponse[]>(`/csat?ticket_id=${ticketId}`),
  })

  // Doc 03 §5 step 6: the survey appears on the next visit to a resolved ticket,
  // and only if it has not already been answered.
  useEffect(() => {
    if (ticket.data?.status === 'resolved' && csat.isSuccess && csat.data.length === 0) {
      setCsatOpen(true)
    }
  }, [ticket.data?.status, csat.isSuccess, csat.data])

  // Drop the ?created marker once the pipeline has produced something, so a
  // refresh later doesn't re-enter the polling state.
  useEffect(() => {
    if (justCreated && ticket.data && ticket.data.status !== 'new') {
      setSearchParams({}, { replace: true })
    }
  }, [justCreated, ticket.data, setSearchParams])

  if (ticket.isPending) return <DetailSkeleton />
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

  return (
    <div className="mx-auto max-w-[960px]">
      <Link
        to="/portal/tickets"
        className={cn(
          'text-body-sm text-muted hover:text-ink inline-flex items-center gap-8',
          focusRing,
        )}
      >
        <ArrowLeft aria-hidden size={16} strokeWidth={1.5} />
        My Tickets
      </Link>

      <div className="mt-16 flex flex-wrap items-start justify-between gap-16">
        <div>
          <h1 className="text-h1 font-semibold">{data.subject}</h1>
          <p className="text-data text-muted mt-8 font-mono">{data.ref}</p>
        </div>
        <StatusPill status={data.status} />
      </div>

      {justCreated && data.status === 'new' && <AiProcessingBanner />}

      {/* Doc 04's ticket-header metadata grid, label/value pairs. */}
      <dl className="border-border mt-24 grid grid-cols-2 gap-16 border-y py-16 md:grid-cols-4">
        <Meta label="Status" value={statusLabel(data.status)} />
        <Meta
          label="Priority"
          value={
            priority ? (
              <PriorityPill name={priority.name} colorHex={priority.color_hex} />
            ) : (
              'Being assessed'
            )
          }
        />
        <Meta label="Category" value={category?.name ?? 'Being assessed'} />
        <Meta
          label="Expected response"
          value={data.response_due_at ? relativeTime(data.response_due_at) : '—'}
        />
      </dl>

      <div className="mt-24">
        <Tabs tabs={TABS} active={tab} onChange={setTab} />
      </div>

      <div className="mt-24">
        {tab === 'conversation' && (
          <Conversation
            ticketId={data.id}
            description={data.description}
            createdAt={data.created_at}
            comments={comments}
            canReply={data.status !== 'closed'}
          />
        )}
        {tab === 'attachments' && <Attachments ticketId={data.id} />}
      </div>

      {data.status === 'closed' && <ReopenPanel ticketId={data.id} />}

      {ticketId && (
        <CsatModal open={csatOpen} onClose={() => setCsatOpen(false)} ticketId={ticketId} />
      )}
    </div>
  )
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-caption text-muted tracking-wide uppercase">{label}</dt>
      <dd className="text-body text-ink mt-4">{value}</dd>
    </div>
  )
}

/** Doc 03 §6: the AI-processing state shown right after submission. */
function AiProcessingBanner() {
  return (
    <div
      role="status"
      aria-live="polite"
      className="ai-shimmer rounded-card border-border mt-24 border p-16"
    >
      <p className="text-body flex items-center gap-8">
        <Sparkles aria-hidden size={16} strokeWidth={1.5} className="text-ai" />
        AgentDesk is reviewing your ticket and routing it to the right team.
      </p>
    </div>
  )
}

function Conversation({
  ticketId,
  description,
  createdAt,
  comments,
  canReply,
}: {
  ticketId: string
  description: string
  createdAt: string
  comments: ReturnType<typeof useQuery<Comment[]>>
  canReply: boolean
}) {
  const user = useUser()
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')

  const reply = useMutation({
    mutationFn: (text: string) =>
      api<Comment>(`/tickets/${ticketId}/comments`, {
        method: 'POST',
        json: { body: text, is_internal: false },
      }),
    onSuccess: async () => {
      setBody('')
      await queryClient.invalidateQueries({ queryKey: ['comments', ticketId] })
    },
    onError: (err) =>
      toast(err instanceof ApiError ? err.message : 'Could not post your reply', 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (body.trim()) reply.mutate(body.trim())
  }

  // Requesters never see internal notes; the API already filters them, this is
  // belt-and-braces so a backend change can't leak one into the portal.
  const visible = (comments.data ?? []).filter((c) => !c.is_internal)

  return (
    <div className="flex flex-col gap-16">
      {/* The original request reads as the first message in the thread. */}
      <Card>
        <div className="flex items-center gap-12">
          <Avatar name={user?.full_name ?? 'You'} seed={user?.id} size="sm" />
          <span className="text-body-sm text-ink font-medium">You</span>
          <time className="text-body-sm text-muted" dateTime={createdAt}>
            {relativeTime(createdAt)}
          </time>
        </div>
        <p className="text-body mt-12 whitespace-pre-wrap">{description}</p>
      </Card>

      {comments.isPending && <Skeleton className="h-[96px]" />}

      {comments.isSuccess && visible.length === 0 && (
        <p className="text-body text-muted py-24 text-center">No replies yet.</p>
      )}

      {visible.map((comment) => {
        const mine = comment.author_id === user?.id
        return (
          <Card key={comment.id}>
            <div className="flex items-center gap-12">
              <Avatar
                name={mine ? (user?.full_name ?? 'You') : 'Support Agent'}
                seed={comment.author_id ?? 'agent'}
                size="sm"
              />
              <span className="text-body-sm text-ink font-medium">
                {mine ? 'You' : 'Support Agent'}
              </span>
              <time className="text-body-sm text-muted" dateTime={comment.created_at}>
                {relativeTime(comment.created_at)}
              </time>
            </div>
            <p className="text-body mt-12 whitespace-pre-wrap">{comment.body}</p>
          </Card>
        )
      })}

      {canReply ? (
        <form onSubmit={onSubmit} className="flex flex-col gap-8">
          <label htmlFor="reply" className="text-body-sm text-muted font-medium">
            Add a reply
          </label>
          <textarea
            id="reply"
            rows={4}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary w-full border p-12',
              'placeholder:text-muted focus:border-primary transition-colors duration-micro',
              focusRing,
            )}
          />
          <div className="flex justify-end">
            <Button type="submit" variant="primary" disabled={!body.trim() || reply.isPending}>
              {reply.isPending ? 'Sending…' : 'Send reply'}
            </Button>
          </div>
        </form>
      ) : (
        <p className="text-body-sm text-muted">
          This ticket is closed. Reopen it below if you still need help.
        </p>
      )}
    </div>
  )
}

function Attachments({ ticketId }: { ticketId: string }) {
  // Attachments come back on the ticket's own listing endpoint; the portal only
  // reads them (upload happens at creation time, per Doc 03 §13).
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
  if (attachments.data.length === 0) {
    return <EmptyState icon={Paperclip} title="No attachments" />
  }

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

function ReopenPanel({ ticketId }: { ticketId: string }) {
  const queryClient = useQueryClient()
  const reopen = useMutation({
    mutationFn: () => api(`/tickets/${ticketId}/reopen`, { method: 'POST', json: {} }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
      toast('Ticket reopened', 'success')
    },
    onError: (err) =>
      toast(err instanceof ApiError ? err.message : 'Could not reopen this ticket', 'error'),
  })

  return (
    <Card className="mt-24 flex flex-wrap items-center justify-between gap-16">
      <div>
        <p className="text-body text-ink font-medium">Still having trouble?</p>
        <p className="text-body-sm text-muted mt-4">
          You can reopen this ticket for a short window after it was closed.
        </p>
      </div>
      <Button onClick={() => reopen.mutate()} disabled={reopen.isPending}>
        Reopen ticket
      </Button>
    </Card>
  )
}

function DetailSkeleton() {
  return (
    <div className="mx-auto flex max-w-[960px] flex-col gap-16">
      <Skeleton className="h-[32px] w-1/2" />
      <Skeleton className="h-[64px]" />
      <Skeleton className="h-[160px]" />
    </div>
  )
}
