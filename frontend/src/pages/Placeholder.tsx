import { Compass } from 'lucide-react'

/**
 * Stands in for every screen Phases 10–12 will build, so the shell built in
 * Phase 9 is fully navigable and the role-based routing can actually be
 * verified. Uses Doc 04's empty-state treatment — line illustration in the ink
 * colour (never the gradient) plus a typographic headline.
 */
export function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center py-64 text-center">
      <Compass aria-hidden size={24} strokeWidth={1.5} className="text-ink" />
      <h1 className="font-display text-h1 mt-24 font-semibold">{title}</h1>
      <p className="text-body text-muted mt-16">Built in {phase}.</p>
    </div>
  )
}
