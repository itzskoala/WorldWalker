// The access token's one home - a plain module-level variable, never
// localStorage/sessionStorage, so it's gone the instant the tab reloads
// (web/static/js/auth.js's exact security model: only the httpOnly
// refresh cookie survives a reload). src/api/httpClient.ts reads/writes
// it directly; AuthContext.tsx subscribes so React state stays in sync
// without owning the token itself.

type Listener = (token: string | null) => void

let accessToken: string | null = null
const listeners = new Set<Listener>()

export function getToken(): string | null {
  return accessToken
}

export function setToken(token: string | null): void {
  accessToken = token
  listeners.forEach((listener) => listener(accessToken))
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
