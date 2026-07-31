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

/** One `ai_classification_history` row — the AI Insights tab's whole payload. */
export interface AiClassification {
  id: string
  ticket_id: string
  predicted_category_id: string | null
  predicted_priority_id: string | null
  /** 0–100, as the pipeline stores it. */
  confidence: number
  confidence_tier: 'high' | 'medium' | 'low'
  model_version: string
  was_overridden: boolean
  corrected_category_id: string | null
  corrected_priority_id: string | null
  created_at: string
}

export interface AiDraft {
  id: string
  ticket_id: string
  generated_by_model: string
  draft_content: string
  confidence_score: number | null
  review_status: 'pending' | 'approved' | 'edited' | 'rejected'
  reviewed_by: string | null
  reviewed_at: string | null
  final_comment_id: string | null
  created_at: string
}

export interface AiInsights {
  classification: AiClassification | null
  drafts: AiDraft[]
}

export interface StatusHistoryEntry {
  id: string
  old_status: string | null
  new_status: string
  changed_by: string | null
  changed_at: string
}

export interface SavedView {
  id: string
  name: string
  filters: Record<string, unknown>
  created_at: string
}

/** `UserOut` — the staff directory behind assignment and @mention. */
export interface DirectoryUser {
  id: string
  email: string
  full_name: string
  role: string
  team_id: string | null
  is_active: boolean
}

export interface DashboardMetrics {
  open_ticket_count: number
  avg_resolution_seconds: number | null
  sla_compliance_rate: number | null
  agent_workload: { assignee_id: string; full_name: string; open_tickets: number }[]
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

// --- Admin configuration (Phase 12) ----------------------------------------

export interface Team {
  id: string
  name: string
  created_at: string
}

export interface Queue {
  id: string
  name: string
  team_id: string | null
  created_at: string
}

export interface Tag {
  id: string
  name: string
}

/** `sla_policies` — the API calls them rules, the table calls them policies. */
export interface SlaRule {
  id: string
  category_id: string | null
  priority_id: string
  response_minutes: number
  resolution_minutes: number
  created_at: string
  updated_at: string
}

export interface AutomationRule {
  id: string
  name: string
  trigger_type: string
  conditions: { field: string; op: string; value: string }[]
  actions: { type: string; [key: string]: unknown }[]
  priority: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AutomationLog {
  id: string
  automation_rule_id: string
  ticket_id: string | null
  execution_status: 'success' | 'failed' | 'skipped'
  execution_started_at: string
  execution_completed_at: string | null
  error_message: string | null
  created_at: string
}

export interface NotificationTemplate {
  id: string
  trigger_type: string
  channel: string
  subject_template: string | null
  body_template: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Webhook {
  id: string
  event_type: string
  target_url: string
  is_active: boolean
  created_at: string
  /** Returned once, by the create call only — never on a read. */
  secret?: string
}

export interface WebhookDelivery {
  id: string
  webhook_id: string
  event_type: string
  response_status: number | null
  attempt_count: number
  delivered_at: string | null
  created_at: string
}

export interface AuditLogEntry {
  id: string
  entity_type: string
  entity_id: string
  actor_id: string | null
  action: string
  before_state: Record<string, unknown> | null
  after_state: Record<string, unknown> | null
  created_at: string
}

/** A generated report, polled until it leaves `pending` (Doc 03 §23). */
export interface ReportOut {
  id: string
  report_type: string
  status: 'pending' | 'ready' | 'failed'
  columns: string[]
  rows: Record<string, unknown>[]
  error: string | null
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
