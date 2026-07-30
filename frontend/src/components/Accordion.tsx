import { ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface AccordionItem {
  id: string
  title: string
  content: ReactNode
}

export interface AccordionProps {
  items: AccordionItem[]
  /** Doc 04: closed by default, except where one item is pre-expanded because
   *  it is the relevant one (e.g. the closest FAQ match during ticket creation). */
  defaultOpenId?: string
}

export function Accordion({ items, defaultOpenId }: AccordionProps) {
  const [openId, setOpenId] = useState<string | null>(defaultOpenId ?? null)

  return (
    <div className="border-border divide-border divide-y border-y">
      {items.map((item) => {
        const open = item.id === openId
        return (
          <div key={item.id}>
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpenId(open ? null : item.id)}
              className={cn(
                'text-body text-ink flex w-full cursor-pointer items-center justify-between gap-16 py-16 text-left font-medium',
                focusRing,
              )}
            >
              {item.title}
              <ChevronDown
                aria-hidden
                size={20}
                strokeWidth={1.5}
                className={cn(
                  'text-muted shrink-0 transition-transform duration-micro',
                  open && 'rotate-180',
                )}
              />
            </button>
            {/* Height-only animation via a 0fr→1fr grid row. Doc 04 forbids
                fading the content in separately from the height change. */}
            <div
              className={cn(
                'grid transition-[grid-template-rows] duration-card ease-out',
                open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]',
              )}
            >
              <div className="overflow-hidden">
                <div className="text-body text-muted pb-16">{item.content}</div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
