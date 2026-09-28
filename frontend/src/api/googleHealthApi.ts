// Typed client for auth/router.py's Google Health connect/disconnect
// routes (not the OAuth callback itself - that's a full-page redirect
// Google hits directly, never called from the frontend).

import type { GoogleAuthStartResponse, GoogleHealthStatus } from '../types/api'
import { apiFetch } from './httpClient'

export async function googleHealthStatus(): Promise<GoogleHealthStatus> {
  const res = await apiFetch('/auth/google/status')
  if (!res.ok) throw new Error("Couldn't check your Google Health connection.")
  return res.json() as Promise<GoogleHealthStatus>
}

export async function startGoogleHealthConnect(): Promise<GoogleAuthStartResponse> {
  const res = await apiFetch('/auth/google/start', { method: 'POST' })
  if (!res.ok) throw new Error("Couldn't start the Google Health connection.")
  return res.json() as Promise<GoogleAuthStartResponse>
}

/** The route itself returns an HTML page (not JSON) either way - callers
 * only ever care whether it succeeded, same as web/static/js/app.js. */
export async function disconnectGoogleHealth(): Promise<boolean> {
  const res = await apiFetch('/auth/google/disconnect', { method: 'POST' })
  return res.ok
}
