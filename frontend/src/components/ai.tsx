/**
 * The AI-signature components.
 *
 * The signature rule survived Doc 07, its carrier didn't: the flat `ai` violet
 * now means exactly one thing across the product — "the model produced or
 * influenced this" — and unlike Doc 04's gradient it appears *only* here, never
 * on a CTA or a nav indicator. Anything a human wrote stays neutral.
 */
import { Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '../lib/ui'
import { Drawer, type DrawerProps } from './Drawer'

export interface AIInsightChipProps {
  label: string
  /** 0–1, as the pipeline reports it. Rendered as a whole percentage. */
  confidence?: number
  className?: string
}

export function AIInsightChip({ label, confidence, className }: AIInsightChipProps) {
  const percent = confidence === undefined ? null : Math.round(confidence * 100)

  return (
    <span
      // The violet is never the only signal — the spark glyph and this label
      // carry the same meaning without colour.
      aria-label={
        percent === null
          ? `AI-suggested: ${label}`
          : `AI-suggested: ${label}, ${percent} percent confidence`
      }
      className={cn(
        'rounded-pill bg-ai-tint text-ai text-caption',
        'inline-flex items-center gap-4 px-12 py-4 font-medium tracking-wide uppercase',
        className,
      )}
    >
      <Sparkles aria-hidden size={16} strokeWidth={1.5} />
      {label}
      {percent !== null && <span className="font-mono normal-case">{percent}%</span>}
    </span>
  )
}

export interface DiffCalloutProps {
  /** What the value was before the AI changed it. */
  removed?: string
  /** What the AI set it to. */
  added: string
  caption?: string
}

/**
 * The diff-style change callout — a reclassification, a matched SLA rule.
 * Monospace and bordered, removed line muted/struck, added line in the AI
 * violet, since the addition is what the model decided.
 */
export function DiffCallout({ removed, added, caption }: DiffCalloutProps) {
  return (
    <div className="rounded-card border-border bg-surface border p-16">
      {caption && <p className="text-caption text-muted mb-8 tracking-wide uppercase">{caption}</p>}
      <div className="text-data font-mono whitespace-pre-wrap">
        {removed !== undefined && (
          <div className="text-muted line-through">
            <span aria-hidden>- </span>
            <span className="sr-only">Previously: </span>
            {removed}
          </div>
        )}
        <div className="text-ai">
          <span aria-hidden>+ </span>
          <span className="sr-only">AI set: </span>
          {added}
        </div>
      </div>
    </div>
  )
}

export interface AIDraftDrawerProps extends Omit<DrawerProps, 'header' | 'title'> {
  /** True while the model is still producing the draft. */
  generating?: boolean
  title?: string
}

/**
 * Shell for the AI Draft Response drawer. Phase 11 fills in the body (the draft
 * text, approve/edit/reject controls); what lives here is the part that matters
 * either way: the provenance header is the first thing visible on open, never
 * something the agent has to scroll past.
 */
export function AIDraftDrawer({
  generating = false,
  title = 'AI Draft Response',
  children,
  ...props
}: AIDraftDrawerProps) {
  return (
    <Drawer
      {...props}
      title={title}
      header={
        <div
          className={cn(
            'bg-ai-tint text-ai border-divider border-b px-24 py-16',
            generating && 'ai-shimmer',
          )}
        >
          <p className="text-caption flex items-center gap-8 font-medium tracking-wide uppercase">
            <Sparkles aria-hidden size={16} strokeWidth={1.5} />
            {generating ? 'Drafting a response…' : 'AI-generated — review before sending'}
          </p>
        </div>
      }
    >
      {children}
    </Drawer>
  )
}

/**
 * Wraps a region the model is actively working on. Distinct from <Skeleton>
 * on purpose: skeleton means "loading data", this means "the AI is thinking".
 */
export function AIGenerating({ children }: { children: ReactNode }) {
  return (
    <div role="status" aria-live="polite" className="ai-shimmer rounded-card">
      {children}
    </div>
  )
}
