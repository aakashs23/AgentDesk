import { useQuery } from '@tanstack/react-query'
import { Bot } from 'lucide-react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AIInsightChip } from '../../components/ai'
import { Card } from '../../components/Card'
import { EmptyState } from '../../components/EmptyState'
import { ReportRunner } from '../../components/ReportRunner'
import { SkeletonRows } from '../../components/Skeleton'
import { api } from '../../lib/api'
import { chartAxis, chartGrid, chartLegend, chartTooltip } from '../../lib/charts'
import { formatRate } from '../../lib/admin'
import type { ReportOut } from '../../lib/types'

const TREND_REPORTS = [{ id: 'ai_performance_trend', label: 'AI performance over time' }]

/**
 * AI Performance Monitor (Doc 03 §1) — AgentDesk's AI-first differentiator, so
 * this is the one screen where the brand gradient carries meaning throughout:
 * every number on it came out of a model.
 *
 * Both halves read the report generators Phase 8 built, not a bespoke endpoint,
 * so these figures cannot drift from what Reports & Analytics exports.
 */
export function AiPerformance() {
  return (
    <div>
      <h1 className="text-h1 font-semibold">AI Performance</h1>
      <p className="text-body text-muted mt-8">
        Classification accuracy, auto-routing acceptance and draft approval — the three places a
        human overrules the pipeline.
      </p>

      <Headline />

      <Card className="mt-24">
        <h2 className="text-h3 font-semibold">Over time</h2>
        <p className="text-body-sm text-muted mt-8">
          A falling acceptance rate means agents are correcting the model more often than they were.
        </p>
        <ReportRunner reports={TREND_REPORTS} formats={['csv', 'xlsx']}>
          {(report) => <TrendChart report={report} />}
        </ReportRunner>
      </Card>
    </div>
  )
}

/** The lifetime numbers, generated on mount rather than behind a button — this
 *  is the headline of the screen, not something to ask for. */
function Headline() {
  const snapshot = useQuery({
    queryKey: ['ai-performance'],
    queryFn: async () => {
      const started = await api<ReportOut>('/reports/generate', {
        method: 'POST',
        json: { report_type: 'ai_performance' },
      })
      return api<ReportOut>(`/reports/${started.id}`)
    },
    refetchInterval: (query) => (query.state.data?.status === 'pending' ? 800 : false),
  })

  const value = (metric: string) =>
    (snapshot.data?.rows.find((row) => row.metric === metric)?.value ?? null) as number | null

  if (snapshot.data?.status !== 'ready') return <SkeletonRows rows={3} />

  if (!value('classifications_total')) {
    return (
      <Card className="mt-24">
        <EmptyState
          icon={Bot}
          title="The pipeline has not classified anything yet"
          message="Accuracy is measured against agent corrections, so it needs tickets that have been through triage."
        />
      </Card>
    )
  }

  const drafts = Number(value('drafts_total') ?? 0)

  return (
    <>
      <div className="mt-24 grid gap-16 md:grid-cols-3 md:gap-24">
        <Card>
          <p className="text-caption text-muted tracking-wide uppercase">Classification accuracy</p>
          <div className="mt-12">
            <AIInsightChip
              label="Not corrected by an agent"
              confidence={(value('classification_accuracy') ?? 0) * 100}
            />
          </div>
          <p className="text-body-sm text-muted mt-12">
            {value('classifications_total')} classifications recorded.
          </p>
        </Card>

        <Card>
          <p className="text-caption text-muted tracking-wide uppercase">Auto-routing accepted</p>
          <p className="text-h1 mt-12 font-semibold tabular-nums">
            {formatRate(value('auto_routing_acceptance_rate'))}
          </p>
          <p className="text-body-sm text-muted mt-4">
            Share of routed tickets an agent did not override.
          </p>
        </Card>

        <Card>
          <p className="text-caption text-muted tracking-wide uppercase">Draft approval</p>
          <p className="text-h1 mt-12 font-semibold tabular-nums">
            {formatRate(value('draft_approval_rate'))}
          </p>
          <p className="text-body-sm text-muted mt-4">
            Approved or edited, out of {drafts} draft{drafts === 1 ? '' : 's'}.
          </p>
        </Card>
      </div>

      <Card className="mt-24">
        <h2 className="text-h3 font-semibold">Draft review outcomes</h2>
        <p className="text-body-sm text-muted mt-8">
          Human-in-the-loop is mandatory — no draft reaches a requester without an agent acting on
          it, so every draft ends in exactly one of these.
        </p>
        <ul className="mt-16 flex flex-col gap-12">
          {(
            [
              ['Approved as written', 'drafts_approved'],
              ['Edited before sending', 'drafts_edited'],
              ['Rejected', 'drafts_rejected'],
            ] as const
          ).map(([label, metric]) => (
            <li
              key={metric}
              className="border-border flex items-center justify-between border-b py-8 last:border-b-0"
            >
              <span className="text-body-sm">{label}</span>
              <span className="text-data font-mono tabular-nums">{value(metric) ?? 0}</span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}

function TrendChart({ report }: { report: ReportOut }) {
  if (report.rows.length === 0) return null

  const data = report.rows.map((row) => ({
    day: String(row.day).slice(0, 10),
    routing:
      row.auto_routing_acceptance_rate === null
        ? null
        : Number(row.auto_routing_acceptance_rate) * 100,
    drafts: row.draft_approval_rate === null ? null : Number(row.draft_approval_rate) * 100,
  }))

  return (
    <div className="mt-24 h-[280px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid {...chartGrid} />
          <XAxis dataKey="day" {...chartAxis} />
          <YAxis domain={[0, 100]} unit="%" {...chartAxis} />
          <Tooltip {...chartTooltip} />
          <Legend {...chartLegend} />
          {/* Both series are model output, so both carry the AI violet — giving
              one of them a different hue would claim a difference that isn't
              there. They separate by dash pattern, which also survives a
              colour-blind reader and a greyscale print. */}
          <Line
            type="monotone"
            dataKey="routing"
            name="Auto-routing accepted"
            stroke="var(--color-ai)"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="drafts"
            name="Drafts approved"
            stroke="var(--color-ai)"
            strokeDasharray="4 4"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
