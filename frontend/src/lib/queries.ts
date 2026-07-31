import { useQuery } from '@tanstack/react-query'

import { api } from './api'
import type { Category, Priority, Ticket } from './types'

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

/** Index a list by id — turns the taxonomy lists into lookups for a ticket row. */
export function byId<T extends { id: string }>(items: T[] | undefined): Map<string, T> {
  return new Map((items ?? []).map((item) => [item.id, item]))
}
