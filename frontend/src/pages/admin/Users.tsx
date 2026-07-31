import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Plus, UserPlus, Users as UsersIcon } from 'lucide-react'
import { useState } from 'react'

import { Avatar } from '../../components/Avatar'
import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { Select } from '../../components/Select'
import { ConfirmModal, Modal } from '../../components/Modal'
import { SkeletonRows } from '../../components/Skeleton'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import { humanise } from '../../lib/admin'
import { useUser } from '../../lib/auth'
import { useDebounced } from '../../lib/hooks'
import { useAllUsers, useTeams } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { DirectoryUser, Team } from '../../lib/types'
import { cn, focusRing } from '../../lib/ui'

const ROLES = ['requester', 'agent', 'team_lead', 'admin'] as const

/**
 * User & Team Management (Doc 03 §1, §24). Both halves live on one screen
 * because they are one decision: a user's team is what decides which queues and
 * tickets they can see, so creating the team and assigning it belong together.
 */
export function UsersAndTeams() {
  const [tab, setTab] = useState('users')
  const teams = useTeams()

  return (
    <div className="mx-auto max-w-[1440px]">
      <h1 className="font-display text-h1 font-semibold">Users &amp; Teams</h1>
      <p className="text-body text-muted mt-8">
        Provision accounts, set roles, and decide who sees which queues.
      </p>

      <div className="mt-24">
        <Tabs
          active={tab}
          onChange={setTab}
          tabs={[
            { id: 'users', label: 'Users' },
            { id: 'teams', label: 'Teams', badge: teams.data?.length },
          ]}
        />
      </div>

      {tab === 'users' ? <UserList teams={teams.data ?? []} /> : <TeamList />}
    </div>
  )
}

// --- Users ------------------------------------------------------------------

function UserList({ teams }: { teams: Team[] }) {
  const users = useAllUsers()
  const [search, setSearch] = useState('')
  const [role, setRole] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [inviting, setInviting] = useState(false)
  const [editing, setEditing] = useState<DirectoryUser | null>(null)
  const term = useDebounced(search.trim().toLowerCase(), 300)

  const visible = (users.data ?? []).filter(
    (u) =>
      (showInactive || u.is_active) &&
      (!role || u.role === role) &&
      (!term || u.full_name.toLowerCase().includes(term) || u.email.toLowerCase().includes(term)),
  )

  return (
    <>
      <div className="mt-24 flex flex-wrap items-end gap-16">
        <label className="flex flex-1 flex-col gap-8 sm:max-w-[320px]">
          <span className="text-body-sm text-muted font-medium">Search</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name or email…"
            className={cn(
              'rounded-control border-border bg-canvas text-ink h-[44px] w-full border px-12',
              'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
              focusRing,
            )}
          />
        </label>
        <Select label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {humanise(r)}
            </option>
          ))}
        </Select>
        <label className="flex h-[44px] items-center gap-8">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className={cn('accent-brand-start size-[16px]', focusRing)}
          />
          <span className="text-body-sm">Show deactivated</span>
        </label>
        <Button
          variant="primary"
          icon={<UserPlus size={16} strokeWidth={1.5} />}
          onClick={() => setInviting(true)}
        >
          Invite user
        </Button>
      </div>

      <div className="mt-24">
        {users.isPending && <SkeletonRows rows={6} />}
        {users.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load users"
            onRetry={() => void users.refetch()}
          />
        )}
        {users.isSuccess && visible.length === 0 && (
          <EmptyState icon={UsersIcon} title="Nobody matches those filters" />
        )}

        <ul className="flex flex-col gap-8">
          {visible.map((user) => (
            <li key={user.id}>
              <Card className="flex flex-wrap items-center gap-16 p-16">
                <Avatar name={user.full_name} />
                <div className="min-w-0 flex-1">
                  <p className="text-body text-ink truncate font-medium">
                    {user.full_name}
                    {!user.is_active && (
                      <span className="text-caption text-muted ml-8 tracking-wide uppercase">
                        Deactivated
                      </span>
                    )}
                  </p>
                  <p className="text-body-sm text-muted truncate">{user.email}</p>
                </div>
                <span className="text-body-sm text-muted">{humanise(user.role)}</span>
                <span className="text-body-sm text-muted min-w-[120px]">
                  {teams.find((t) => t.id === user.team_id)?.name ?? 'No team'}
                </span>
                <Button size="sm" onClick={() => setEditing(user)}>
                  Manage
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      <Modal open={inviting} onClose={() => setInviting(false)} title="Invite a user">
        <InviteUserForm teams={teams} onDone={() => setInviting(false)} />
      </Modal>

      {editing && <ManageUserModal user={editing} teams={teams} onClose={() => setEditing(null)} />}
    </>
  )
}

/**
 * App Flow §24 steps 1–4: create, assign a role, assign a team, invite email.
 * Exported because First-Time Admin Setup's last step is exactly this form.
 */
export function InviteUserForm({ teams, onDone }: { teams: Team[]; onDone?: () => void }) {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<string>('agent')
  const [teamId, setTeamId] = useState('')

  const invite = useMutation({
    mutationFn: () =>
      api<DirectoryUser>('/users', {
        method: 'POST',
        json: {
          email: email.trim(),
          full_name: fullName.trim(),
          role,
          team_id: teamId || null,
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['users'] })
      toast('Invite sent — they set their own password', 'success')
      setEmail('')
      setFullName('')
      onDone?.()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not invite', 'error'),
  })

  return (
    <div className="flex flex-col gap-16">
      <Input
        label="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        autoComplete="off"
      />
      <Input
        label="Email"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        autoComplete="off"
      />
      <Select label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {humanise(r)}
          </option>
        ))}
      </Select>
      <Select label="Team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
        <option value="">No team</option>
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {team.name}
          </option>
        ))}
      </Select>
      <p className="text-body-sm text-muted">
        Requesters normally self-register; this path is for Agents, Team Leads and Admins.
      </p>
      <div className="flex justify-end">
        <Button
          variant="primary"
          disabled={!email.trim() || !fullName.trim() || invite.isPending}
          onClick={() => invite.mutate()}
        >
          Send invite
        </Button>
      </div>
    </div>
  )
}

