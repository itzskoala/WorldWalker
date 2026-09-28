// Typed client for accounts/router.py's /auth/* endpoints - a port of
// web/static/js/auth.js. Unlike the vanilla version, this module holds no
// session state itself (no `currentUser`/`accessToken` variables) - it's
// pure request/response functions; src/auth/AuthContext.tsx owns the
// resulting state, src/auth/tokenStore.ts owns the token.

import type { AccessTokenResponse, User } from '../types/user'
import { setToken } from '../auth/tokenStore'
import { apiFetch, jsonHeaders, parseErrorMessage } from './httpClient'

async function postJson<T>(path: string, body: unknown, fallbackError: string): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'include',
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await parseErrorMessage(res, fallbackError))
  return res.json() as Promise<T>
}

/** signup/login/loginWithGoogle all get a fresh access_token back in the
 * body - this is the one place that actually puts it in tokenStore.ts,
 * so every one of them goes through here instead of the bare postJson()
 * above. Without this, the token from a successful signup/login was
 * simply discarded: the follow-up GET /auth/me (AuthContext.tsx's
 * establishSession()) went out with no Authorization header at all and
 * 401'd, every single time - the "Couldn't load your account" error
 * right after an otherwise-successful signup. */
async function postForToken(path: string, body: unknown, fallbackError: string): Promise<AccessTokenResponse> {
  const data = await postJson<AccessTokenResponse>(path, body, fallbackError)
  setToken(data.access_token)
  return data
}

/** Creates the account and starts the session in one call
 * (accounts/service.py's signup()) - surfaces "an account with this
 * email already exists" etc. straight from the server via
 * parseErrorMessage. */
export function signup(email: string, password: string): Promise<AccessTokenResponse> {
  return postForToken('/auth/signup', { email, password }, "Couldn't sign up — try again.")
}

// TODO(otp): startSignup()/verifySignup() backed the two-step "email a
// 6-digit code first" flow - disabled along with the backend routes they
// called (accounts/router.py). Revive together.
// export function startSignup(email: string, password: string): Promise<{ sent: boolean }> {
//   return postJson('/auth/signup/start', { email, password }, "Couldn't sign up — try again.")
// }
//
// export function verifySignup(email: string, code: string): Promise<AccessTokenResponse> {
//   return postJson('/auth/signup/verify', { email, code }, 'Incorrect code — try again.')
// }

/** The signup form's real-time check - fails open (true) on a network/
 * server hiccup so a check that couldn't even run never blocks someone
 * from submitting; accounts/service.py reruns the same validation
 * server-side regardless. */
export async function validateEmail(email: string): Promise<boolean> {
  try {
    const res = await fetch(`/auth/validate-email?email=${encodeURIComponent(email)}`, {
      credentials: 'include',
    })
    if (!res.ok) return true
    const data = (await res.json()) as { valid: boolean }
    return data.valid
  } catch {
    return true
  }
}

export function login(email: string, password: string, rememberMe: boolean): Promise<AccessTokenResponse> {
  return postForToken('/auth/login', { email, password, remember_me: rememberMe }, 'Incorrect email or password.')
}

/** `credential` is the ID token Google Identity Services hands back after
 * the user picks an account - verified server-side (accounts/
 * google_oauth.py) before anything trusts the identity inside. */
export function loginWithGoogle(credential: string): Promise<AccessTokenResponse> {
  return postForToken('/auth/google', { credential }, "Couldn't sign in with Google — try again.")
}

export async function logout(): Promise<void> {
  try {
    await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
  } catch (err) {
    console.warn('Logout request failed (clearing the local session anyway):', err)
  }
}

export async function fetchMe(): Promise<User> {
  const res = await apiFetch('/auth/me')
  if (!res.ok) throw new Error("Couldn't load your account.")
  return res.json() as Promise<User>
}
