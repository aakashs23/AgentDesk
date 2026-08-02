/**
 * Customer Portal chat widget (App Flow §12).
 *
 * A conversation first, a ticket only if self-service fails — the deflection
 * path the PRD lists as a Nice to Have. The bot greets, answers from the
 * knowledge base, and the requester decides: "that solved it" ends the chat as
 * a deflection, "talk to a person" converts the transcript into a ticket.
 *
 * Polling, not sockets: the transcript is re-read every few seconds while the
 * panel is open, which is how an agent's takeover messages (§12 step 7) appear.
 * ponytail: swap for SSE if the poll ever shows up in a profile.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookOpen, MessageCircle, Send, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { Button } from '../../components/Button'
import { useDialog } from '../../components/useDialog'
import { ApiError, api } from '../../lib/api'
import { botIsAnswering, canRaiseTicket, storeSession, storedSession } from '../../lib/chat'
import { toast } from '../../lib/toast'
import type { ChatMessage, ChatSession, ChatTurn, Ticket } from '../../lib/types'
import { cn, focusRing, tapTarget } from '../../lib/ui'

const POLL_MS = 5000

export function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(storedSession)
  const [draft, setDraft] = useState('')
  const [articles, setArticles] = useState<ChatTurn['articles']>([])
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const dialogRef = useDialog(open, () => setOpen(false))
  const endRef = useRef<HTMLDivElement>(null)

  const session = useQuery({
    queryKey: ['chat', sessionId],
    enabled: open && Boolean(sessionId),
    queryFn: () => api<ChatSession>(`/chat/sessions/${sessionId}`),
    // Only while a human might be typing on the other end; the bot's replies
    // arrive in the send response itself.
    refetchInterval: (query) =>
      query.state.data && botIsAnswering(query.state.data.messages) ? false : POLL_MS,
  })
  const messages = session.data?.messages ?? []
  const ticketId = session.data?.ticket_id ?? null

  // §12 steps 1–2: opening the widget starts the session and the bot greets.
  useEffect(() => {
    if (!open || sessionId) return
    let cancelled = false
    api<ChatSession>('/chat/sessions', { method: 'POST' })
      .then((created) => {
        if (cancelled) return
        storeSession(created.session_id)
        setSessionId(created.session_id)
        queryClient.setQueryData(['chat', created.session_id], created)
      })
      .catch(() => toast('Chat is unavailable right now.', 'error'))
    return () => {
      cancelled = true
    }
  }, [open, sessionId, queryClient])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length])

  const send = useMutation({
    mutationFn: (message: string) =>
      api<ChatTurn>(`/chat/sessions/${sessionId}/messages`, { method: 'POST', json: { message } }),
    onSuccess: (turn) => {
      setArticles(turn.articles)
      queryClient.setQueryData(['chat', sessionId], (current: ChatSession | undefined) =>
        current ? { ...current, messages: [...current.messages, ...turn.messages] } : current,
      )
    },
    onError: (error) =>
      toast(error instanceof ApiError ? error.message : 'Message not sent.', 'error'),
  })

  const end = useMutation({
    mutationFn: (resolved: boolean) =>
      api<Ticket | null>(`/chat/sessions/${sessionId}/end`, {
        method: 'POST',
        json: { resolved },
      }),
    onSuccess: (ticket) => {
      storeSession(null)
      setSessionId(null)
      setArticles([])
      setOpen(false)
      if (ticket) {
        void queryClient.invalidateQueries({ queryKey: ['tickets', 'mine'] })
        navigate(`/portal/tickets/${ticket.id}?created=1`)
      } else {
        toast('Glad we could help — chat closed.', 'success')
      }
    },
    onError: (error) =>
      toast(error instanceof ApiError ? error.message : 'Could not close the chat.', 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || send.isPending) return
    setDraft('')
    send.mutate(message)
  }

  return (
    <>
      {/* The launcher carries the AI violet because what it opens is the model —
          the signature rule, not decoration. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Chat with the AgentDesk assistant"
        className={cn(
          'bg-ai-fill shadow-card fixed right-16 z-40',
          'rounded-pill flex cursor-pointer items-center gap-8 px-16 text-white',
          'bottom-[88px] h-[52px] md:bottom-24', // above the mobile tab bar
          'transition-[filter] duration-button hover:brightness-108 active:brightness-95',
          open && 'hidden',
          focusRing,
        )}
      >
        <MessageCircle aria-hidden size={20} strokeWidth={1.5} />
        <span className="text-body font-medium">Ask AgentDesk</span>
      </button>

      <dialog
        ref={dialogRef}
        aria-label="AgentDesk assistant"
        className={cn(
          'border-border bg-elevated text-ink shadow-overlay border backdrop:bg-ink/60 backdrop:backdrop-blur-[4px]',
          'open:flex open:flex-col',
          // Bottom sheet on mobile, anchored panel on desktop (Doc 04 responsive).
          'mt-auto mb-0 ml-auto h-[80dvh] max-h-[80dvh] w-full max-w-full rounded-t-card',
          'md:rounded-card md:mr-24 md:mb-24 md:h-[560px] md:max-h-[80dvh] md:w-[400px]',
          'open:animate-[slide-in-bottom_var(--duration-drawer)_var(--ease-drawer)]',
        )}
      >
        <header className="bg-ai-tint text-ai border-divider flex items-center justify-between border-b px-16 py-12">
          <p className="text-caption flex items-center gap-8 font-medium tracking-wide uppercase">
            <Sparkles aria-hidden size={16} strokeWidth={1.5} />
            AgentDesk assistant
          </p>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close chat"
            className={cn('cursor-pointer rounded-[8px] p-4', focusRing)}
          >
            <X aria-hidden size={20} strokeWidth={1.5} />
          </button>
        </header>

        <div className="flex min-h-0 flex-1 flex-col gap-12 overflow-y-auto p-16">
          {messages.map((message) => (
            <Bubble key={message.id} message={message} />
          ))}
          {send.isPending && (
            <p role="status" className="text-body-sm text-muted ai-shimmer rounded-card p-12">
              Thinking…
            </p>
          )}
          {articles.length > 0 && (
            <div className="rounded-card border-border bg-surface flex flex-col gap-8 border p-12">
              <p className="text-caption text-muted flex items-center gap-8 tracking-wide uppercase">
                <BookOpen aria-hidden size={16} strokeWidth={1.5} />
                Suggested reading
              </p>
              {articles.map((article) => (
                <Link
                  key={article.id}
                  to={`/portal/kb/${article.id}`}
                  onClick={() => setOpen(false)}
                  className={cn(
                    'text-body-sm text-ink hover:text-primary underline underline-offset-4',
                    focusRing,
                  )}
                >
                  {article.title}
                </Link>
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-border flex flex-col gap-12 border-t p-16">
          {/* §12 steps 4–5: the two ways a conversation ends. */}
          {canRaiseTicket(messages, ticketId) && (
            <div className="flex gap-8">
              <Button
                size="sm"
                className="flex-1"
                disabled={end.isPending}
                onClick={() => end.mutate(true)}
              >
                That solved it
              </Button>
              <Button
                size="sm"
                variant="primary"
                className="flex-1"
                disabled={end.isPending}
                onClick={() => end.mutate(false)}
              >
                Talk to a person
              </Button>
            </div>
          )}
          <form onSubmit={onSubmit} className="flex items-end gap-8">
            <label htmlFor="chat-input" className="sr-only">
              Message
            </label>
            <input
              id="chat-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Describe your issue…"
              autoComplete="off"
              className={cn(
                'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] min-w-0 flex-1 border px-12',
                'placeholder:text-muted focus:border-primary transition-colors duration-micro',
                focusRing,
              )}
            />
            <Button
              type="submit"
              variant="primary"
              aria-label="Send message"
              disabled={!draft.trim() || send.isPending}
              className={tapTarget}
              icon={<Send aria-hidden size={18} strokeWidth={1.5} />}
            />
          </form>
        </div>
      </dialog>
    </>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.speaker === 'user'
  return (
    <div className={cn('flex', mine ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          // No gradient on either bubble: the requester's own words are not AI
          // output, and a gradient fill behind body copy is unreadable anyway.
          // The panel's gradient header carries the "this is the AI" signal.
          'rounded-card text-body max-w-[85%] px-12 py-8 whitespace-pre-wrap',
          mine ? 'bg-ink text-canvas' : 'border-border bg-surface border',
        )}
      >
        {!mine && (
          <p className="text-caption text-muted mb-4 flex items-center gap-4 tracking-wide uppercase">
            {message.speaker === 'bot' ? (
              <>
                <Sparkles aria-hidden size={14} strokeWidth={1.5} className="text-ai" />
                Assistant
              </>
            ) : (
              'Support agent'
            )}
          </p>
        )}
        {message.message}
      </div>
    </div>
  )
}
