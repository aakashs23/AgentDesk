import { getSession, setSession } from './session'

const BASE = '/api/v1'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI returns either `{detail: "..."}` or `{detail: [{msg, loc}, ...]}`. */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg ?? String(d)).join('; ')
  } catch {
    /* non-JSON error body */
  }
  return res.statusText || `Request failed (${res.status})`
}

// Single-flight: a burst of parallel 401s must rotate the refresh token once,
// not N times — the backend revokes the old token on rotation, so concurrent
// refreshes would invalidate each other and log the user out.
let refreshing: Promise<boolean> | null = null

function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    const session = getSession()
    if (!session) return false
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ refresh_token: session.refresh }),
    })
    if (!res.ok) {
      setSession(null) // refresh token is dead: the session is genuinely over
      return false
    }
    const data = await res.json()
    const latest = getSession()
    if (!latest) return false
    setSession({ ...latest, access: data.access_token, refresh: data.refresh_token })
    return true
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

/**
 * Multipart upload with real progress. `fetch` cannot report upload progress,
 * and Doc 03 §13 asks for a progress bar, so this one call uses XHR. It repeats
 * `api()`'s single-flight refresh-and-retry rather than skipping it, so a token
 * expiring mid-form does not lose the user's file.
 */
export function uploadFile<T = unknown>(
  path: string,
  file: File,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  const attempt = (): Promise<{ status: number; text: string }> =>
    new Promise((resolve, reject) => {
      const request = new XMLHttpRequest()
      const form = new FormData()
      form.append('file', file)

      request.open('POST', BASE + path)
      const session = getSession()
      if (session) request.setRequestHeader('authorization', `Bearer ${session.access}`)

      request.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total)
      }
      request.onload = () => resolve({ status: request.status, text: request.responseText })
      request.onerror = () => reject(new ApiError(0, 'Upload failed — check your connection'))
      request.onabort = () => reject(new DOMException('Aborted', 'AbortError'))
      signal?.addEventListener('abort', () => request.abort(), { once: true })
      request.send(form)
    })

  const parse = (text: string) => {
    try {
      return JSON.parse(text)
    } catch {
      return null
    }
  }

  return (async () => {
    let result = await attempt()
    if (result.status === 401 && getSession() && (await refreshTokens())) result = await attempt()
    if (result.status < 200 || result.status >= 300) {
      const body = parse(result.text)
      const detail = typeof body?.detail === 'string' ? body.detail : 'Upload failed'
      throw new ApiError(result.status, detail)
    }
    return parse(result.text) as T
  })()
}

export interface ApiOptions extends Omit<RequestInit, 'body'> {
  /** Serialised as a JSON body with the right content-type. */
  json?: unknown
  body?: BodyInit
}

export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
  const { json, ...init } = options

  const send = () => {
    const headers = new Headers(init.headers)
    const session = getSession()
    if (session) headers.set('authorization', `Bearer ${session.access}`)
    if (json !== undefined) headers.set('content-type', 'application/json')
    return fetch(BASE + path, {
      ...init,
      headers,
      body: json !== undefined ? JSON.stringify(json) : init.body,
    })
  }

  let res = await send()
  if (res.status === 401 && getSession() && (await refreshTokens())) res = await send()

  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}
