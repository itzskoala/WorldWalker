// Typed client for auth/router.py's Google Health connect/disconnect
// routes (not the OAuth callback itself - that's a full-page redirect
// Google hits directly, never called from the frontend).

import type { GoogleAuthStartResponse, GoogleHealthStatus } from '../types/api'
import { apiFetch, parseErrorMessage } from './httpClient'

export async function googleHealthStatus(): Promise<GoogleHealthStatus> {
  const res = await apiFetch('/auth/google/status')
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't check your Google Health connection."))
  return res.json() as Promise<GoogleHealthStatus>
}

export async function startGoogleHealthConnect(): Promise<GoogleAuthStartResponse> {
  const res = await apiFetch('/auth/google/start', { method: 'POST' })
  if (!res.ok) throw new Error(await parseErrorMessage(res, "Couldn't start the Google Health connection."))
  return res.json() as Promise<GoogleAuthStartResponse>
}

/** The route itself returns an HTML page (not JSON) either way - a
 * failure body is still real text worth surfacing (auth/router.py's
 * disconnect only ever 404s - "nothing to disconnect" - so that's the
 * one message callers can show), just not JSON parseErrorMessage can
 * read, hence the plain .text() here instead. */
export async function disconnectGoogleHealth(): Promise<{ ok: true } | { ok: false; message: string }> {
  const res = await apiFetch('/auth/google/disconnect', { method: 'POST' })
  if (res.ok) return { ok: true }
  const body = await res.text()
  const message = body.match(/<p>(.*?)<\/p>/)?.[1] ?? "Couldn't disconnect your Google Health connection."
  return { ok: false, message }
}
