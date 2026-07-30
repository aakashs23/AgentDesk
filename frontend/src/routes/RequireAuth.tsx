import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { HOME_BY_ROLE, useUser } from '../lib/auth'
import type { Role } from '../lib/session'
import { toast } from '../lib/toast'

export interface RequireAuthProps {
  /** Omit to allow any signed-in role. */
  roles?: Role[]
}

/**
 * App Flow Doc 03 §3 and §8:
 *  - no session → Login, with the requested URL preserved and restored after
 *    authenticating;
 *  - wrong role → the caller's own role home plus an "Access restricted" toast,
 *    never a dead end or a blank 403 page.
 */
export function RequireAuth({ roles }: RequireAuthProps) {
  const user = useUser()
  const location = useLocation()
  const denied = user !== null && roles !== undefined && !roles.includes(user.role)

  useEffect(() => {
    if (denied) toast('Access restricted', 'error')
  }, [denied])

  if (!user) {
    // `state.from` is what Login replays on success.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }
  if (denied) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  return <Outlet />
}
