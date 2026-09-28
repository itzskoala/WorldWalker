// Mirrors accounts/schemas.py's UserOut and AccessTokenResponse exactly -
// see accounts/router.py's /auth/* routes.

export interface User {
  id: string
  email: string
  is_active: boolean
  created_at: string
}

export interface AccessTokenResponse {
  access_token: string
  token_type: string
}

/** What useAuth() exposes while a session is still being restored from
 * the refresh cookie (App start) vs. resolved one way or the other - see
 * src/auth/AuthContext.tsx's AuthProvider. */
export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'
