import { Navigate, Route, Routes } from 'react-router'

import { HOME_BY_ROLE, useUser } from '../lib/auth'
import { Login } from '../pages/Login'
import { Placeholder } from '../pages/Placeholder'
import { ForgotPassword, ResetPassword, SignUp, VerifyEmail } from '../pages/SignUp'
import { AgentKbArticle, AgentKnowledgeBase, KbArticleEditor } from '../pages/agent/KnowledgeBase'
import { Queue } from '../pages/agent/Queue'
import { SavedViews } from '../pages/agent/SavedViews'
import { TeamReports, TeamWorkload } from '../pages/agent/Team'
import { AgentTicketDetail } from '../pages/agent/TicketDetail'
import { AccountSettings } from '../pages/portal/AccountSettings'
import { KbArticleDetail, KnowledgeBaseSearch } from '../pages/portal/KnowledgeBase'
import { MyTickets } from '../pages/portal/MyTickets'
import { NewTicket } from '../pages/portal/NewTicket'
import { Notifications } from '../pages/portal/Notifications'
import { TicketDetail } from '../pages/portal/TicketDetail'
import { AppShell } from '../shell/AppShell'
import { RequireAuth } from './RequireAuth'

/**
 * The route table for all three surfaces. Phase 9 built the structure — role
 * guards, per-surface shell, redirects — with placeholders behind it; Phase 10
 * filled in the Customer Portal and Phase 11 the Agent Console. Only `/admin`
 * still renders placeholders, until Phase 12.
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
          <Route path="/agent/queue" element={<Queue />} />
          <Route path="/agent/tickets/:ticketId" element={<AgentTicketDetail />} />
          <Route path="/agent/views" element={<SavedViews />} />
          <Route path="/agent/kb" element={<AgentKnowledgeBase />} />
          {/* `new` before `:articleId`, or the editor is never reached. */}
          <Route path="/agent/kb/new" element={<KbArticleEditor />} />
          <Route path="/agent/kb/:articleId" element={<AgentKbArticle />} />
          <Route path="/agent/kb/:articleId/edit" element={<KbArticleEditor />} />
          {/* Notifications and Account Settings are surface-agnostic: they read
              their deep-link prefix from the URL, so one copy serves all three. */}
          <Route path="/agent/notifications" element={<Notifications />} />
          <Route path="/agent/settings" element={<AccountSettings />} />
          {/* Team Lead only — a plain Agent has no sidebar entry for these and
              is bounced by the guard if they type the URL. */}
          <Route element={<RequireAuth roles={['team_lead', 'admin']} />}>
            <Route path="/agent/workload" element={<TeamWorkload />} />
            <Route path="/agent/reports" element={<TeamReports />} />
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
