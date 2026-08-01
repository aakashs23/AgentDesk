/**
 * Pure logic behind the chat widget (App Flow §12). Kept out of the components
 * so `npm run selfcheck` can assert it — the failure modes here are silent
 * ones: an "end chat" button offered before there is anything to raise a ticket
 * about, or a bot that keeps answering over an agent who has joined.
 */
// Explicit extension: `scripts/ui.selfcheck.ts` imports this module under
// Node's nodenext resolution, which requires one.
import type { ChatMessage } from './types.ts'

export type ChatPhase = 'greeting' | 'chatting' | 'with-agent' | 'converted'

const SESSION_KEY = 'agentdesk.chat-session'

/**
 * What the conversation is doing right now, which is what decides who replies
 * next and which controls the widget offers.
 */
export function chatPhase(messages: ChatMessage[], ticketId: string | null): ChatPhase {
  if (ticketId) return 'converted'
  if (messages.some((m) => m.speaker === 'agent')) return 'with-agent'
  return messages.some((m) => m.speaker === 'user') ? 'chatting' : 'greeting'
}

/**
 * §12 step 5 needs something to raise a ticket *about* — the API rejects a
 * conversation with no requester message, so the button is not offered either.
 */
export function canRaiseTicket(messages: ChatMessage[], ticketId: string | null): boolean {
  return !ticketId && messages.some((m) => m.speaker === 'user')
}

/** True while the bot is the one who answers — an agent takeover ends it. */
export function botIsAnswering(messages: ChatMessage[]): boolean {
  return !messages.some((m) => m.speaker === 'agent')
}

/**
 * The session id encodes its owner as `{user_id}:{uuid}` (see the backend's
 * `intake/chat_service.py`), so the console can label a waiting conversation
 * without a second request.
 */
export function requesterOf(sessionId: string): string {
  return sessionId.split(':')[0] ?? ''
}

/** Resume across a page reload; a converted or ended chat clears itself. */
export function storedSession(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function storeSession(sessionId: string | null): void {
  if (sessionId) localStorage.setItem(SESSION_KEY, sessionId)
  else localStorage.removeItem(SESSION_KEY)
}
