import { useRef, useState, type KeyboardEvent } from 'react'

import { applyMention, matchPeople, mentionQuery } from '../lib/agent'
import type { DirectoryUser } from '../lib/types'
import { cn, focusRing } from '../lib/ui'
import { Avatar } from './Avatar'

export interface MentionTextareaProps {
  id: string
  value: string
  onChange: (value: string) => void
  people: DirectoryUser[]
  placeholder?: string
  rows?: number
  className?: string
}

/**
 * Comment composer with `@` autocomplete. Picking someone inserts their email
 * address, which is the form `comment_mentions` is written from server-side —
 * so what the agent sees typed is exactly what the backend will match.
 */
export function MentionTextarea({
  id,
  value,
  onChange,
  people,
  placeholder,
  rows = 4,
  className,
}: MentionTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const [token, setToken] = useState<{ query: string; start: number } | null>(null)
  const [cursor, setCursor] = useState(0)

  const matches = token ? matchPeople(people, token.query) : []
  const open = matches.length > 0

  function reread(target: HTMLTextAreaElement) {
    const next = mentionQuery(target.value, target.selectionStart)
    setToken(next)
    setCursor(0)
  }

  function choose(person: DirectoryUser) {
    const element = ref.current
    if (!element || !token) return
    const result = applyMention(value, token.start, element.selectionStart, person.email)
    onChange(result.text)
    setToken(null)
    // Restore the caret after React has written the new value back.
    requestAnimationFrame(() => {
      element.focus()
      element.setSelectionRange(result.caret, result.caret)
    })
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => Math.min(c + 1, matches.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => Math.max(c - 1, 0))
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      choose(matches[cursor])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setToken(null)
    }
  }

  return (
    <div className="relative">
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        value={value}
        placeholder={placeholder}
        aria-autocomplete="list"
        aria-expanded={open}
        onKeyDown={onKeyDown}
        onClick={(e) => reread(e.currentTarget)}
        onChange={(e) => {
          onChange(e.target.value)
          reread(e.currentTarget)
        }}
        onBlur={() => setToken(null)}
        className={cn(
          'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary w-full border p-12',
          'placeholder:text-muted focus:border-primary transition-colors duration-micro',
          focusRing,
          className,
        )}
      />

      {open && (
        <ul
          role="listbox"
          aria-label="Mention a teammate"
          className={cn(
            'rounded-card border-border bg-elevated shadow-overlay absolute z-50 mt-4 w-full max-w-[320px] border p-4',
            'animate-[fade-in_var(--duration-dropdown)_ease-out]',
          )}
        >
          {matches.map((person, i) => (
            <li key={person.id}>
              <button
                type="button"
                role="option"
                aria-selected={i === cursor}
                // The composer's blur fires before click, so commit on mousedown.
                onMouseDown={(e) => {
                  e.preventDefault()
                  choose(person)
                }}
                onMouseEnter={() => setCursor(i)}
                className={cn(
                  'rounded-control flex w-full cursor-pointer items-center gap-12 px-12 py-8 text-left',
                  i === cursor && 'bg-surface',
                )}
              >
                <Avatar name={person.full_name} seed={person.id} size="sm" />
                <span className="min-w-0">
                  <span className="text-body-sm text-ink block truncate">{person.full_name}</span>
                  <span className="text-caption text-muted block truncate">{person.email}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
