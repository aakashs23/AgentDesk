import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowRight, Bot, Users } from 'lucide-react'
import { Link } from 'react-router'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { AIInsightChip } from '../../components/ai'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { SkeletonRows } from '../../components/Skeleton'
import { api } from '../../lib/api'
import { chartAxis, chartCursor, chartGrid, chartTooltip } from '../../lib/charts'
import { formatDuration } from '../../lib/agent'
import { formatRate } from '../../lib/admin'
import type { DashboardMetrics, ReportOut } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'
import { SetupBanner } from './Setup'

/**
 * Admin Overview (Doc 03 §1) — the org-wide read of the same
 * `/dashboard/metrics` the Team Lead sees, unscoped because
 * `scope_tickets_to_caller` returns `true` for an Admin.
 *
 * The AI snapshot on the right is the one place on this screen carrying the AI
 * violet: it means "a model produced this", and an open-ticket count did not.
 */
export function AdminOverview() {
  const metrics = useQuery({
    queryKey: ['dashboard-metrics'],
    queryFn: () => api<DashboardMetrics>('/dashboard/metrics'),
  })

  return (
    <div>
      <h1 className="text-h1 font-semibold">Overview</h1>
      <p className="text-body text-muted mt-8">
        Everything across the organisation — every queue, every team.
      </p>

      {/* App Flow §26: an unconfigured deployment cannot take tickets, so the
          checklist outranks the metrics until it is done. */}
      <SetupBanner />

      {metrics.isPending && <SkeletonRows rows={4} />}
      {metrics.isError && (
        <ErrorState
          icon={AlertCircle}
          title="Couldn't load org metrics"
          onRetry={() => void metrics.refetch()}
        />
      )}

      {metrics.isSuccess && (
        <>
          <div className="mt-24 grid gap-16 md:grid-cols-3 md:gap-24">
            <Stat label="Open tickets" value={String(metrics.data.open_ticket_count)} />
            <Stat
              label="Avg. resolution"
              value={formatDuration(metrics.data.avg_resolution_seconds)}
            />
            <Stat
              label="SLA compliance"
              value={formatRate(metrics.data.sla_compliance_rate)}
              to="/admin/sla"
            />
          </div>

          <div className="mt-24 grid gap-24 lg:grid-cols-[2fr_1fr]">
            <Workload rows={metrics.data.agent_workload} />
            <AiSnapshot />
          </div>
        </>
      )}
    </div>
  )
}

/** Doc 04's stat-callout: large display number, small uppercase caption. */
function Stat({ label, value, to }: { label: string; value: string; to?: string }) {
  const body = (
    <>
      <p className="text-h1 font-semibold tabular-nums">{value}</p>
      <p className="text-caption text-muted mt-4 tracking-wide uppercase">{label}</p>
    </>
  )
  if (!to) return <Card>{body}</Card>
  return (
    <Card interactive className="p-0">
      <Link to={to} className={cn('block p-24', focusRing)}>
        {body}
      </Link>
    </Card>
  )
}

function Workload({ rows }: { rows: DashboardMetrics['agent_workload'] }) {
  return (
    <Card>
      <h2 className="text-h3 font-semibold">Open tickets by agent</h2>
      {rows.length === 0 ? (
        <EmptyState icon={Users} title="Nothing assigned anywhere right now" />
      ) : (
        <>
          <div className="mt-24 h-[280px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows}>
                <CartesianGrid {...chartGrid} />
                <XAxis dataKey="full_name" {...chartAxis} />
                <YAxis allowDecimals={false} {...chartAxis} />
                <Tooltip cursor={chartCursor} {...chartTooltip} />
                <Bar dataKey="open_tickets" fill="var(--color-primary-fill)" radius={4} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* The chart is not the only way to read this (Doc 04 Accessibility). */}
          <ul className="mt-16 flex flex-col gap-8">
            {rows.map((row) => (
              <li
                key={row.assignee_id}
                className="border-border flex items-center justify-between gap-12 border-b py-12 last:border-b-0"
              >
                <span className="text-body">{row.full_name}</span>
                <span className="text-data font-mono">{row.open_tickets} open</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

/** Reads the same `ai_performance` report the AI Performance Monitor does, so
 *  the snapshot and the full screen can never disagree. */
function AiSnapshot() {
  const snapshot = useQuery({
    queryKey: ['ai-snapshot'],
    queryFn: async () => {
      const started = await api<ReportOut>('/reports/generate', {
        method: 'POST',
        json: { report_type: 'ai_performance' },
      })
      return api<ReportOut>(`/reports/${started.id}`)
    },
    // Generation is a background task; one retry covers the race where the poll
    // lands before the generator has written its rows.
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 800 : false),
  })

  const value = (metric: string) =>
    snapshot.data?.rows.find((row) => row.metric === metric)?.value ?? null

  return (
    <Card>
      <div className="flex items-center justify-between gap-12">
        <h2 className="text-h3 font-semibold">AI performance</h2>
        <Link
          to="/admin/ai"
          className={cn(
            'text-body-sm text-primary inline-flex items-center gap-4 font-medium',
            focusRing,
          )}
        >
          Full monitor
          <ArrowRight size={14} strokeWidth={1.5} aria-hidden />
        </Link>
      </div>

      {snapshot.data?.status !== 'ready' ? (
        <SkeletonRows rows={3} />
      ) : Number(value('classifications_total')) === 0 ? (
        <EmptyState
          icon={Bot}
          title="No classifications yet"
          message="The pipeline records its accuracy as tickets arrive."
        />
      ) : (
        <div className="mt-16 flex flex-col gap-16">
          <AIInsightChip
            label="Classification accuracy"
            confidence={Number(value('classification_accuracy')) * 100}
          />
          <Metric
            label="Auto-routing accepted"
            value={formatRate(value('auto_routing_acceptance_rate') as number | null)}
          />
          <Metric
            label="Drafts approved or edited"
            value={formatRate(value('draft_approval_rate') as number | null)}
          />
          <Metric label="Classifications" value={String(value('classifications_total') ?? 0)} />
        </div>
      )}
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-12">
      <span className="text-body-sm text-muted">{label}</span>
      <span className="text-data font-mono tabular-nums">{value}</span>
    </div>
  )
}
