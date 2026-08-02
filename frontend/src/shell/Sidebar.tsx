import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { NavLink } from 'react-router'

import { Tooltip } from '../components/Tooltip'
import { cn, focusRing, needsExactMatch, tapTarget } from '../lib/ui'
import type { NavGroup } from './nav'

export interface SidebarProps {
  groups: NavGroup[]
  collapsed: boolean
  onToggle?: () => void
  /** In the mobile off-canvas drawer there is no collapse control. */
  showToggle?: boolean
  onNavigate?: () => void
}

export function Sidebar({
  groups,
  collapsed,
  onToggle,
  showToggle = true,
  onNavigate,
}: SidebarProps) {
  const allPaths = groups.flatMap((g) => g.items.map((i) => i.to))

  return (
    <nav
      aria-label="Main"
      className={cn(
        'border-divider bg-canvas flex h-full flex-col border-r py-24',
        // Doc 04: the collapse is a width animation only — a fade would briefly
        // hide navigation the user may be mid-click on.
        'transition-[width] duration-page ease-in-out',
        collapsed ? 'w-[72px]' : 'w-[260px]',
      )}
    >
      <div className={cn('flex flex-col gap-24 overflow-y-auto', collapsed ? 'px-12' : 'px-16')}>
        {groups.map((group, i) => (
          <div key={group.heading ?? i} className="flex flex-col gap-4">
            {group.heading && !collapsed && (
              <p className="text-caption text-muted mb-4 px-12 tracking-wide uppercase">
                {group.heading}
              </p>
            )}
            {group.items.map((item) => {
              const link = (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={needsExactMatch(allPaths, item.to)}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'rounded-control text-body relative flex items-center gap-12 px-12',
                      tapTarget,
                      'transition-colors duration-micro',
                      collapsed && 'justify-center',
                      isActive
                        ? // Doc 07 §6 offers a left border or a tint fill; the fill
                          // is the one that isn't a side stripe. Weight carries the
                          // state alongside colour, so it never rests on hue alone.
                          'bg-primary-tint text-primary font-medium'
                        : 'text-muted hover:text-ink hover:bg-sunken',
                      focusRing,
                    )
                  }
                >
                  <item.icon aria-hidden size={20} strokeWidth={1.5} className="shrink-0" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </NavLink>
              )
              // Collapsed to an icon rail, the label only survives as a tooltip.
              return collapsed ? (
                <Tooltip key={item.to} label={item.label}>
                  {link}
                </Tooltip>
              ) : (
                link
              )
            })}
          </div>
        ))}
      </div>

      {showToggle && (
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          className={cn(
            'text-muted hover:text-ink mt-24 flex cursor-pointer items-center gap-12 px-12',
            collapsed ? 'mx-12 justify-center' : 'mx-16',
            'rounded-control text-body-sm',
            tapTarget,
            focusRing,
          )}
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden size={20} strokeWidth={1.5} />
          ) : (
            <>
              <PanelLeftClose aria-hidden size={20} strokeWidth={1.5} />
              Collapse
            </>
          )}
        </button>
      )}
    </nav>
  )
}
