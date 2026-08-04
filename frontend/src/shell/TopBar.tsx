import { useQuery } from '@tanstack/react-query'
import { Bell, LogOut, Menu, Moon, Search, Settings, Sun } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Avatar } from '../components/Avatar'
import { Dropdown, DropdownItem } from '../components/Dropdown'
import { api } from '../lib/api'
import { logout, type User } from '../lib/auth'
import { useTheme } from '../lib/theme'
import { cn, focusRing, tapTarget } from '../lib/ui'

interface Notification {
  id: string
  is_read: boolean
}

export interface TopBarProps {
  user: User
  /** Surface prefix ('/portal', '/agent', '/admin') — the shared screens live
   *  under each surface so the shell around them stays the right one. */
  basePath: string
  /** Opens the off-canvas nav on mobile; absent on the Customer Portal, which
   *  uses a bottom tab bar instead. */
  onOpenNav?: () => void
  onOpenSearch: () => void
  searchPlaceholder: string
}

export function TopBar({
  user,
  basePath,
  onOpenNav,
  onOpenSearch,
  searchPlaceholder,
}: TopBarProps) {
  const navigate = useNavigate()
  const { mode, toggle } = useTheme()

  const { data: unread = 0 } = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: () =>
      api<Notification[]>('/notifications?unread_only=true&limit=100').then((n) => n.length),
    refetchInterval: 60_000,
  })

  return (
    // Doc 07 §7: 64px, surface-coloured, hairline divider, and the glass only
    // matters once content scrolls beneath it — hence the translucent fill.
    <header className="border-divider bg-surface/80 sticky top-0 z-40 flex h-[64px] shrink-0 items-center gap-16 border-b px-16 backdrop-blur-[12px] md:px-32">
      {onOpenNav && (
        <button
          type="button"
          onClick={onOpenNav}
          aria-label="Open navigation"
          className={cn(
            'text-muted hover:text-ink -ml-12 flex cursor-pointer items-center justify-center md:hidden',
            tapTarget,
            focusRing,
          )}
        >
          <Menu aria-hidden size={20} strokeWidth={1.5} />
        </button>
      )}

      {/* A button rather than a real input: the palette owns the query, so two
          places to type the same search would only get out of sync. */}
      <button
        type="button"
        onClick={onOpenSearch}
        className={cn(
          // Doc 07 §17: a pill on the sunken fill, not a bordered input — it
          // opens the palette rather than accepting text.
          'rounded-pill bg-sunken text-body text-muted hover:text-ink',
          'flex h-[44px] flex-1 items-center gap-8 px-16 md:max-w-[420px]',
          'cursor-pointer transition-colors duration-micro',
          focusRing,
        )}
      >
        <Search aria-hidden size={16} strokeWidth={1.5} />
        <span className="truncate">{searchPlaceholder}</span>
      </button>

      <div className="ml-auto flex items-center gap-8">
        <button
          type="button"
          onClick={() => navigate(`${basePath}/notifications`)}
          aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
          className={cn(
            'text-muted hover:text-ink relative flex cursor-pointer items-center justify-center',
            tapTarget,
            focusRing,
          )}
        >
          <Bell aria-hidden size={20} strokeWidth={1.5} />
          {unread > 0 && (
            // `h-[16px]`, not `h-4`: this project keys the spacing scale in
            // pixels (`--spacing-4: 4px`), so `h-4` compiles to a 4px-tall
            // badge here rather than stock Tailwind's 16px. Centring with flex
            // also retires the `leading-4` that was clipping the digits.
            <span className="absolute -top-1 -right-1 flex h-[16px] min-w-[16px] items-center justify-center rounded-full bg-critical-fill px-1 text-[10px] font-bold text-white">
              {unread > 99 ? '99+' : unread}
            </span>
          )}
        </button>

        <Dropdown
          align="end"
          label="User menu"
          trigger={<Avatar name={user.full_name} seed={user.id} />}
        >
          {(close) => (
            <>
              <div className="px-12 py-8">
                <p className="text-body text-ink truncate font-medium">{user.full_name}</p>
                <p className="text-body-sm text-muted truncate">{user.email}</p>
              </div>
              <DropdownItem
                onClick={() => {
                  close()
                  navigate(`${basePath}/settings`)
                }}
              >
                <Settings aria-hidden size={16} strokeWidth={1.5} />
                Account Settings
              </DropdownItem>
              <DropdownItem
                onClick={() => {
                  close()
                  void toggle()
                }}
              >
                {mode === 'dark' ? (
                  <Sun aria-hidden size={16} strokeWidth={1.5} />
                ) : (
                  <Moon aria-hidden size={16} strokeWidth={1.5} />
                )}
                {mode === 'dark' ? 'Light mode' : 'Dark mode'}
              </DropdownItem>
              <DropdownItem
                onClick={() => {
                  close()
                  void logout()
                }}
              >
                <LogOut aria-hidden size={16} strokeWidth={1.5} />
                Log out
              </DropdownItem>
            </>
          )}
        </Dropdown>
      </div>
    </header>
  )
}
