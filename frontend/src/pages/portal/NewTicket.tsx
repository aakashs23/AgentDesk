import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { AttachmentPicker, type QueuedFile } from '../../components/AttachmentPicker'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Input } from '../../components/Input'
import { ApiError, api, uploadFile } from '../../lib/api'
import { validateFile } from '../../lib/attachments'
import { useDebounced } from '../../lib/hooks'
import { useCategories } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { KbArticleSummary, Ticket } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'

export function NewTicket() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const categories = useCategories()

  const [subject, setSubject] = useState('')
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [queued, setQueued] = useState<QueuedFile[]>([])
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  /** Set once the ticket exists; from then on failures are upload-only. */
  const [ticketId, setTicketId] = useState<string | null>(null)

  // Self-service deflection (PRD Nice to Have): suggest articles as they type.
  const suggestTerm = useDebounced(subject.trim(), 400)
  const suggestions = useQuery({
    queryKey: ['kb-suggest', suggestTerm],
    enabled: suggestTerm.length > 4,
    queryFn: () =>
      api<KbArticleSummary[]>(
        `/knowledge-base/articles?limit=3&q=${encodeURIComponent(suggestTerm)}`,
      ),
  })

  function addFiles(picked: File[]) {
    const accepted: QueuedFile[] = []
    for (const file of picked) {
      const problem = validateFile(file)
      if (problem) {
        // Doc 03 §13 steps 3/5: the file leaves the queue, the form is untouched.
        toast(problem, 'error')
        continue
      }
      accepted.push({
        key: crypto.randomUUID(),
        file,
        status: 'queued',
        progress: 0,
      })
    }
    setQueued((current) => [...current, ...accepted])
  }

  function patchFile(key: string, patch: Partial<QueuedFile>) {
    setQueued((current) => current.map((f) => (f.key === key ? { ...f, ...patch } : f)))
  }

  /** Uploads sequentially so a failure is attributable to one file. Returns the
   *  keys that failed, so the caller can decide whether to navigate away. */
  async function uploadAll(id: string, pending: QueuedFile[]): Promise<string[]> {
    const failed: string[] = []
    for (const item of pending) {
      patchFile(item.key, { status: 'uploading', progress: 0, error: undefined })
      try {
        await uploadFile(`/tickets/${id}/attachments`, item.file, (fraction) =>
          patchFile(item.key, { progress: fraction }),
        )
        patchFile(item.key, { status: 'done', progress: 1 })
      } catch (err) {
        failed.push(item.key)
        patchFile(item.key, {
          status: 'error',
          error: err instanceof ApiError ? err.message : 'Upload failed',
        })
      }
    }
    return failed
  }

  function finish(id: string) {
    void queryClient.invalidateQueries({ queryKey: ['tickets', 'mine'] })
    navigate(`/portal/tickets/${id}?created=1`, { replace: true })
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    setBusy(true)
    try {
      const ticket = await api<Ticket>('/tickets', {
        method: 'POST',
        json: {
          subject: subject.trim(),
          description: description.trim(),
          channel: 'portal',
          ...(categoryId ? { category_id: categoryId } : {}),
        },
      })
      setTicketId(ticket.id)

      // Attachments link to a ticket, so they upload once it exists
      // (Doc 03 §13 step 9).
      const failed = queued.length > 0 ? await uploadAll(ticket.id, queued) : []
      if (failed.length === 0) {
        finish(ticket.id)
        return
      }
      // The ticket is saved — don't discard it because a file failed. Doc 03 §13
      // asks for retry rather than a silent failure.
      setBusy(false)
      setSubmitError(
        `Your ticket was created, but ${failed.length} attachment${failed.length > 1 ? 's' : ''} failed to upload.`,
      )
    } catch (err) {
      setBusy(false)
      setSubmitError(
        err instanceof ApiError ? err.message : 'Could not submit your ticket. Please try again.',
      )
    }
  }

  async function retryFile(key: string) {
    if (!ticketId) return
    const item = queued.find((f) => f.key === key)
    if (!item) return
    const failed = await uploadAll(ticketId, [item])
    if (failed.length === 0 && queued.every((f) => f.key === key || f.status === 'done')) {
      finish(ticketId)
    }
  }

  // Doc 03 §6: the post-submit "AgentDesk is reviewing your ticket…" state.
  if (busy && !ticketId) return <ProcessingState />

  const canSubmit = subject.trim().length > 0 && description.trim().length > 0
  const ticketExists = ticketId !== null

  return (
    <div className="mx-auto max-w-[640px]">
      <h1 className="font-display text-h1 font-semibold">New Ticket</h1>
      <p className="text-body text-muted mt-8">
        Tell us what's going on and we'll route it to the right person.
      </p>

      <form onSubmit={onSubmit} className="mt-32 flex flex-col gap-16" noValidate>
        <Input
          label="Subject"
          required
          disabled={ticketExists}
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Short summary of the issue"
          validate={(v) => (v.trim() ? null : 'Please give your request a subject.')}
        />

        <div className="flex flex-col gap-8">
          <label htmlFor="description" className="text-body-sm text-muted font-medium">
            Description
          </label>
          <textarea
            id="description"
            required
            rows={6}
            disabled={ticketExists}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What happened, what you expected, and anything you've already tried"
            className={cn(
              'rounded-control border-border bg-canvas text-ink w-full border p-12',
              'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
              'disabled:cursor-not-allowed disabled:opacity-40',
              focusRing,
            )}
          />
        </div>

        {!ticketExists && suggestions.data && suggestions.data.length > 0 && (
          <KbSuggestions articles={suggestions.data} />
        )}

        <div className="flex flex-col gap-8">
          <label htmlFor="category" className="text-body-sm text-muted font-medium">
            Category (optional)
          </label>
          <select
            id="category"
            value={categoryId}
            disabled={ticketExists}
            onChange={(e) => setCategoryId(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
              'focus:border-brand-start transition-colors duration-micro',
              'disabled:cursor-not-allowed disabled:opacity-40',
              focusRing,
            )}
          >
            <option value="">Let AgentDesk decide</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          {/* Doc 03 §1 lists Priority on this form, but Doc 05 §6 makes priority a
              staff-only classification field and the AI pipeline assigns it — so
              it is reported here, not asked for. */}
          <p className="text-body-sm text-muted">
            Priority is set automatically during triage — leave the category blank if you're unsure.
          </p>
        </div>

        <AttachmentPicker
          files={queued}
          onAdd={addFiles}
          onRemove={(key) => setQueued((c) => c.filter((f) => f.key !== key))}
          onRetry={ticketExists ? retryFile : undefined}
          disabled={busy}
        />

        {submitError && (
          <p
            role="alert"
            className="rounded-control border-critical text-body-sm text-critical border p-12"
          >
            {submitError}
          </p>
        )}

        <div className="mt-16 flex justify-end gap-8">
          {ticketExists ? (
            <Button type="button" variant="primary" onClick={() => finish(ticketId)}>
              Continue to ticket
            </Button>
          ) : (
            <>
              <Button type="button" onClick={() => navigate('/portal/tickets')}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={!canSubmit || busy}>
                Submit ticket
              </Button>
            </>
          )}
        </div>
      </form>
    </div>
  )
}

