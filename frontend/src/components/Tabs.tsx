import type { ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface Tab {
  id: string
  label: string
  /** Tabs a role can't see are filtered by the caller, not disabled here. */
  badge?: ReactNode
}

export interface TabsProps {
  tabs: Tab[]
  active: string
  onChange: (id: string) => void
}

/**
 * Controlled on purpose: Doc 04 requires switching tabs to preserve the parent
 * view's scroll position, which means the parent owns the state and nothing
 * above the tab strip remounts.
 */
export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div role="tablist" className="border-border flex gap-24 border-b">
      {tabs.map((tab) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(tab.id)}
            className={cn(
              'text-body -mb-px cursor-pointer border-b-2 px-4 pb-12 font-medium',
              'transition-colors duration-micro flex items-center gap-8',
              selected
                ? 'border-brand-start text-ink'
                : 'text-muted hover:text-ink border-transparent',
              focusRing,
            )}
          >
            {tab.label}
            {tab.badge}
          </button>
        )
      })}
    </div>
  )
}
