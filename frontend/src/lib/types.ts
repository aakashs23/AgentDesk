/** Response shapes mirroring the FastAPI schemas. Kept hand-written and small:
 *  only the fields the UI actually reads, so a backend addition never forces a
 *  frontend edit. */

export interface Ticket {
  id: string
  display_id: number
  /** Server-formatted `AGT-1042` (Doc 05: display_id is formatted app-side). */
  ref: string
  subject: string
  description: string
  requester_id: string
  assignee_id: string | null
  category_id: string | null
  priority_id: string | null
  status: TicketStatus
  channel: string
  response_due_at: string | null
  resolution_due_at: string | null
  resolved_at: string | null
  closed_at: string | null
  reopened_count: number
  created_at: string
  updated_at: string
}

export type TicketStatus =
  'new' | 'open' | 'in_progress' | 'on_hold' | 'resolved' | 'closed' | 'reopened'

export interface Comment {
  id: string
  ticket_id: string
  author_id: string | null
  body: string
  is_internal: boolean
  is_ai_generated: boolean
  created_at: string
  updated_at: string | null
}

export interface Attachment {
  id: string
  ticket_id: string
  file_name: string
  mime_type: string
  size_bytes: number
  created_at: string
}

export interface Category {
  id: string
  name: string
  parent_id: string | null
}

export interface Priority {
  id: string
  name: string
  rank: number
  color_hex: string
}

export interface KbArticleSummary {
  id: string
  title: string
  category_id: string | null
  status: string
  published_at: string | null
  updated_at: string
}

export interface KbArticle extends KbArticleSummary {
  body: string
  source_ticket_id: string | null
  author_id: string | null
  created_at: string
}

export interface Notification {
  id: string
  ticket_id: string | null
  trigger_type: string
  channel: string
  is_read: boolean
  payload: Record<string, unknown> | null
  created_at: string
}

export interface CsatResponse {
  id: string
  ticket_id: string
  rating: number
  comment: string | null
  submitted_at: string
}

/** Per-trigger, per-channel notification preferences (Doc 05 users table). */
export const NOTIFICATION_TRIGGERS = [
  'ticket_assigned',
  'ticket_replied',
  'status_changed',
  'sla_warning',
  'sla_breached',
  'escalation',
  'mention',
  'ticket_closed',
  'automation_executed',
] as const

export type NotificationTrigger = (typeof NOTIFICATION_TRIGGERS)[number]
