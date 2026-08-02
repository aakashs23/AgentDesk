import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { ApiError, api } from '../lib/api'
import { toast } from '../lib/toast'
import type { ReportOut } from '../lib/types'
import { cn, focusRing } from '../lib/ui'
import { Button } from './Button'
import { ErrorState } from './EmptyState'
import { Skeleton } from './Skeleton'

export interface ReportChoice {
  id: string
  label: string
}

export interface ReportRunnerProps {
  reports: ReportChoice[]
  /** Doc 03 §23 gives Admin every export format; Team Reports only offers CSV. */
  formats?: readonly string[]
  /** Rendered above the table once a report is ready — the AI monitor charts it. */
  children?: (report: ReportOut) => ReactNode
}

const DAY_MS = 24 * 60 * 60 * 1000

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * DAY_MS).toISOString().slice(0, 10)
}

/**
 * Generate → poll → render → export, for any of the Phase 8 report types.
 *
 * Shared between Team Reports and the Admin's Reports & Analytics because the
 * endpoints are identical: `/reports/*` scopes its rows to the caller via
 * `scope_tickets_to_caller`, so "org-wide" versus "my team" is a property of
 * who is asking, not of a second endpoint or a second screen.
 */
export function ReportRunner({ reports, formats = ['csv'], children }: ReportRunnerProps) {
  const [reportType, setReportType] = useState(reports[0].id)
  const [start, setStart] = useState(isoDaysAgo(30))
  const [end, setEnd] = useState('')
  const [reportId, setReportId] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      api<ReportOut>('/reports/generate', {
        method: 'POST',
        json: {
          report_type: reportType,
          // Dates arrive from <input type="date"> as YYYY-MM-DD; the end bound
          // is inclusive of its whole day, which a bare date is not.
          start_date: start ? `${start}T00:00:00Z` : null,
          end_date: end ? `${end}T23:59:59Z` : null,
        },
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

  const ready = report.data?.status === 'ready' ? report.data : null

  return (
    <>
      <div className="mt-24 flex flex-wrap items-end gap-16">
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Report</span>
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] min-w-[240px] border px-12',
              focusRing,
            )}
          >
            {reports.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>

        {/* Native date inputs: a picker dependency would buy nothing here. */}
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">From</span>
          <input
            type="date"
            value={start}
            max={end || undefined}
            onChange={(e) => setStart(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] border px-12',
              focusRing,
            )}
          />
        </label>
        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">To</span>
          <input
            type="date"
            value={end}
            min={start || undefined}
            onChange={(e) => setEnd(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] border px-12',
              focusRing,
            )}
          />
        </label>

        <Button variant="primary" disabled={generate.isPending} onClick={() => generate.mutate()}>
          Generate
        </Button>

        {ready &&
          formats.map((format) => (
            <a
              key={format}
              href={`/api/v1/reports/${ready.id}/export?format=${format}`}
              download
              className={cn(
                'text-body-sm text-primary font-medium underline underline-offset-4',
                focusRing,
              )}
            >
              Export {format.toUpperCase()}
            </a>
          ))}
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

        {ready && (
          <>
            {children?.(ready)}
            <ReportTable report={ready} />
          </>
        )}
      </div>
    </>
  )
}

/** Doc 04 Responsive: wide data scrolls inside its own container so the page
 *  body never scrolls sideways. */
export function ReportTable({ report }: { report: ReportOut }) {
  return (
    <div className="border-border rounded-card mt-16 overflow-x-auto border">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-border border-b">
            {report.columns.map((column) => (
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
          {report.rows.map((row, i) => (
            <tr key={i} className="border-border border-b last:border-b-0">
              {report.columns.map((column) => (
                <td key={column} className="text-body-sm px-16 py-12 whitespace-nowrap">
                  {String(row[column] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {report.rows.length === 0 && (
        <p className="text-body-sm text-muted px-16 py-24 text-center">No data in this period.</p>
      )}
    </div>
  )
}
