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
      className="border-divider bg-surface fixed inset-x-0 bottom-0 z-40 flex border-t md:hidden"
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
                ? // Tinting the icon and label is what a tab bar does on both
                  // mobile platforms; the weight change keeps the state legible
                  // without colour. An accent rail here would be a web-ism.
                  'text-primary font-medium'
                : 'text-muted',
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
