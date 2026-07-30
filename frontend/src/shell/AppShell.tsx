import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'

import { useDialog } from '../components/useDialog'
import { useUser } from '../lib/auth'
import { useTheme } from '../lib/theme'
import { cn } from '../lib/ui'
import { BottomTabBar } from './BottomTabBar'
import { CommandPalette } from './CommandPalette'
import { navFor } from './nav'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

const COLLAPSE_KEY = 'agentdesk.sidebar-collapsed'

/** Doc 04: tablet (768–1279px) defaults to the collapsed 72px icon rail. */
function initialCollapsed() {
  const stored = localStorage.getItem(COLLAPSE_KEY)
  if (stored !== null) return stored === 'true'
  return window.matchMedia('(max-width: 1279px)').matches
}

export interface AppShellProps {
  /** '/portal' | '/agent' | '/admin' — drives nav paths and the theme default. */
  basePath: string
  searchPlaceholder: string
}

export function AppShell({ basePath, searchPlaceholder }: AppShellProps) {
  const user = useUser()
  useTheme() // applies the per-surface light/dark default for this route
  const [collapsed, setCollapsed] = useState(initialCollapsed)
  const [navOpen, setNavOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)

  const isPortal = basePath === '/portal'
  const navDialog = useDialog(navOpen, () => setNavOpen(false))

  // The Cmd/Ctrl+K shortcut is an Agent Console / Admin Dashboard affordance
  // (Phase 9 scope). Every surface can still reach the palette from the top
  // bar's search control, which is what Doc 03 §2 asks of all three portals.
  useEffect(() => {
    if (isPortal) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isPortal])

  if (!user) return null // RequireAuth has already redirected

  const groups = navFor(user.role)

  return (
    <div className="bg-canvas text-ink flex min-h-dvh">
      {/* Desktop/tablet rail. Below md the portal falls back to the bottom tab
          bar and the product surfaces to the off-canvas drawer below. */}
      <div className="sticky top-0 hidden h-dvh md:block">
        <Sidebar
          groups={groups}
          collapsed={collapsed}
          onToggle={() =>
            setCollapsed((c) => {
              localStorage.setItem(COLLAPSE_KEY, String(!c))
              return !c
            })
          }
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          user={user}
          basePath={basePath}
          onOpenNav={isPortal ? undefined : () => setNavOpen(true)}
          onOpenSearch={() => setPaletteOpen(true)}
          searchPlaceholder={searchPlaceholder}
        />
        <main
          className={cn(
            'flex-1 p-16 md:p-24 lg:p-32',
            isPortal && 'pb-[72px] md:pb-24', // clearance for the bottom tab bar
          )}
        >
          <Outlet />
        </main>
      </div>

      {isPortal && <BottomTabBar />}

      {!isPortal && (
        <dialog
          ref={navDialog}
          aria-label="Navigation"
          className="bg-canvas mr-auto ml-0 h-dvh max-h-dvh backdrop:bg-black/40 md:hidden open:animate-[slide-in-left_var(--duration-drawer)_ease-out]"
        >
          <Sidebar
            groups={groups}
            collapsed={false}
            showToggle={false}
            onNavigate={() => setNavOpen(false)}
          />
        </dialog>
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        role={user.role}
        ticketBasePath={`${basePath}/tickets`}
      />
    </div>
  )
}