function KbSuggestions({ articles }: { articles: KbArticleSummary[] }) {
  return (
    <Card className="flex flex-col gap-12">
      <p className="text-caption text-muted flex items-center gap-8 tracking-wide uppercase">
        <BookOpen aria-hidden size={16} strokeWidth={1.5} />
        These might already answer it
      </p>
      <ul className="flex flex-col gap-8">
        {articles.map((article) => (
          <li key={article.id}>
            <Link
              to={`/portal/kb/${article.id}`}
              className={cn(
                'text-body text-ink hover:text-brand-start underline underline-offset-4',
                focusRing,
              )}
            >
              {article.title}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/**
 * Doc 03 §5 step 3 / §6: a brief processing state while the AI pipeline runs
 * PII redaction, classification and routing. Uses the AI shimmer, not a
 * skeleton — this is "the model is thinking", not "data is loading".
 */
function ProcessingState() {
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center py-96 text-center">
      <div role="status" aria-live="polite" className="ai-shimmer rounded-card w-full p-32">
        <Sparkles aria-hidden size={24} strokeWidth={1.5} className="text-brand-start mx-auto" />
        <h1 className="font-display text-h2 mt-24 font-semibold">
          AgentDesk is reviewing your ticket…
        </h1>
        <p className="text-body text-muted mt-8">
          We're classifying it and finding the right person. This only takes a moment.
        </p>
      </div>
    </div>
  )
}
