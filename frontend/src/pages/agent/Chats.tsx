/**
 * Live Chats — human takeover (App Flow §12 step 7).
 *
 * Lists conversations that are still live and have not become tickets, and
 * lets an agent join one. Joining is just posting a message: the backend marks
 * the speaker `agent` from the caller's role and stands the bot down from then
 * on, so there is no separate "claim" state to keep in sync.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageCircle, Send } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { Skeleton } from '../../components/Skeleton'
import { ApiError, api } from '../../lib/api'
import { chatPhase } from '../../lib/chat'
import { toast } from '../../lib/toast'
import type { ChatSession, ChatSessionSummary, ChatTurn } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

const POLL_MS = 5000

export function LiveChats() {
  const [selected, setSelected] = useState<string | null>(null)

  const sessions = useQuery({
    queryKey: ['chat-sessions'],
    queryFn: () => api<ChatSessionSummary[]>('/chat/sessions'),
    refetchInterval: POLL_MS,
  })

  return (
    <div className="flex flex-col gap-24">
      <div>
        <h1 className="font-display text-h1 font-semibold">Live Chats</h1>
        <p className="text-body text-muted mt-8">
          Conversations still open in the portal widget. Joining one takes it off the assistant.
        </p>
      </div>

      {sessions.isLoading && <Skeleton className="h-[120px]" />}
      {sessions.data?.length === 0 && (
        <EmptyState
          icon={MessageCircle}
          title="No live conversations"
          message="Chats appear here while a requester is still typing in the widget."
        />
      )}

      <div className="grid gap-16 lg:grid-cols-[320px_1fr]">
        <ul className="flex flex-col gap-8">
          {(sessions.data ?? []).map((session) => (
            <li key={session.session_id}>
              <button
                type="button"
                onClick={() => setSelected(session.session_id)}
                className={cn(
                  'rounded-card border-border w-full cursor-pointer border p-12 text-left',
                  'transition-colors duration-micro hover:border-brand-start',
                  selected === session.session_id && 'border-brand-start bg-surface',
                  focusRing,
                )}
              >
                <p className="text-body font-medium">
                  {session.agent_joined ? 'With an agent' : 'Waiting on the assistant'}
                </p>
                <p className="text-body-sm text-muted mt-4">
                  {session.message_count} messages · {relativeTime(session.last_message_at)}
                </p>
              </button>
            </li>
          ))}
        </ul>

        {selected && <Conversation sessionId={selected} />}
      </div>
    </div>
  )
}

function Conversation({ sessionId }: { sessionId: string }) {
  const [draft, setDraft] = useState('')
  const queryClient = useQueryClient()

  const session = useQuery({
    queryKey: ['chat', sessionId],
    queryFn: () => api<ChatSession>(`/chat/sessions/${sessionId}`),
    refetchInterval: POLL_MS,
  })
  const messages = session.data?.messages ?? []

  const send = useMutation({
    mutationFn: (message: string) =>
      api<ChatTurn>(`/chat/sessions/${sessionId}/messages`, { method: 'POST', json: { message } }),
    onSuccess: (turn) => {
      queryClient.setQueryData(['chat', sessionId], (current: ChatSession | undefined) =>
        current ? { ...current, messages: [...current.messages, ...turn.messages] } : current,
      )
      void queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
    },
    onError: (error) =>
      toast(error instanceof ApiError ? error.message : 'Message not sent.', 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const message = draft.trim()
    if (!message || send.isPending) return
    setDraft('')
    send.mutate(message)
  }

  const phase = chatPhase(messages, session.data?.ticket_id ?? null)

  return (
    <Card className="flex flex-col gap-12">
      <p className="text-caption text-muted tracking-wide uppercase">
        {phase === 'with-agent' ? 'An agent has joined' : 'The assistant is handling this'}
      </p>
      <div className="flex max-h-[420px] flex-col gap-8 overflow-y-auto">
        {messages.map((message) => (
          <div key={message.id} className="rounded-card border-border bg-surface border p-12">
            <p className="text-caption text-muted mb-4 tracking-wide uppercase">
              {message.speaker === 'user'
                ? 'Requester'
                : message.speaker === 'bot'
                  ? 'Assistant'
                  : 'Agent'}
            </p>
            <p className="text-body whitespace-pre-wrap">{message.message}</p>
          </div>
        ))}
      </div>
      <form onSubmit={onSubmit} className="flex items-end gap-8">
        <label htmlFor="agent-chat-input" className="sr-only">
          Reply to the requester
        </label>
        <input
          id="agent-chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={phase === 'with-agent' ? 'Reply…' : 'Join this conversation…'}
          autoComplete="off"
          className={cn(
            'rounded-control border-border bg-canvas text-ink h-[44px] min-w-0 flex-1 border px-12',
            'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
            focusRing,
          )}
        />
        <Button
          type="submit"
          variant="primary"
          aria-label="Send reply"
          disabled={!draft.trim() || send.isPending}
          icon={<Send aria-hidden size={18} strokeWidth={1.5} />}
        />
      </form>
    </Card>
  )
}
