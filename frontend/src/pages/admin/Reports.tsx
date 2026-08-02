import { ReportRunner } from '../../components/ReportRunner'

/** Every generator in `reporting/service.py`, org-wide because an Admin's
 *  ticket scope is unrestricted. */
const REPORTS = [
  { id: 'agent_productivity', label: 'Agent productivity' },
  { id: 'sla_compliance', label: 'SLA compliance' },
  { id: 'ticket_trends', label: 'Ticket trends' },
  { id: 'category_analytics', label: 'Category analytics' },
  { id: 'ai_performance', label: 'AI performance' },
  { id: 'ai_performance_trend', label: 'AI performance over time' },
]

/**
 * Reports & Analytics (Doc 03 §1, §23). The same `/reports/*` endpoints Team
 * Reports uses — org-wide is a property of who is asking, since
 * `scope_tickets_to_caller` returns everything for an Admin — with all three
 * export formats Doc 03 promises.
 */
export function AdminReports() {
  return (
    <div>
      <h1 className="text-h1 font-semibold">Reports &amp; Analytics</h1>
      <p className="text-body text-muted mt-8">
        Org-wide, across every team and queue. Generation runs in the background and the table fills
        in when it finishes.
      </p>
      <ReportRunner reports={REPORTS} formats={['csv', 'xlsx', 'pdf']} />
    </div>
  )
}
