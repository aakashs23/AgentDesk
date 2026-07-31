import { useMutation } from '@tanstack/react-query'
import { Moon, Sun } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Input } from '../../components/Input'
import { ApiError, api } from '../../lib/api'
import { updateMe, useUser } from '../../lib/auth'
import { useTheme } from '../../lib/theme'
import { toast } from '../../lib/toast'
import { NOTIFICATION_TRIGGERS, type NotificationTrigger } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'

const TRIGGER_LABELS: Record<NotificationTrigger, string> = {
  ticket_assigned: 'My ticket is assigned',
  ticket_replied: 'Someone replies to my ticket',
  status_changed: 'My ticket changes status',
  sla_warning: 'A response is due soon',
  sla_breached: 'A response is overdue',
  escalation: 'My ticket is escalated',
  mention: 'I am mentioned',
  ticket_closed: 'My ticket is closed',
  automation_executed: 'An automation runs on my ticket',
}

export function AccountSettings() {
  return (
    <div className="mx-auto flex max-w-[640px] flex-col gap-32">
      <h1 className="font-display text-h1 font-semibold">Account Settings</h1>
      <ProfileSection />
      <PasswordSection />
      <NotificationSection />
      <AppearanceSection />
    </div>
  )
}

function ProfileSection() {
  const user = useUser()
  const [fullName, setFullName] = useState(user?.full_name ?? '')

  const save = useMutation({
    mutationFn: () => updateMe({ full_name: fullName.trim() }),
    onSuccess: () => toast('Profile updated', 'success'),
    onError: (err) =>
      toast(err instanceof ApiError ? err.message : 'Could not update your profile', 'error'),
  })

  return (
    <Card className="flex flex-col gap-16">
      <h2 className="font-display text-h3 font-semibold">Profile</h2>
      <Input
        label="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        validate={(v) => (v.trim() ? null : 'Your name cannot be empty.')}
      />
      {/* Email is the login identifier and the notification address; changing it
          needs re-verification, which is out of scope for the prototype. */}
      <Input
        label="Email"
        value={user?.email ?? ''}
        disabled
        readOnly
        hint="Contact an administrator to change your email."
      />
      <div className="flex justify-end">
        <Button
          variant="primary"
          disabled={!fullName.trim() || save.isPending}
          onClick={() => save.mutate()}
        >
          Save changes
        </Button>
      </div>
    </Card>
  )
}

function PasswordSection() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (next !== confirm) {
      setError('The new passwords do not match.')
      return
    }
    setSaving(true)
    try {
      await api('/auth/password-change', {
        method: 'POST',
        json: { current_password: current, new_password: next },
      })
      setCurrent('')
      setNext('')
      setConfirm('')
      // The server revokes every other session on a password change (TRD §9);
      // this tab keeps its access token, so the user stays signed in here.
      toast('Password updated — other devices have been signed out', 'success')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update your password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="flex flex-col gap-16">
      <h2 className="font-display text-h3 font-semibold">Password</h2>
      <form onSubmit={onSubmit} className="flex flex-col gap-16" noValidate>
        <Input
          label="Current password"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          validate={(v) => (v.length >= 8 ? null : 'Use at least 8 characters.')}
        />
        <Input
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-body-sm text-critical">
            {error}
          </p>
        )}
        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            disabled={!current || next.length < 8 || !confirm || saving}
          >
            Update password
          </Button>
        </div>
      </form>
    </Card>
  )
}

function NotificationSection() {
  // The stored shape is {trigger: {email: bool, in_app: bool}}. Unset means the
  // backend default applies, so an unchecked box is only written once touched.
  const [prefs, setPrefs] = useState<Record<string, { email: boolean; in_app: boolean }>>({})
  const [touched, setTouched] = useState(false)

  const save = useMutation({
    mutationFn: () =>
      api('/notifications/preferences', { method: 'PATCH', json: { preferences: prefs } }),
    onSuccess: () => toast('Notification preferences saved', 'success'),
    onError: (err) =>
      toast(err instanceof ApiError ? err.message : 'Could not save preferences', 'error'),
  })

  function toggle(trigger: NotificationTrigger, channel: 'email' | 'in_app') {
    setTouched(true)
    setPrefs((current) => {
      const existing = current[trigger] ?? { email: true, in_app: true }
      return { ...current, [trigger]: { ...existing, [channel]: !existing[channel] } }
    })
  }

  function isOn(trigger: NotificationTrigger, channel: 'email' | 'in_app') {
    return prefs[trigger]?.[channel] ?? true
  }

  return (
    <Card className="flex flex-col gap-16">
      <h2 className="font-display text-h3 font-semibold">Notifications</h2>
      <p className="text-body-sm text-muted">Choose how you'd like to hear from us.</p>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-border border-b">
              <th className="text-caption text-muted py-12 text-left tracking-wide uppercase">
                When
              </th>
              <th className="text-caption text-muted py-12 tracking-wide uppercase">Email</th>
              <th className="text-caption text-muted py-12 tracking-wide uppercase">In-app</th>
            </tr>
          </thead>
          <tbody>
            {NOTIFICATION_TRIGGERS.map((trigger) => (
              <tr key={trigger} className="border-border border-b last:border-0">
                <td className="text-body py-12">{TRIGGER_LABELS[trigger]}</td>
                {(['email', 'in_app'] as const).map((channel) => (
                  <td key={channel} className="py-12 text-center">
                    <input
                      type="checkbox"
                      checked={isOn(trigger, channel)}
                      onChange={() => toggle(trigger, channel)}
                      aria-label={`${TRIGGER_LABELS[trigger]} — ${channel === 'email' ? 'email' : 'in-app'}`}
                      className={cn(
                        'size-[20px] cursor-pointer accent-[var(--color-brand-start)]',
                        focusRing,
                      )}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end">
        <Button
          variant="primary"
          disabled={!touched || save.isPending}
          onClick={() => save.mutate()}
        >
          Save preferences
        </Button>
      </div>
    </Card>
  )
}

function AppearanceSection() {
  const { mode, toggle } = useTheme()

  return (
    <Card className="flex flex-wrap items-center justify-between gap-16">
      <div>
        <h2 className="font-display text-h3 font-semibold">Appearance</h2>
        <p className="text-body-sm text-muted mt-4">
          Currently using {mode} mode. Your choice is saved to your account.
        </p>
      </div>
      <Button onClick={() => void toggle()}>
        {mode === 'dark' ? (
          <Sun aria-hidden size={16} strokeWidth={1.5} />
        ) : (
          <Moon aria-hidden size={16} strokeWidth={1.5} />
        )}
        Switch to {mode === 'dark' ? 'light' : 'dark'} mode
      </Button>
    </Card>
  )
}
