import {
  Bell,
  BookOpen,
  Bot,
  FileText,
  Gauge,
  Inbox,
  LayoutDashboard,
  ListChecks,
  Plus,
  ScrollText,
  Settings,
  Ticket,
  Timer,
  Users,
  Webhook,
  Workflow,
  type LucideIcon,
} from 'lucide-react'

import type { Role } from '../lib/session'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

export interface NavGroup {
  /** Undefined for the primary group, which needs no heading. */
  heading?: string
  items: NavItem[]
}

// App Flow Doc 03 §1–2. Requesters get a minimal four-item sidebar; agents get
// queue-oriented items; admins get the full configuration set.
const REQUESTER: NavGroup[] = [
  {
    items: [
      { to: '/portal/tickets', label: 'My Tickets', icon: Ticket },
      { to: '/portal/tickets/new', label: 'New Ticket', icon: Plus },
      { to: '/portal/kb', label: 'Knowledge Base', icon: BookOpen },
      { to: '/portal/notifications', label: 'Notifications', icon: Bell },
    ],
  },
]

const AGENT: NavGroup[] = [
  {
    items: [
      { to: '/agent/queue', label: 'Ticket Queue', icon: Inbox },
      { to: '/agent/views', label: 'Saved Views', icon: ListChecks },
      { to: '/agent/kb', label: 'Knowledge Base', icon: BookOpen },
    ],
  },
]

// Team Lead = Agent plus team oversight. Doc 03 §9 is explicit that a plain
// Agent must not merely be blocked from these — the items are absent.
const TEAM_LEAD: NavGroup[] = [
  ...AGENT,
  {
    heading: 'Team',
    items: [
      { to: '/agent/workload', label: 'Team Workload', icon: Users },
      { to: '/agent/reports', label: 'Team Reports', icon: Gauge },
    ],
  },
]

const ADMIN: NavGroup[] = [
  {
    items: [
      { to: '/admin', label: 'Overview', icon: LayoutDashboard },
      { to: '/admin/users', label: 'Users & Teams', icon: Users },
    ],
  },
  {
    heading: 'Configuration',
    items: [
      { to: '/admin/tickets', label: 'Ticket Configuration', icon: Settings },
      { to: '/admin/sla', label: 'SLA Rules', icon: Timer },
      { to: '/admin/automation', label: 'Automation Rules', icon: Workflow },
      { to: '/admin/templates', label: 'Templates & Branding', icon: FileText },
      { to: '/admin/webhooks', label: 'Webhooks', icon: Webhook },
    ],
  },
  {
    heading: 'Insight',
    items: [
      { to: '/admin/reports', label: 'Reports & Analytics', icon: Gauge },
      { to: '/admin/ai', label: 'AI Performance', icon: Bot },
      { to: '/admin/audit', label: 'Audit Log', icon: ScrollText },
      { to: '/admin/kb', label: 'Knowledge Base', icon: BookOpen },
    ],
  },
]

export function navFor(role: Role): NavGroup[] {
  switch (role) {
    case 'requester':
      return REQUESTER
    case 'agent':
      return AGENT
    case 'team_lead':
      return TEAM_LEAD
    case 'admin':
      return ADMIN
  }
}

/** Mobile bottom tab bar — Customer Portal only, per Doc 04. */
export const PORTAL_TABS = REQUESTER[0].items
