import { Check, Rocket } from 'lucide-react'
import { Link, Navigate, useLocation } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { Skeleton } from '../../components/Skeleton'
import {
  isSystemReady,
  setupProgress,
  setupSteps,
  type SetupCounts,
  type SetupStep,
} from '../../lib/admin'
import { useAllUsers, useCategories, usePriorities, useSlaRules, useTeams } from '../../lib/queries'
import { cn, focusRing } from '../../lib/ui'
import { CategoryCreateForm, PriorityCreateForm } from './TicketConfig'
import { SlaRuleForm } from './Sla'
import { InviteUserForm, TeamCreateForm } from './Users'

/**
 * What the §26 checklist is measured against. All five reads are cached
 * elsewhere on the dashboard, so asking for them here costs nothing extra.
 */
function useSetupCounts(): { counts: SetupCounts | null; loading: boolean } {
  const teams = useTeams()
  const categories = useCategories()
  const priorities = usePriorities()
  const slaRules = useSlaRules()
  const users = useAllUsers()

  const queries = [teams, categories, priorities, slaRules, users]
  if (queries.some((q) => q.isPending)) return { counts: null, loading: true }

  return {
    loading: false,
    counts: {
      teams: teams.data?.length ?? 0,
      categories: categories.data?.length ?? 0,
      priorities: priorities.data?.length ?? 0,
      slaRules: slaRules.data?.length ?? 0,
      staff: (users.data ?? []).filter((u) => u.role !== 'requester' && u.is_active).length,
    },
  }
}

/**
 * Shown on the Admin Overview until the system is configured (App Flow §26).
 *
 * On a genuinely brand-new deployment — no teams *and* no categories — it does
 * not ask, it redirects: §26 says the journey "runs once, on the very first
 * Admin login", and an empty metrics dashboard is not a useful thing to land on.
 * Once anything exists, it degrades to a banner so a half-configured system is
 * never a modal wall in front of the data.
 */
export function SetupBanner() {
  const { pathname } = useLocation()
  const { counts, loading } = useSetupCounts()

  if (loading || !counts) return null
  if (isSystemReady(counts)) return null
  if (pathname.startsWith('/admin/setup')) return null

  if (counts.teams === 0 && counts.categories === 0) {
    return <Navigate to="/admin/setup" replace />
  }

  const progress = setupProgress(counts)
  return (
    <Card className="mt-24">
      <div className="flex flex-wrap items-center justify-between gap-16">
        <div>
          <h2 className="text-h3 font-display font-semibold">Finish setting up</h2>
          <p className="text-body-sm text-muted mt-4">
            The Customer Portal can take tickets, but until every step is done they arrive with no
            deadline and no queue.
          </p>
        </div>
        <Link to="/admin/setup" className={cn('shrink-0', focusRing)}>
          <Button variant="primary">Continue setup — {progress}%</Button>
        </Link>
      </div>
    </Card>
  )
}

/**
 * First-Time Admin Setup (App Flow §26), as one scrolling checklist rather than
 * a stepper: every step's form is the same component its permanent home screen
 * uses, so nothing here is a second implementation that can drift, and an Admin
 * can jump straight to whichever step is still outstanding.
 */
export function FirstTimeSetup() {
  const { counts, loading } = useSetupCounts()
  const teams = useTeams()

  if (loading || !counts) return <Skeleton className="h-[400px]" />

  const steps = setupSteps(counts)
  const ready = isSystemReady(counts)
  const progress = setupProgress(counts)

  const forms: Record<SetupStep['id'], React.ReactNode> = {
    teams: <TeamCreateForm />,
    categories: <CategoryCreateForm />,
    priorities: <PriorityCreateForm />,
    slaRules: <SlaRuleForm />,
    staff: <InviteUserForm teams={teams.data ?? []} />,
  }

  return (
    <div className="mx-auto max-w-[960px]">
      <h1 className="font-display text-h1 font-semibold">Set up AgentDesk</h1>
      <p className="text-body text-muted mt-8">
        Five things stand between an empty deployment and a working help desk. Each one is the same
        form as its permanent screen, so nothing has to be redone later.
      </p>

      <div className="mt-24">
        <div className="flex items-center justify-between gap-16">
          <span className="text-body-sm text-muted">{progress}% complete</span>
          {ready && (
            <span className="text-body-sm text-success font-medium">Ready to take tickets</span>
          )}
        </div>
        {/* The one gradient on this screen — Doc 04 allows it on progress toward
            a goal no more than it does anywhere else, so this stays a flat fill. */}
        <div className="bg-surface rounded-pill mt-8 h-[8px] overflow-hidden">
          <div
            className="bg-brand-start h-full transition-[width] duration-normal"
            style={{ width: `${progress}%` }}
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Setup progress"
          />
        </div>
      </div>

      <ol className="mt-24 flex flex-col gap-16">
        {steps.map((step, index) => (
          <li key={step.id}>
            <Card>
              <div className="flex items-start gap-16">
                <span
                  aria-hidden
                  className={cn(
                    'rounded-pill flex size-[28px] shrink-0 items-center justify-center text-sm font-medium',
                    step.done ? 'bg-success text-white' : 'border-border text-muted border',
                  )}
                >
                  {step.done ? <Check size={14} strokeWidth={2} /> : index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <h2 className="text-h3 font-display font-semibold">
                    {step.label}
                    {step.done && (
                      <span className="text-body-sm text-muted ml-8 font-normal">Done</span>
                    )}
                  </h2>
                  {forms[step.id]}
                </div>
              </div>
            </Card>
          </li>
        ))}
      </ol>

      <Card className="mt-24">
        <div className="flex flex-wrap items-center justify-between gap-16">
          <div>
            <h2 className="text-h3 font-display font-semibold">Automation rules</h2>
            <p className="text-body-sm text-muted mt-4">
              Optional at this stage (§26 step 6) — add them once you have seen real tickets arrive.
            </p>
          </div>
          <Link to="/admin/automation" className={cn('shrink-0', focusRing)}>
            <Button>Open automation</Button>
          </Link>
        </div>
      </Card>

      <Card className="mt-24">
        <div className="flex flex-wrap items-center gap-16">
          <Rocket
            size={20}
            strokeWidth={1.5}
            aria-hidden
            className={ready ? 'text-success' : 'text-muted'}
          />
          <div className="min-w-0 flex-1">
            <h2 className="text-h3 font-display font-semibold">
              {ready ? 'System ready' : 'Not ready yet'}
            </h2>
            <p className="text-body-sm text-muted mt-4">
              {ready
                ? 'Requesters can submit tickets, and the pipeline has a taxonomy, a queue and an SLA to route them against.'
                : 'A ticket submitted now would get no priority, no deadline and no queue until the remaining steps are done.'}
            </p>
          </div>
          <Link to="/admin" className={cn('shrink-0', focusRing)}>
            <Button variant={ready ? 'primary' : 'secondary'}>Go to Overview</Button>
          </Link>
        </div>
      </Card>
    </div>
  )
}
