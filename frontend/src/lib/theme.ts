import { useEffect } from 'react'
import { useLocation } from 'react-router'

import { updateMe, useUser } from './auth'
import { resolveTheme } from './ui'

export function useTheme() {
  const { pathname } = useLocation()
  const preference = useUser()?.theme_preference ?? 'system'
  const mode = resolveTheme(preference, pathname)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', mode === 'dark')
  }, [mode])

  return {
    mode,
    preference,
    /** Writes through to `users.theme_preference`, so it survives a reload. */
    toggle: () => updateMe({ theme_preference: mode === 'dark' ? 'light' : 'dark' }),
  }
}
