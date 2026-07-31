import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'

import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ApiError } from '../lib/api'
import { HOME_BY_ROLE, login, useUser } from '../lib/auth'
import { cn, focusRing } from '../lib/ui'

export function Login() {
  const user = useUser()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Login is the one screen every persona sees, so Doc 04 designs it once in
  // the light, Aave-inspired style rather than theming it per role.
  useEffect(() => {
    document.documentElement.classList.remove('dark')
  }, [])

  const from = (location.state as { from?: string } | null)?.from

  if (user) return <Navigate to={from ?? HOME_BY_ROLE[user.role]} replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const signedIn = await login(email, password)
      // Back to wherever they were headed before the redirect, else role home.
      navigate(from ?? HOME_BY_ROLE[signedIn.role], { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? 'That email and password combination is not recognised.'
          : err instanceof ApiError
            ? err.message
            : 'Could not reach the server. Check your connection and try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-canvas text-ink flex min-h-dvh flex-col items-center justify-center p-24">
      <div className="w-full max-w-[420px]">
        {/* The gradient text fill is Doc 04's single sanctioned exception to the
            AI-signature-only gradient rule: first impression, not a signal. */}
        <h1 className="text-gradient font-display text-hero animate-[rise-in_var(--duration-page)_ease-out] leading-tight font-bold">
          AgentDesk
        </h1>
        <p className="text-body text-muted mt-16">
          AI-native ticket management. Sign in to continue.
        </p>

        <form onSubmit={onSubmit} className="mt-48 flex flex-col gap-16" noValidate>
          <Input
            label="Email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            validate={(v) => (v.includes('@') ? null : 'Enter a valid email address.')}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && (
            <p role="alert" className="text-body-sm text-critical">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={submitting} className="mt-16">
            {submitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>

        <div className="text-body-sm text-muted mt-24 flex flex-col gap-8">
          <Link
            to="/forgot-password"
            className={cn('text-brand-start font-medium underline underline-offset-4', focusRing)}
          >
            Forgot your password?
          </Link>
          <span>
            New here?{' '}
            <Link
              to="/signup"
              className={cn('text-brand-start font-medium underline underline-offset-4', focusRing)}
            >
              Create an account
            </Link>
          </span>
        </div>
      </div>
    </div>
  )
}
