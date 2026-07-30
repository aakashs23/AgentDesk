import { useSyncExternalStore } from 'react'

import { api } from './api'
import {
  getSession,
  setSession,
  subscribeSession,
  type Role,
  type Session,
  type User,
} from './session'

export type { Role, User }

/** Post-login landing per App Flow Doc 03 §3 — there is no shared home screen. */
export const HOME_BY_ROLE: Record<Role, string> = {
  requester: '/portal/tickets',
  agent: '/agent/queue',
  team_lead: '/agent/queue',
  admin: '/admin',
}

export function useSession(): Session | null {
  return useSyncExternalStore(subscribeSession, getSession)
}

export function useUser(): User | null {
  return useSession()?.user ?? null
}

export async function login(email: string, password: string): Promise<User> {
  const data = await api<{ access_token: string; refresh_token: string; user: User }>(
    '/auth/login',
    { method: 'POST', json: { email, password } },
  )
  setSession({ access: data.access_token, refresh: data.refresh_token, user: data.user })
  return data.user
}

export async function logout() {
  const session = getSession()
  setSession(null) // clear first: the user is logged out even if the call fails
  if (!session) return
  await api('/auth/logout', {
    method: 'POST',
    json: { refresh_token: session.refresh },
    headers: { authorization: `Bearer ${session.access}` },
  }).catch(() => {
    /* best-effort server-side revocation */
  })
}

/** Patch the signed-in user and keep the cached copy in the session in step. */
export async function updateMe(patch: Partial<Pick<User, 'full_name' | 'theme_preference'>>) {
  const session = getSession()
  if (!session) return
  const user = await api<User>(`/users/${session.user.id}`, { method: 'PATCH', json: patch })
  setSession({ ...getSession()!, user })
  return user
}
