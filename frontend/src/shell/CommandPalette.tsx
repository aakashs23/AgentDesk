import { useQuery } from '@tanstack/react-query'
import { CornerDownLeft, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { useDialog } from '../components/useDialog'
import { api } from '../lib/api'
import { cn, formatTicketId } from '../lib/ui'
import { navFor } from './nav'
import type { Role } from '../lib/session'

/** Flattened by the search router: score merged into the ticket fields. */
interface TicketHit {
  id: string
  display_id: number | null
  subject: string
}

function useDebounced<T>(value: T, ms = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return debounced
}

export interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  role: Role
  /** Ticket detail lives under whichever surface the user is in. */
  ticketBasePath: string
}

/**
 * Cmd/Ctrl+K palette for the Agent Console and Admin Dashboard (Doc 03 §18 —
 * requesters search their own tickets from the top bar instead).
 *
 * ponytail: navigation destinations plus ticket search. Actions ("assign to
 * me", "escalate") land in Phase 11 alongside the endpoints that back them.
 */
export function CommandPalette({ open, onClose, role, ticketBasePath }: CommandPaletteProps) {
  const ref = useDialog(open, onClose)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const debounced = useDebounced(query.trim())

  const destinations = useMemo(() => {
    const all = navFor(role).flatMap((g) => g.items)
    const q = query.trim().toLowerCase()
    return q ? all.filter((i) => i.label.toLowerCase().includes(q)) : all
  }, [role, query])

  const { data: hits = [], isFetching } = useQuery({
    queryKey: ['palette', debounced],
    enabled: open && debounced.length > 1,
    queryFn: () =>
      api<{ tickets: TicketHit[] }>(
        `/search/tickets?q=${encodeURIComponent(debounced)}&limit=5`,
      ).then((r) => r.tickets),
  })

  const results = [
    ...destinations.map((d) => ({ key: d.to, label: d.label, hint: 'Go to', to: d.to })),
    ...hits.map((h) => ({
      key: h.id,
      label: h.subject,
      hint: formatTicketId(h.display_id),
      to: `${ticketBasePath}/${h.id}`,
    })),
  ]

  // Reset between openings so a stale query never greets the next invocation.
  useEffect(() => {
    if (!open) {
      setQuery('')
      setCursor(0)
    }
  }, [open])

  useEffect(() => setCursor(0), [debounced, query])

  const select = (index: number) => {
    const target = results[index]
    if (!target) return
    onClose()
    navigate(target.to)
  }

  return (
    <dialog
      ref={ref}
      aria-label="Command palette"
      className={cn(
        'rounded-card border-border bg-elevated text-ink shadow-elevated',
        'mx-auto mt-[96px] mb-auto w-[calc(100%-32px)] max-w-[640px] border p-0 backdrop:bg-black/40',
        'open:animate-[rise-in_var(--duration-modal)_ease-out]',
      )}
      onKeyDown={(e) => {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setCursor((c) => Math.min(c + 1, results.length - 1))
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setCursor((c) => Math.max(c - 1, 0))
        } else if (e.key === 'Enter') {
          e.preventDefault()
          select(cursor)
        }
      }}
    >
      <div className="border-border flex items-center gap-12 border-b px-16">
        <Search aria-hidden size={20} strokeWidth={1.5} className="text-muted shrink-0" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search tickets or jump to a page…"
          aria-label="Search tickets or jump to a page"
          className="text-body placeholder:text-muted h-[44px] w-full bg-transparent outline-none"
        />
      </div>

      <ul className="max-h-[320px] overflow-y-auto p-8">
        {results.map((result, i) => (
          <li key={result.key}>
            <button
              type="button"
              onMouseEnter={() => setCursor(i)}
              onClick={() => select(i)}
              aria-current={i === cursor}
              className={cn(
                'rounded-control text-body flex w-full cursor-pointer items-center justify-between gap-12 px-12 py-12 text-left',
                i === cursor && 'bg-surface',
              )}
            >
              <span className="truncate">{result.label}</span>
              <span className="text-caption text-muted font-mono shrink-0">{result.hint}</span>
            </button>
          </li>
        ))}
        {results.length === 0 && (
          <li className="text-body-sm text-muted px-12 py-12">
            {isFetching ? 'Searching…' : 'No matches'}
          </li>
        )}
      </ul>

      <p className="border-border text-caption text-muted flex items-center gap-4 border-t px-16 py-8">
        <CornerDownLeft aria-hidden size={16} strokeWidth={1.5} />
        to open · Esc to dismiss
      </p>
    </dialog>
  )
}
