import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router'

import { api } from './api'
import type {
  AiInsights,
  Category,
  DirectoryUser,
  Priority,
  Queue,
  SlaRule,
  Team,
  Ticket,
} from './types'

/**
 * Shared reads. Taxonomy barely changes within a session, so it is cached hard
 * rather than refetched per screen — the New Ticket form and every ticket row
 * need the same two lists.
 */
const STATIC = { staleTime: 10 * 60_000, gcTime: 30 * 60_000 }

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => api<Category[]>('/categories'),
    ...STATIC,
  })
}

export function usePriorities() {
  return useQuery({
    queryKey: ['priorities'],
    queryFn: () => api<Priority[]>('/priorities'),
    ...STATIC,
  })
}

export function useTicket(ticketId: string | undefined) {
  return useQuery({
    queryKey: ['ticket', ticketId],
    enabled: Boolean(ticketId),
    queryFn: () => api<Ticket>(`/tickets/${ticketId}`),
  })
}

/** AI Insights for one ticket — the classification plus every draft it produced. */
export function useTicketAi(ticketId: string | undefined) {
  return useQuery({
    queryKey: ['ticket-ai', ticketId],
    enabled: Boolean(ticketId),
    queryFn: () => api<AiInsights>(`/tickets/${ticketId}/ai`),
  })
}

/**
 * The caller's team directory, staff only. Backs the assignment modal and
 * @mention autocomplete; requesters are filtered out here rather than at the
 * API, which returns the whole team.
 */
export function useStaffDirectory(enabled = true) {
  return useQuery({
    queryKey: ['staff'],
    enabled,
    queryFn: async () => {
      const users = await api<DirectoryUser[]>('/users')
      return users.filter((u) => u.is_active && u.role !== 'requester')
    },
    ...STATIC,
  })
}

// --- Admin configuration reads (Phase 12) ----------------------------------

/**
 * Teams, queues and SLA rules are Admin-only reads (Doc 05 §6) and change about
 * as often as the taxonomy, so they get the same hard cache. Every admin
 * mutation invalidates its own key, which is what keeps that safe.
 */
export function useTeams(enabled = true) {
  return useQuery({
    queryKey: ['teams'],
    enabled,
    queryFn: () => api<Team[]>('/admin/teams'),
    ...STATIC,
  })
}

export function useQueues(enabled = true) {
  return useQuery({
    queryKey: ['queues'],
    enabled,
    queryFn: () => api<Queue[]>('/admin/queues'),
    ...STATIC,
  })
}

export function useSlaRules(enabled = true) {
  return useQuery({
    queryKey: ['sla-rules'],
    enabled,
    queryFn: () => api<SlaRule[]>('/admin/sla-rules'),
  })
}

/** The whole org directory — deactivated accounts included, so they can be
 *  reactivated (App Flow §24). Distinct from `useStaffDirectory`, which is
 *  team-scoped and drops requesters. */
export function useAllUsers() {
  return useQuery({
    queryKey: ['users', 'all'],
    queryFn: () => api<DirectoryUser[]>('/users'),
  })
}

/** Index a list by id — turns the taxonomy lists into lookups for a ticket row. */
export function byId<T extends { id: string }>(items: T[] | undefined): Map<string, T> {
  return new Map((items ?? []).map((item) => [item.id, item]))
}

/**
 * Which of the three surfaces the current route belongs to. Notifications,
 * Account Settings and ticket deep-links are shared screens mounted under all
 * three, so they read their prefix from the URL instead of each surface
 * shipping a near-identical copy.
 */
export function useSurfaceBase(): string {
  const { pathname } = useLocation()
  return `/${pathname.split('/')[1] || 'portal'}`
}
