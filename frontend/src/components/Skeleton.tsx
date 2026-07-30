import { cn } from '../lib/ui'

/**
 * Doc 04 prefers a skeleton over a spinner everywhere the eventual shape is
 * predictable — a spinner says "wait", a skeleton says "this is what's coming".
 * Callers size it to match the real content so nothing jumps on arrival.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('skeleton rounded-control h-16 w-full', className)} />
}

/** Skeleton stand-in for a list of rows (Ticket Queue, Audit Log, KB list). */
export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="flex flex-col gap-12">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-[44px]" />
      ))}
    </div>
  )
}
