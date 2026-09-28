// React port of web/static/js/auth-ui.js's session-restore logic plus
// web/static/js/auth.js's login/signup/logout calls, unified into one
// context so every screen reads the same session state instead of poking
// window.Auth directly. The security model is unchanged: the access
// token still lives only in src/auth/tokenStore.ts's module variable
// (never localStorage), the refresh token is still an httpOnly cookie
// this code never touches directly.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as authApi from '../api/authApi'
import { onUnauthorized, refreshAccessToken } from '../api/httpClient'
import type { AuthStatus, User } from '../types/user'

interface AuthContextValue {
  status: AuthStatus
  user: User | null
  login: (email: string, password: string, rememberMe: boolean) => Promise<void>
  signup: (email: string, password: string) => Promise<void>
  loginWithGoogle: (credential: string) => Promise<void>
  validateEmail: (email: string) => Promise<boolean>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<User | null>(null)

  const establishSession = useCallback(async () => {
    const me = await authApi.fetchMe()
    setUser(me)
    setStatus('authenticated')
  }, [])

  // Once on mount: try to restore a session from the refresh cookie left
  // by an earlier login/signup, same as auth-ui.js's Auth.init() - so
  // reloading the tab, or coming back within the refresh window, doesn't
  // sign anyone out. How long that window is depends on "Remember me"
  // at login (accounts/security.py's REFRESH_TOKEN_EXPIRE_DAYS vs
  // SESSION_REFRESH_TOKEN_EXPIRE_HOURS) - signup and Google sign-in
  // always get the long one.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const restored = await refreshAccessToken()
      if (cancelled) return
      if (!restored) {
        setStatus('unauthenticated')
        return
      }
      try {
        await establishSession()
      } catch {
        if (!cancelled) setStatus('unauthenticated')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [establishSession])

  // httpClient's apiFetch fires this when a retry-after-refresh still
  // comes back 401 - the replacement for the vanilla app's
  // "ww:unauthorized" CustomEvent.
  useEffect(() => onUnauthorized(() => {
    setUser(null)
    setStatus('unauthenticated')
  }), [])

  const login = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    await authApi.login(email, password, rememberMe)
    await establishSession()
  }, [establishSession])

  const signup = useCallback(async (email: string, password: string) => {
    await authApi.signup(email, password)
    await establishSession()
  }, [establishSession])

  const loginWithGoogle = useCallback(async (credential: string) => {
    await authApi.loginWithGoogle(credential)
    await establishSession()
  }, [establishSession])

  const logout = useCallback(async () => {
    await authApi.logout()
    setUser(null)
    setStatus('unauthenticated')
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, signup, loginWithGoogle, validateEmail: authApi.validateEmail, logout }),
    [status, user, login, signup, loginWithGoogle, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
