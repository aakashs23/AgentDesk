import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Skeleton, SkeletonRows } from '../../components/Skeleton'
import { ApiError, api } from '../../lib/api'
import { formatDuration } from '../../lib/agent'
import { toast } from '../../lib/toast'
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
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Team Workload</h1>
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
        <h2 className="text-h3 font-display font-semibold">Open tickets by agent</h2>
        {agent_workload.length === 0 ? (
          <EmptyState icon={Users} title="Nothing assigned in your team right now" />
        ) : (
          <>
            <div className="mt-24 h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={agent_workload}>
                  <CartesianGrid stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="full_name"
                    tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
                    stroke="var(--color-border)"
                  />
                  <YAxis
                    allowDecimals={false}
                    tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
                    stroke="var(--color-border)"
                  />
                  <Tooltip
                    cursor={{ fill: 'var(--color-surface)' }}
                    contentStyle={{
                      background: 'var(--color-elevated)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-card)',
                      color: 'var(--color-ink)',
                    }}
                  />
                  {/* Flat brand-start fill, not the gradient — a workload count
                      is a database fact, not something a model produced. */}
                  <Bar dataKey="open_tickets" fill="var(--color-brand-start)" radius={4} />
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
      <p className="font-display text-h1 font-semibold tabular-nums">{value}</p>
      <p className="text-caption text-muted mt-4 tracking-wide uppercase">{label}</p>
    </Card>
  )
}

// --- Team Reports -----------------------------------------------------------

interface ReportOut {
  id: string
  report_type: string
  status: 'pending' | 'ready' | 'failed'
  columns: string[]
  rows: Record<string, unknown>[]
  error: string | null
}

const REPORTS = [
  { id: 'agent_productivity', label: 'Agent productivity' },
  { id: 'sla_compliance', label: 'SLA compliance' },
  { id: 'ticket_trends', label: 'Ticket trends' },
  { id: 'category_analytics', label: 'Category analytics' },
]

/**
 * Team Reports (Doc 03 §23). Generation is asynchronous server-side, so the
 * screen polls the report until it leaves `pending` — the same contract Phase 8
 * built, surfaced rather than reimplemented.
 */
export function TeamReports() {
  const [reportType, setReportType] = useState(REPORTS[0].id)
  const [reportId, setReportId] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      api<ReportOut>('/reports/generate', {
        method: 'POST',
        json: { report_type: reportType },
      }),
    onSuccess: (report) => setReportId(report.id),
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not start report', 'error'),
  })

  const report = useQuery({
    queryKey: ['report', reportId],
    enabled: Boolean(reportId),
    queryFn: () => api<ReportOut>(`/reports/${reportId}`),
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 1000 : false),
  })

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Team Reports</h1>
      <p className="text-body text-muted mt-8">
        Scoped to your team — resolution time and SLA compliance for the people you lead.
      </p>

      <div className="mt-24 flex flex-wrap items-end gap-16">
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Report</span>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] min-w-[240px] border px-12',
              focusRing,
            )}
          >
            {REPORTS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <Button variant="primary" disabled={generate.isPending} onClick={() => generate.mutate()}>
          Generate
        </Button>
        {report.data?.status === 'ready' && (
          <a
            href={`/api/v1/reports/${report.data.id}/export?format=csv`}
            download
            className={cn(
              'text-body-sm text-brand-start font-medium underline underline-offset-4',
              focusRing,
            )}
          >
            Export CSV
          </a>
        )}
      </div>

      <div className="mt-24">
        {report.data?.status === 'pending' && <Skeleton className="h-[160px]" />}

        {report.data?.status === 'failed' && (
          <ErrorState
            icon={AlertCircle}
            title={report.data.error ?? 'Report generation failed'}
            onRetry={() => generate.mutate()}
          />
        )}

        {report.data?.status === 'ready' && (
          // Doc 04 Responsive: wide data scrolls inside its own container so the
          // page body never scrolls sideways.
          <div className="border-border rounded-card overflow-x-auto border">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-border border-b">
                  {report.data.columns.map((column) => (
                    <th
                      key={column}
                      scope="col"
                      className="text-caption text-muted px-16 py-12 tracking-wide whitespace-nowrap uppercase"
                    >
                      {column.replaceAll('_', ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {report.data.rows.map((row, i) => (
                  <tr key={i} className="border-border border-b last:border-b-0">
                    {report.data!.columns.map((column) => (
                      <td key={column} className="text-body-sm px-16 py-12 whitespace-nowrap">
                        {String(row[column] ?? '—')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {report.data.rows.length === 0 && (
              <p className="text-body-sm text-muted px-16 py-24 text-center">
                No data in this period.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
