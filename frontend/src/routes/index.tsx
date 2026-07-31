import { Navigate, Route, Routes } from 'react-router'

import { HOME_BY_ROLE, useUser } from '../lib/auth'
import { Login } from '../pages/Login'
import { Placeholder } from '../pages/Placeholder'
import { ForgotPassword, ResetPassword, SignUp, VerifyEmail } from '../pages/SignUp'
import { AccountSettings } from '../pages/portal/AccountSettings'
import { KbArticleDetail, KnowledgeBaseSearch } from '../pages/portal/KnowledgeBase'
import { MyTickets } from '../pages/portal/MyTickets'
import { NewTicket } from '../pages/portal/NewTicket'
import { Notifications } from '../pages/portal/Notifications'
import { TicketDetail } from '../pages/portal/TicketDetail'
import { AppShell } from '../shell/AppShell'
import { RequireAuth } from './RequireAuth'

/**
 * Phase 9 builds the shell, not the screens: every route below the three
 * surfaces renders a placeholder until its phase lands. The structure is what
 * matters here — the role guards, the per-surface shell, and the redirects.
 */
function RoleHome() {
  const user = useUser()
  return <Navigate to={user ? HOME_BY_ROLE[user.role] : '/login'} replace />
}

export function AppRoutes() {
  return (
    <Routes>
      {/* First-touch surfaces — light-themed, outside the app shell. */}
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<SignUp />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      {/* Customer Portal — light-first, bottom tab bar on mobile. Admins are
          allowed in too: Doc 03 §9 gives them every surface for support. */}
      <Route element={<RequireAuth roles={['requester', 'admin']} />}>
        <Route element={<AppShell basePath="/portal" searchPlaceholder="Search your tickets…" />}>
          <Route path="/portal/tickets" element={<MyTickets />} />
          <Route path="/portal/tickets/new" element={<NewTicket />} />
          <Route path="/portal/tickets/:ticketId" element={<TicketDetail />} />
          <Route path="/portal/kb" element={<KnowledgeBaseSearch />} />
          <Route path="/portal/kb/:articleId" element={<KbArticleDetail />} />
          <Route path="/portal/notifications" element={<Notifications />} />
          <Route path="/portal/settings" element={<AccountSettings />} />
        </Route>
      </Route>

      {/* Agent Console — dark-first. Team Lead extras are gated inside. */}
      <Route element={<RequireAuth roles={['agent', 'team_lead', 'admin']} />}>
        <Route element={<AppShell basePath="/agent" searchPlaceholder="Search tickets…" />}>
          <Route
            path="/agent/queue"
            element={<Placeholder title="Ticket Queue" phase="Phase 11" />}
          />
          <Route
            path="/agent/tickets/:ticketId"
            element={<Placeholder title="Ticket Detail" phase="Phase 11" />}
          />
          <Route
            path="/agent/views"
            element={<Placeholder title="Saved Views" phase="Phase 11" />}
          />
          <Route
            path="/agent/kb"
            element={<Placeholder title="Knowledge Base" phase="Phase 11" />}
          />
          <Route
            path="/agent/notifications"
            element={<Placeholder title="Notifications" phase="Phase 11" />}
          />
          <Route
            path="/agent/settings"
            element={<Placeholder title="Account Settings" phase="Phase 11" />}
          />
          {/* Team Lead only — a plain Agent has no sidebar entry for these and
              is bounced by the guard if they type the URL. */}
          <Route element={<RequireAuth roles={['team_lead', 'admin']} />}>
            <Route
              path="/agent/workload"
              element={<Placeholder title="Team Workload" phase="Phase 11" />}
            />
            <Route
              path="/agent/reports"
              element={<Placeholder title="Team Reports" phase="Phase 11" />}
            />
          </Route>
        </Route>
      </Route>

      {/* Admin Dashboard — dark-first. */}
      <Route element={<RequireAuth roles={['admin']} />}>
        <Route element={<AppShell basePath="/admin" searchPlaceholder="Search tickets…" />}>
          <Route path="/admin" element={<Placeholder title="Admin Overview" phase="Phase 12" />} />
          <Route
            path="/admin/users"
            element={<Placeholder title="Users & Teams" phase="Phase 12" />}
          />
          <Route
            path="/admin/tickets"
            element={<Placeholder title="Ticket Configuration" phase="Phase 12" />}
          />
          <Route path="/admin/sla" element={<Placeholder title="SLA Rules" phase="Phase 12" />} />
          <Route
            path="/admin/automation"
            element={<Placeholder title="Automation Rules" phase="Phase 12" />}
          />
          <Route
            path="/admin/templates"
            element={<Placeholder title="Templates & Branding" phase="Phase 12" />}
          />
          <Route
            path="/admin/webhooks"
            element={<Placeholder title="Webhooks" phase="Phase 12" />}
          />
          <Route
            path="/admin/reports"
            element={<Placeholder title="Reports & Analytics" phase="Phase 12" />}
          />
          <Route
            path="/admin/ai"
            element={<Placeholder title="AI Performance" phase="Phase 12" />}
          />
          <Route path="/admin/audit" element={<Placeholder title="Audit Log" phase="Phase 12" />} />
          <Route
            path="/admin/kb"
            element={<Placeholder title="Knowledge Base" phase="Phase 12" />}
          />
          <Route
            path="/admin/notifications"
            element={<Placeholder title="Notifications" phase="Phase 12" />}
          />
          <Route
            path="/admin/settings"
            element={<Placeholder title="Account Settings" phase="Phase 12" />}
          />
        </Route>
      </Route>

      {/* No shared home screen exists — "/" resolves by role (Doc 03 §3). */}
      <Route path="/" element={<RoleHome />} />
      <Route path="*" element={<RoleHome />} />
    </Routes>
  )
}
