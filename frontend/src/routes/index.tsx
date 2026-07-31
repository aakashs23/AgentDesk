import { Navigate, Route, Routes } from 'react-router'

import { HOME_BY_ROLE, useUser } from '../lib/auth'
import { Login } from '../pages/Login'
import { ForgotPassword, ResetPassword, SignUp, VerifyEmail } from '../pages/SignUp'
import { AiPerformance } from '../pages/admin/AiPerformance'
import { AuditLog } from '../pages/admin/AuditLog'
import { AutomationRules } from '../pages/admin/Automation'
import { AdminOverview } from '../pages/admin/Overview'
import { AdminReports } from '../pages/admin/Reports'
import { FirstTimeSetup } from '../pages/admin/Setup'
import { SlaRules } from '../pages/admin/Sla'
import { TemplatesAndBranding } from '../pages/admin/Templates'
import { TicketConfiguration } from '../pages/admin/TicketConfig'
import { UsersAndTeams } from '../pages/admin/Users'
import { Webhooks } from '../pages/admin/Webhooks'
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
 * guards, per-surface shell, redirects — with placeholders behind it; Phases
 * 10–12 filled in the Customer Portal, the Agent Console and the Admin
 * Dashboard in turn — every route below renders a real screen.
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

      {/* Admin Dashboard — dark-first. Phase 12. */}
      <Route element={<RequireAuth roles={['admin']} />}>
        <Route element={<AppShell basePath="/admin" searchPlaceholder="Search tickets…" />}>
          <Route path="/admin" element={<AdminOverview />} />
          {/* App Flow §26 — the Overview redirects here on an empty deployment. */}
          <Route path="/admin/setup" element={<FirstTimeSetup />} />
          <Route path="/admin/users" element={<UsersAndTeams />} />
          <Route path="/admin/tickets" element={<TicketConfiguration />} />
          <Route path="/admin/sla" element={<SlaRules />} />
          <Route path="/admin/automation" element={<AutomationRules />} />
          <Route path="/admin/templates" element={<TemplatesAndBranding />} />
          <Route path="/admin/webhooks" element={<Webhooks />} />
          <Route path="/admin/reports" element={<AdminReports />} />
          <Route path="/admin/ai" element={<AiPerformance />} />
          <Route path="/admin/audit" element={<AuditLog />} />
          {/* Knowledge Base Management is the Agent Console's KB screens with an
              Admin asking: same API, wider scope, plus delete. */}
          <Route path="/admin/kb" element={<AgentKnowledgeBase />} />
          <Route path="/admin/kb/new" element={<KbArticleEditor />} />
          <Route path="/admin/kb/:articleId" element={<AgentKbArticle />} />
          <Route path="/admin/kb/:articleId/edit" element={<KbArticleEditor />} />
          {/* Surface-agnostic, as on the other two surfaces. */}
          <Route path="/admin/notifications" element={<Notifications />} />
          <Route path="/admin/settings" element={<AccountSettings />} />
        </Route>
      </Route>

      {/* No shared home screen exists — "/" resolves by role (Doc 03 §3). */}
      <Route path="/" element={<RoleHome />} />
      <Route path="*" element={<RoleHome />} />
    </Routes>
  )
}
