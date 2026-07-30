import { NavLink } from 'react-router'

import { cn, focusRing } from '../lib/ui'
import { PORTAL_TABS } from './nav'

/**
 * Customer Portal only, mobile only. Doc 04 gives the Agent Console and Admin
 * Dashboard an off-canvas drawer instead — their nav is too long for four tabs.
 */
export function BottomTabBar() {
  return (
    <nav
      aria-label="Main"
      className="border-border bg-canvas fixed inset-x-0 bottom-0 z-40 flex border-t md:hidden"
    >
      {PORTAL_TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === '/portal/tickets'}
          className={({ isActive }) =>
            cn(
              'text-caption flex min-h-[56px] flex-1 flex-col items-center justify-center gap-4',
              'transition-colors duration-micro',
              isActive
                ? // Colour is never the only signal — the active tab also gains
                  // a top accent bar and a medium weight.
                  'text-ink border-brand-start border-t-2 font-medium'
                : 'text-muted border-t-2 border-transparent',
              focusRing,
            )
          }
        >
          <tab.icon aria-hidden size={20} strokeWidth={1.5} />
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
