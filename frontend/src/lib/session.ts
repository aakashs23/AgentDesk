/**
 * The stored session: access token, refresh token, and the user record the
 * login response returned. Kept in localStorage so a page reload restores the
 * session (and with it the theme preference) without a network round-trip.
 *
 * This is an external store rather than React context so `api.ts` can read and
 * rotate tokens without importing anything from the React tree.
 */

export type Role = 'requester' | 'agent' | 'team_lead' | 'admin'

export interface User {
  id: string
  email: string
  full_name: string
  role: Role
  team_id: string | null
  is_active: boolean
  email_verified: boolean
  theme_preference: 'light' | 'dark' | 'system'
}

export interface Session {
  access: string
  refresh: string
  user: User
}

const KEY = 'agentdesk.session'

function read(): Session | null {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? 'null') as Session | null
  } catch {
    return null // corrupt entry — treat as logged out rather than crashing the app
  }
}

let current = read()
const listeners = new Set<() => void>()

export function getSession() {
  return current
}

export function setSession(next: Session | null) {
  current = next
  if (next) localStorage.setItem(KEY, JSON.stringify(next))
  else localStorage.removeItem(KEY)
  listeners.forEach((l) => l())
}

export function subscribeSession(listener: () => void) {
  listeners.add(listener)
  return () => void listeners.delete(listener)
}

// Another tab logged in or out — mirror it here so the two don't diverge.
window.addEventListener('storage', (e) => {
  if (e.key !== KEY) return
  current = read()
  listeners.forEach((l) => l())
})
