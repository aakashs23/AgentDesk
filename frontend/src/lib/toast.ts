import { useSyncExternalStore } from 'react'

export type ToastTone = 'info' | 'success' | 'error'

export interface Toast {
  id: number
  message: string
  tone: ToastTone
}

// A module-level store rather than a context: route guards and the API layer
// need to raise a toast from outside the React tree ("Access restricted",
// "Session expired"), and threading a provider into those is not worth it.
let toasts: Toast[] = []
const listeners = new Set<() => void>()
let nextId = 1

function emit() {
  listeners.forEach((l) => l())
}

export function toast(message: string, tone: ToastTone = 'info') {
  const id = nextId++
  toasts = [...toasts, { id, message, tone }]
  emit()
  setTimeout(() => dismissToast(id), 4000)
  return id
}

export function dismissToast(id: number) {
  const next = toasts.filter((t) => t.id !== id)
  if (next.length === toasts.length) return
  toasts = next
  emit()
}

export function useToasts() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => void listeners.delete(l)
    },
    () => toasts,
  )
}
