import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { PriorityPill } from '../../components/StatusPill'
import { AIDraftDrawer, AIInsightChip, DiffCallout } from '../../components/ai'
import { ApiError, api } from '../../lib/api'
import { TIER_COPY } from '../../lib/agent'
import { byId, useCategories, usePriorities, useTicketAi } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { AiClassification, AiDraft, Ticket } from '../../lib/types'
import { cn, focusRing, formatTicketId, relativeTime } from '../../lib/ui'

/**
 * The AI Insights tab (App Flow §14). Everything the model produced for this
 * ticket, plus the two human-in-the-loop controls the prototype makes
 * mandatory: confirm/correct the classification, and review the draft.
 *
 * The gradient appears here and nowhere else on the ticket — Doc 04's signature
 * rule is what tells an agent at a glance which parts a model wrote.
 */
export function AiInsightsTab({
  ticket,
  onOpenDraft,
}: {
  ticket: Ticket
  onOpenDraft: (draft: AiDraft) => void
}) {
  const insights = useTicketAi(ticket.id)

  if (insights.isPending) return <Skeleton className="h-[240px]" />
  if (insights.isError) {
    return (
      <ErrorState
        icon={AlertCircle}
        title="Couldn't load AI insights"
        onRetry={() => void insights.refetch()}
      />
    )
  }

  const { classification, drafts } = insights.data
  const pending = drafts.filter((d) => d.review_status === 'pending')
  const reviewed = drafts.filter((d) => d.review_status !== 'pending')

  if (!classification && drafts.length === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No AI output for this ticket"
        message="The pipeline either hasn't run yet or is disabled — classify and reply manually."
      />
    )
  }

  return (
    <div className="flex flex-col gap-24">
      {classification && <ClassificationPanel ticket={ticket} classification={classification} />}

      {pending.map((draft) => (
        <Card key={draft.id} className="flex flex-wrap items-center justify-between gap-16">
          <div>
            <p className="text-body text-ink font-medium">A reply is drafted and waiting</p>
            <p className="text-body-sm text-muted mt-4">
              Nothing is sent until you approve it — {relativeTime(draft.created_at)}.
            </p>
          </div>
          <Button variant="primary" onClick={() => onOpenDraft(draft)}>
            Review draft
          </Button>
        </Card>
      ))}

      {reviewed.length > 0 && (
        <div>
          <h3 className="text-caption text-muted tracking-wide uppercase">Reviewed drafts</h3>
          <ul className="mt-12 flex flex-col gap-8">
            {reviewed.map((draft) => (
              <li
                key={draft.id}
                className="rounded-control border-border flex items-center justify-between gap-12 border p-12"
              >
                <span className="text-body-sm text-muted truncate">
                  {draft.draft_content.slice(0, 80)}…
                </span>
                <span className="text-caption text-muted shrink-0 tracking-wide uppercase">
                  {draft.review_status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <SimilarTickets ticket={ticket} />
    </div>
  )
}

/** Predicted category/priority, the confidence score and tier, and the §14
 *  confirm/correct controls the medium and low tiers require. */
function ClassificationPanel({
  ticket,
  classification,
}: {
  ticket: Ticket
  classification: AiClassification
}) {
  const queryClient = useQueryClient()
  const categories = useCategories()
  const priorities = usePriorities()
  const categoryById = byId(categories.data)
  const priorityById = byId(priorities.data)

  const [categoryId, setCategoryId] = useState(
    classification.predicted_category_id ?? ticket.category_id ?? '',
  )
  const [priorityId, setPriorityId] = useState(
    classification.predicted_priority_id ?? ticket.priority_id ?? '',
  )

  const tier = TIER_COPY[classification.confidence_tier] ?? TIER_COPY.low
  const predictedCategory = classification.predicted_category_id
    ? categoryById.get(classification.predicted_category_id)?.name
    : null
  const currentCategory = ticket.category_id ? categoryById.get(ticket.category_id)?.name : null
  const predictedPriority = classification.predicted_priority_id
    ? priorityById.get(classification.predicted_priority_id)
    : undefined

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['ticket', ticket.id] }),
      queryClient.invalidateQueries({ queryKey: ['ticket-ai', ticket.id] }),
    ])
  }

  const confirm = useMutation({
    mutationFn: () =>
      api(`/tickets/${ticket.id}/classification/confirm`, { method: 'POST', json: {} }),
    onSuccess: async () => {
      await refresh()
      toast('Classification confirmed', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not confirm', 'error'),
  })

  const correct = useMutation({
    mutationFn: () =>
      api(`/tickets/${ticket.id}/classification/correct`, {
        method: 'POST',
        json: { category_id: categoryId || null, priority_id: priorityId || null },
      }),
    onSuccess: async () => {
      await refresh()
      // §14's feedback loop: the correction is stored against the classification
      // record as training feedback, which is worth telling the agent.
      toast('Correction saved as training feedback', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-16">
        <div>
          <h3 className="text-h3 font-display font-semibold">Classification</h3>
          <p className="text-body-sm text-muted mt-4">{tier.action}</p>
        </div>
        <AIInsightChip
          label={tier.label}
          // The pipeline stores 0–100; the chip renders a fraction as a percent.
          confidence={classification.confidence / 100}
        />
      </div>

      <div className="mt-24 flex flex-col gap-16">
        {predictedCategory && (
          <DiffCallout
            caption="Category"
            removed={
              currentCategory && currentCategory !== predictedCategory ? currentCategory : undefined
            }
            added={predictedCategory}
          />
        )}
        {predictedPriority && (
          <div className="flex items-center gap-12">
            <span className="text-caption text-muted tracking-wide uppercase">
              Predicted priority
            </span>
            <PriorityPill name={predictedPriority.name} colorHex={predictedPriority.color_hex} />
          </div>
        )}
        <p className="text-body-sm text-muted">
          Model {classification.model_version} · {relativeTime(classification.created_at)}
          {classification.was_overridden && ' · corrected by an agent'}
        </p>
      </div>

      {/* Doc 05 §6 keeps classification a staff field; this is where the agent
          exercises it. Confirm is only meaningful while nothing is overridden. */}
      <div className="border-border mt-24 grid gap-16 border-t pt-24 md:grid-cols-2">
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Category</span>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
              focusRing,
            )}
          >
            <option value="">Unclassified</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Priority</span>
          <select
            value={priorityId}
            onChange={(e) => setPriorityId(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
              focusRing,
            )}
          >
            <option value="">Unset</option>
            {(priorities.data ?? []).map((priority) => (
              <option key={priority.id} value={priority.id}>
                {priority.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-16 flex flex-wrap justify-end gap-8">
        {!classification.was_overridden && classification.predicted_category_id && (
          <Button size="sm" disabled={confirm.isPending} onClick={() => confirm.mutate()}>
            Confirm the AI's call
          </Button>
        )}
        <Button
          size="sm"
          variant="primary"
          disabled={correct.isPending}
          onClick={() => correct.mutate()}
        >
          Save correction
        </Button>
      </div>
    </Card>
  )
}

interface TicketHit {
  id: string
  display_id: number | null
  subject: string
  status: string
  score: number
}

/**
 * "Similar past tickets" (§14, Journey 2 step 2). Hybrid retrieval already
 * exists behind `/search/tickets`, so this reuses it with the ticket's own
 * subject as the query rather than adding a second similarity endpoint.
 */
function SimilarTickets({ ticket }: { ticket: Ticket }) {
  const similar = useQuery({
    queryKey: ['similar', ticket.id],
    queryFn: () =>
      api<{ tickets: TicketHit[] }>(
        `/search/tickets?q=${encodeURIComponent(ticket.subject)}&limit=6`,
      ).then((r) => r.tickets.filter((t) => t.id !== ticket.id).slice(0, 5)),
  })

  return (
    <div>
      <h3 className="text-caption text-muted tracking-wide uppercase">Similar past tickets</h3>
      {similar.isPending && <Skeleton className="mt-12 h-[64px]" />}
      {similar.isSuccess && similar.data.length === 0 && (
        <p className="text-body-sm text-muted mt-12">Nothing comparable in the archive.</p>
      )}
      <ul className="mt-12 flex flex-col gap-8">
        {(similar.data ?? []).map((hit) => (
          <li key={hit.id}>
            <Link
              to={`/agent/tickets/${hit.id}`}
              className={cn(
                'rounded-control border-border flex items-center justify-between gap-12 border p-12',
                'hover:bg-surface transition-colors duration-micro',
                focusRing,
              )}
            >
              <span className="text-body-sm text-ink truncate">{hit.subject}</span>
              <span className="text-data text-muted shrink-0 font-mono">
                {formatTicketId(hit.display_id)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * The AI Draft Response drawer (Journey 2 steps 3–4). Approve sends the draft
 * verbatim, Edit sends what the agent rewrote, Reject sends nothing and leaves
 * them to write the reply themselves — the mandatory human-in-the-loop gate.
 */
export function DraftDrawer({
  draft,
  ticketId,
  open,
  onClose,
}: {
  draft: AiDraft | null
  ticketId: string
  open: boolean
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')

  // Reload the model's text whenever a different draft is opened, so an
  // abandoned edit never leaks into the next review.
  useEffect(() => setBody(draft?.draft_content ?? ''), [draft])

  const review = useMutation({
    mutationFn: (action: 'approved' | 'edited' | 'rejected') =>
      api(`/ai/drafts/${draft!.id}/review`, {
        method: 'POST',
        json: { action, content: action === 'edited' ? body : null },
      }),
    onSuccess: async (_data, action) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['ticket-ai', ticketId] }),
        queryClient.invalidateQueries({ queryKey: ['comments', ticketId] }),
        queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] }),
      ])
      toast(action === 'rejected' ? 'Draft rejected' : 'Reply sent', 'success')
      onClose()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Review failed', 'error'),
  })

  const edited = draft ? body.trim() !== draft.draft_content.trim() : false

  return (
    <AIDraftDrawer
      open={open}
      onClose={onClose}
      footer={
        <>
          <Button
            variant="ghost"
            disabled={review.isPending}
            onClick={() => review.mutate('rejected')}
          >
            Reject
          </Button>
          <Button
            variant="primary"
            disabled={review.isPending || !body.trim()}
            onClick={() => review.mutate(edited ? 'edited' : 'approved')}
          >
            {edited ? 'Send edited reply' : 'Approve and send'}
          </Button>
        </>
      }
    >
      {draft && (
        <div className="flex flex-col gap-16">
          <p className="text-body-sm text-muted">
            Drafted by {draft.generated_by_model}
            {draft.confidence_score !== null &&
              ` · ${Math.round(draft.confidence_score)}% confidence`}
            . Edit it freely — sending records whether you approved it as-is or changed it.
          </p>

          <textarea
            rows={14}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-label="Draft reply"
            className={cn(
              'rounded-control border-border bg-canvas text-ink w-full border p-12',
              'focus:border-brand-start transition-colors duration-micro',
              focusRing,
            )}
          />

          {edited && (
            <p className="text-body-sm text-brand-start">
              Edited — this will be recorded as an edit, not an approval.
            </p>
          )}
        </div>
      )}
    </AIDraftDrawer>
  )
}
