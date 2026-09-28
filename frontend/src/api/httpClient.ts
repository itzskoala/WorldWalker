// The one wrapper every authenticated request in this app goes through -
// a typed port of web/static/js/auth.js's apiFetch()/refresh(), same
// behavior: attaches "Authorization: Bearer <token>", and on a 401 tries
// exactly one silent refresh+retry (not an infinite loop) before giving
// up, since a second 401 right after a successful refresh means the
// token really is no good (deactivated user, revoked session).
//
// The refresh token itself is never touched here - it's an httpOnly
// cookie the browser attaches on its own to same-origin requests
// (credentials: "include"), invisible to this code.

import type { ApiErrorBody } from '../types/api'
import { getToken, setToken } from '../auth/tokenStore'

type UnauthorizedListener = () => void
const unauthorizedListeners = new Set<UnauthorizedListener>()

/** AuthProvider subscribes to this to clear its user state the moment a
 * request's retry-after-refresh still comes back 401 - the replacement
 * for the vanilla app's `document.dispatchEvent(new CustomEvent("ww:unauthorized"))`. */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function notifyUnauthorized(): void {
  unauthorizedListeners.forEach((listener) => listener())
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Every route in this app reports errors as either FastAPI's own
 * {detail: string | [{msg}, ...]} or a plain {error: string} JSONResponse
 * - see src/types/api.ts's ApiErrorBody. */
export async function parseErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as ApiErrorBody
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail) && data.detail[0]?.msg) return data.detail[0].msg
    if (data.error) return data.error
    return fallback
  } catch {
    return fallback
  }
}

let refreshPromise: Promise<boolean> | null = null

/** Coalesces concurrent refreshes (e.g. two protected requests both
 * hitting a 401 back-to-back) into a single /auth/refresh call instead of
 * a duplicate race that could rotate the token twice. */
export async function refreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch('/auth/refresh', { method: 'POST', credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) {
          setToken(null)
          return false
        }
        const data = (await res.json()) as { access_token: string }
        setToken(data.access_token)
        return true
      })
      .catch(() => {
        setToken(null)
        return false
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const withAuth = (token: string | null): RequestInit => {
    const headers = new Headers(options.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    return { ...options, headers, credentials: 'include' }
  }

  let res = await fetch(path, withAuth(getToken()))

  if (res.status === 401 && getToken() !== null) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      res = await fetch(path, withAuth(getToken()))
    }
  }

  if (res.status === 401) {
    setToken(null)
    notifyUnauthorized()
  }

  return res
}

export function jsonHeaders(): HeadersInit {
  return { 'Content-Type': 'application/json' }
}