/** Change role, change team, deactivate/reactivate — App Flow §24's four
 *  ongoing admin actions, in one place because they share a target. */
function ManageUserModal({
  user,
  teams,
  onClose,
}: {
  user: DirectoryUser
  teams: Team[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const me = useUser()
  const [role, setRole] = useState(user.role)
  const [teamId, setTeamId] = useState(user.team_id ?? '')
  const [confirming, setConfirming] = useState(false)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['users'] })

  const save = useMutation({
    mutationFn: () =>
      api<DirectoryUser>(`/users/${user.id}`, {
        method: 'PATCH',
        json: { role, team_id: teamId || null },
      }),
    onSuccess: async () => {
      await invalidate()
      toast('Saved — it applies on their next request', 'success')
      onClose()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  // Reactivate is a PATCH, deactivate is the DELETE — Doc 05 has no hard user
  // delete, so `DELETE /users/{id}` is the soft one (App Flow §24).
  const setActive = useMutation({
    mutationFn: async (active: boolean) => {
      if (active) {
        await api<DirectoryUser>(`/users/${user.id}`, {
          method: 'PATCH',
          json: { is_active: true },
        })
      } else {
        await api<void>(`/users/${user.id}`, { method: 'DELETE' })
      }
    },
    onSuccess: async (_data, active) => {
      await invalidate()
      toast(active ? 'Account reactivated' : 'Account deactivated', 'success')
      setConfirming(false)
      onClose()
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not change status', 'error'),
  })

  // Removing your own admin role, or deactivating yourself, locks you out of the
  // screen you would need to undo it.
  const isSelf = me?.id === user.id

  return (
    <>
      <Modal open onClose={onClose} title={user.full_name}>
        <div className="flex flex-col gap-16">
          <p className="text-body-sm text-muted">{user.email}</p>
          <Select
            label="Role"
            value={role}
            disabled={isSelf}
            onChange={(e) => setRole(e.target.value)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {humanise(r)}
              </option>
            ))}
          </Select>
          <Select label="Team" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">No team</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </Select>
          {isSelf && (
            <p className="text-body-sm text-muted">
              You cannot change your own role or deactivate yourself — ask another Admin.
            </p>
          )}
          <p className="text-body-sm text-muted">
            A role change takes effect on their next request; a team change moves which queues they
            can see. Deactivating releases the tickets assigned to them.
          </p>

          <div className="flex flex-wrap justify-between gap-8">
            {user.is_active ? (
              <Button variant="danger" disabled={isSelf} onClick={() => setConfirming(true)}>
                Deactivate
              </Button>
            ) : (
              <Button disabled={setActive.isPending} onClick={() => setActive.mutate(true)}>
                Reactivate
              </Button>
            )}
            <div className="flex gap-8">
              <Button onClick={onClose}>Cancel</Button>
              <Button variant="primary" disabled={save.isPending} onClick={() => save.mutate()}>
                Save
              </Button>
            </div>
          </div>
        </div>
      </Modal>

      <ConfirmModal
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={() => setActive.mutate(false)}
        title="Deactivate this account?"
        message={`${user.full_name} will be signed out and unable to log in. Tickets assigned to them are released for reassignment.`}
        confirmLabel="Deactivate"
        destructive
      />
    </>
  )
}

// --- Teams ------------------------------------------------------------------

function TeamList() {
  const teams = useTeams()
  const users = useAllUsers()
  const queryClient = useQueryClient()
  const [deleting, setDeleting] = useState<Team | null>(null)
  const [renaming, setRenaming] = useState<Team | null>(null)
  const [name, setName] = useState('')

  const rename = useMutation({
    mutationFn: (team: Team) =>
      api<Team>(`/admin/teams/${team.id}`, { method: 'PATCH', json: { name: name.trim() } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast('Team renamed', 'success')
      setRenaming(null)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not rename', 'error'),
  })

  const remove = useMutation({
    mutationFn: (team: Team) => api<void>(`/admin/teams/${team.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast('Team deleted', 'success')
      setDeleting(null)
    },
    // A 409 here is the API refusing to orphan members or queues — show it verbatim.
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  const memberCount = (teamId: string) =>
    (users.data ?? []).filter((u) => u.team_id === teamId && u.is_active).length

  return (
    <>
      <Card className="mt-24">
        <h2 className="text-h3 font-display font-semibold">New team</h2>
        <TeamCreateForm />
      </Card>

      <div className="mt-24">
        {teams.isPending && <SkeletonRows rows={3} />}
        {teams.isSuccess && teams.data.length === 0 && (
          <EmptyState
            icon={UsersIcon}
            title="No teams yet"
            message="A queue belongs to a team, and a team is what scopes an agent's visibility."
          />
        )}
        <ul className="flex flex-col gap-8">
          {(teams.data ?? []).map((team) => (
            <li key={team.id}>
              <Card className="flex flex-wrap items-center gap-16 p-16">
                <div className="min-w-0 flex-1">
                  <p className="text-body text-ink truncate font-medium">{team.name}</p>
                  <p className="text-body-sm text-muted">
                    {memberCount(team.id)} active member{memberCount(team.id) === 1 ? '' : 's'}
                  </p>
                </div>
                <Button
                  size="sm"
                  onClick={() => {
                    setName(team.name)
                    setRenaming(team)
                  }}
                >
                  Rename
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleting(team)}>
                  Delete
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      </div>

      <Modal open={Boolean(renaming)} onClose={() => setRenaming(null)} title="Rename team">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="mt-24 flex justify-end gap-8">
          <Button onClick={() => setRenaming(null)}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!name.trim() || rename.isPending}
            onClick={() => renaming && rename.mutate(renaming)}
          >
            Save
          </Button>
        </div>
      </Modal>

      <ConfirmModal
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting)}
        title="Delete this team?"
        message="Only possible while no user and no queue still belongs to it."
        confirmLabel="Delete"
        destructive
      />
    </>
  )
}

/** Exported for First-Time Admin Setup step 2 (App Flow §26). */
export function TeamCreateForm({ onCreated }: { onCreated?: (team: Team) => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')

  const create = useMutation({
    mutationFn: () => api<Team>('/admin/teams', { method: 'POST', json: { name: name.trim() } }),
    onSuccess: async (team) => {
      await queryClient.invalidateQueries({ queryKey: ['teams'] })
      toast(`Team “${team.name}” created`, 'success')
      setName('')
      onCreated?.(team)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not create team', 'error'),
  })

  return (
    <div className="mt-16 flex flex-wrap items-end gap-16">
      <div className="min-w-[240px] flex-1">
        <Input
          label="Team name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Support, Billing, Infrastructure…"
        />
      </div>
      <Button
        variant="primary"
        icon={<Plus size={16} strokeWidth={1.5} />}
        disabled={!name.trim() || create.isPending}
        onClick={() => create.mutate()}
      >
        Add team
      </Button>
    </div>
  )
}
