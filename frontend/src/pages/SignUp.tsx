import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'

import { Button } from '../components/Button'
import { Input } from '../components/Input'
import { ApiError, api } from '../lib/api'
import { HOME_BY_ROLE, useUser } from '../lib/auth'
import { cn, focusRing } from '../lib/ui'

/** Login, Sign Up and verification are all first-touch surfaces: light, Aave-
 *  styled, designed once regardless of the eventual role (Doc 04). */
function useLightSurface() {
  useEffect(() => {
    document.documentElement.classList.remove('dark')
  }, [])
}

export function SignUp() {
  const user = useUser()
  const navigate = useNavigate()
  useLightSurface()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      // Self-service registration creates a requester; staff accounts are
      // admin-provisioned only (App Flow Doc 03 §4).
      await api('/auth/register', {
        method: 'POST',
        json: { email: email.trim(), password, full_name: fullName.trim() },
      })
      navigate(`/verify-email?sent=${encodeURIComponent(email.trim())}`, { replace: true })
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not create your account. Please try again.',
      )
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-canvas text-ink flex min-h-dvh flex-col items-center justify-center p-24">
      <div className="w-full max-w-[420px]">
        <h1 className="text-gradient font-display text-hero animate-[rise-in_var(--duration-page)_ease-out] leading-tight font-bold">
          Get started
        </h1>
        <p className="text-body text-muted mt-16">
          Create an account to raise and track support requests.
        </p>

        <form onSubmit={onSubmit} className="mt-48 flex flex-col gap-16" noValidate>
          <Input
            label="Full name"
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            validate={(v) => (v.trim() ? null : 'Please tell us your name.')}
          />
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
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            hint="At least 8 characters."
            validate={(v) => (v.length >= 8 ? null : 'Use at least 8 characters.')}
          />
          {error && (
            <p role="alert" className="text-body-sm text-critical">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={submitting} className="mt-16">
            {submitting ? 'Creating account…' : 'Create account'}
          </Button>
        </form>

        <p className="text-body-sm text-muted mt-24">
          Already have an account?{' '}
          <Link
            to="/login"
            className={cn('text-brand-start font-medium underline underline-offset-4', focusRing)}
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

/**
 * Handles both halves of verification: the "check your inbox" message right
 * after sign-up, and the result of following the emailed `?token=` link
 * (App Flow Doc 03 §4).
 */
export function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  useLightSurface()

  const token = searchParams.get('token')
  const sentTo = searchParams.get('sent')
  const [state, setState] = useState<'idle' | 'verifying' | 'done' | 'failed'>(
    token ? 'verifying' : 'idle',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    let cancelled = false
    api('/auth/verify-email', { method: 'POST', json: { token } })
      .then(() => !cancelled && setState('done'))
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not verify this link.')
        setState('failed')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <div className="bg-canvas text-ink flex min-h-dvh flex-col items-center justify-center p-24">
      <div className="w-full max-w-[420px]">
        <h1 className="text-gradient font-display text-hero animate-[rise-in_var(--duration-page)_ease-out] leading-tight font-bold">
          {state === 'done' ? 'You’re verified' : 'Check your inbox'}
        </h1>

        {state === 'idle' && (
          <p className="text-body text-muted mt-16">
            We’ve sent a verification link{sentTo ? ` to ${sentTo}` : ''}. Follow it to activate
            your account, then sign in.
          </p>
        )}
        {state === 'verifying' && (
          <p className="text-body text-muted mt-16">Verifying your email…</p>
        )}
        {state === 'done' && (
          <p className="text-body text-muted mt-16">
            Your email is confirmed. You can sign in now.
          </p>
        )}
        {state === 'failed' && (
          <p role="alert" className="text-body text-critical mt-16">
            {error} The link may have expired — try signing in to request a new one.
          </p>
        )}

        <Button
          variant="primary"
          className="mt-48 w-full"
          onClick={() => navigate('/login', { replace: true })}
        >
          Go to sign in
        </Button>
      </div>
    </div>
  )
}

/** Exported for the Login screen's "Forgot password?" link. */
export function ForgotPassword() {
  useLightSurface()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    // Always reports success: revealing whether an address is registered would
    // turn this into an account-enumeration oracle (the API does the same).
    await api('/auth/password-reset/request', {
      method: 'POST',
      json: { email: email.trim() },
    }).catch(() => undefined)
    setSent(true)
    setSubmitting(false)
  }

  return (
    <div className="bg-canvas text-ink flex min-h-dvh flex-col items-center justify-center p-24">
      <div className="w-full max-w-[420px]">
        <h1 className="text-gradient font-display text-hero animate-[rise-in_var(--duration-page)_ease-out] leading-tight font-bold">
          Reset password
        </h1>

        {sent ? (
          <p className="text-body text-muted mt-16">
            If that address has an account, a reset link is on its way.
          </p>
        ) : (
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
            <Button type="submit" variant="primary" disabled={submitting} className="mt-16">
              {submitting ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>
        )}

        <p className="text-body-sm text-muted mt-24">
          <Link
            to="/login"
            className={cn('text-brand-start font-medium underline underline-offset-4', focusRing)}
          >
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

/** Sets a new password from an emailed reset token. */
export function ResetPassword() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  useLightSurface()

  const token = searchParams.get('token') ?? ''
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await api('/auth/password-reset/confirm', {
        method: 'POST',
        json: { token, new_password: password },
      })
      navigate('/login', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reset your password.')
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-canvas text-ink flex min-h-dvh flex-col items-center justify-center p-24">
      <div className="w-full max-w-[420px]">
        <h1 className="text-gradient font-display text-hero animate-[rise-in_var(--duration-page)_ease-out] leading-tight font-bold">
          Choose a password
        </h1>
        <form onSubmit={onSubmit} className="mt-48 flex flex-col gap-16" noValidate>
          <Input
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            validate={(v) => (v.length >= 8 ? null : 'Use at least 8 characters.')}
          />
          {error && (
            <p role="alert" className="text-body-sm text-critical">
              {error}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            disabled={submitting || password.length < 8 || !token}
            className="mt-16"
          >
            {submitting ? 'Saving…' : 'Set password'}
          </Button>
        </form>
      </div>
    </div>
  )
}
