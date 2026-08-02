import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Users } from 'lucide-react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { ReportRunner } from '../../components/ReportRunner'
import { SkeletonRows } from '../../components/Skeleton'
import { api } from '../../lib/api'
import { chartAxis, chartCursor, chartGrid, chartTooltip } from '../../lib/charts'
import { formatDuration } from '../../lib/agent'
import type { DashboardMetrics } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'

/**
 * Team Workload (Doc 03 §1, Team Lead only). `/dashboard/metrics` is already
 * scoped to the caller's team by `scope_tickets_to_caller`, so this screen is a
 * presentation of that one call rather than a second team-aware endpoint.
 *
 * The route guard, not this component, is what stops a plain Agent reaching it
 * — and `navFor()` omits the sidebar item entirely (Doc 03 §9).
 */
export function TeamWorkload() {
  const metrics = useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: () => api<DashboardMetrics>('/dashboard/metrics'),
  })

  if (metrics.isPending) return <SkeletonRows rows={4} />
  if (metrics.isError) {
    return (
      <ErrorState
        icon={AlertCircle}
        title="Couldn't load team metrics"
        onRetry={() => void metrics.refetch()}
      />
    )
  }

  const { open_ticket_count, avg_resolution_seconds, sla_compliance_rate, agent_workload } =
    metrics.data

  return (
    <div>
      <h1 className="text-h1 font-semibold">Team Workload</h1>
      <p className="text-body text-muted mt-8">
        Open tickets per agent, for rebalancing before anything breaches.
      </p>

      {/* Doc 04's stat-callout row: large mono numbers, small caption below. */}
      <div className="mt-24 grid gap-16 md:grid-cols-3 md:gap-24">
        <Stat label="Open tickets" value={String(open_ticket_count)} />
        <Stat label="Avg. resolution" value={formatDuration(avg_resolution_seconds)} />
        <Stat
          label="SLA compliance"
          value={sla_compliance_rate === null ? '—' : `${Math.round(sla_compliance_rate * 100)}%`}
        />
      </div>

      <Card className="mt-24">
        <h2 className="text-h3 font-semibold">Open tickets by agent</h2>
        {agent_workload.length === 0 ? (
          <EmptyState icon={Users} title="Nothing assigned in your team right now" />
        ) : (
          <>
            <div className="mt-24 h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={agent_workload}>
                  <CartesianGrid {...chartGrid} />
                  <XAxis dataKey="full_name" {...chartAxis} />
                  <YAxis allowDecimals={false} {...chartAxis} />
                  <Tooltip cursor={chartCursor} {...chartTooltip} />
                  {/* Flat primary, never the AI violet — a workload count is a
                      database fact, not something a model produced. */}
                  <Bar dataKey="open_tickets" fill="var(--color-primary-fill)" radius={4} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* The chart is not the only way to read this (Doc 04 Accessibility). */}
            <ul className="mt-16 flex flex-col gap-8">
              {agent_workload.map((row) => (
                <li
                  key={row.assignee_id}
                  className="border-border flex items-center justify-between gap-12 border-b py-12"
                >
                  <Link
                    to={`/agent/queue?tab=team`}
                    className={cn('text-body text-ink hover:underline', focusRing)}
                  >
                    {row.full_name}
                  </Link>
                  <span className="text-data font-mono">{row.open_tickets} open</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <p className="text-h1 font-semibold tabular-nums">{value}</p>
      <p className="text-caption text-muted mt-4 tracking-wide uppercase">{label}</p>
    </Card>
  )
}

// --- Team Reports -----------------------------------------------------------

const REPORTS = [
  { id: 'agent_productivity', label: 'Agent productivity' },
  { id: 'sla_compliance', label: 'SLA compliance' },
  { id: 'ticket_trends', label: 'Ticket trends' },
  { id: 'category_analytics', label: 'Category analytics' },
]

/**
 * Team Reports (Doc 03 §23). Generation is asynchronous server-side, so
 * `ReportRunner` polls the report until it leaves `pending` — the same contract
 * Phase 8 built, surfaced rather than reimplemented. The Admin's Reports &
 * Analytics screen is the same component with more report types: the rows are
 * scoped by who is asking, not by which screen asked.
 */
export function TeamReports() {
  return (
    <div>
      <h1 className="text-h1 font-semibold">Team Reports</h1>
      <p className="text-body text-muted mt-8">
        Scoped to your team — resolution time and SLA compliance for the people you lead.
      </p>
      <ReportRunner reports={REPORTS} />
    </div>
  )
}
