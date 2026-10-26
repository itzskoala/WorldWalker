// A real sign-up/sign-in popup for the landing hero's two CTAs - wired
// to the same auth/AuthContext.tsx (native email/password + Google/Apple)
// AuthPage.tsx's full-page /login and /signup already use, not a second,
// separate auth system. Those two pages still exist unchanged (direct
// links, bookmarks, MarketingHeader's own Log In/Sign Up) - this is only
// an alternate, same-page way to reach the identical signup()/login()
// calls, for a "pop up" rather than a navigation.
//
// Layout (rounded bubble, X close, stacked fields, one big pill button,
// an OR divider, provider buttons, a small switch-mode line) was asked
// to match a Pinterest screenshot's structure - this uses this app's
// own monochrome palette throughout, never Pinterest's logo, red, or
// copy.

import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { fetchPublicConfig } from '../api/configApi'
import { getLastUser, forgetLastUser, type LastUser } from '../auth/lastUser'
import { GoogleSignInButton } from './GoogleSignInButton'
// import { AppleSignInButton } from './AppleSignInButton' - no Apple
// Services ID configured yet, see AppleSignInButton.tsx's own docstring.
// Re-enable once that's wired up.
import { PasswordField } from './PasswordField'
import { IconClose } from './icons'

export type AuthModalMode = 'login' | 'signup'

// "Welcome back, {name}!" in a random language each time the modal
// mounts - purely decorative variety for the returning-user login view,
// not a real i18n system (the rest of the app is still English-only).
const WELCOME_BACK_TEMPLATES = [
  (name: string) => `Welcome back, ${name}!`,
  (name: string) => `¡Bienvenido de nuevo, ${name}!`,
  (name: string) => `欢迎回来，${name}！`,
  (name: string) => `वापसी पर स्वागत है, ${name}!`,
  (name: string) => `С возвращением, ${name}!`,
  (name: string) => `తిరిగి స్వాగతం, ${name}!`,
  (name: string) => `З поверненням, ${name}!`,
  (name: string) => `Willkommen zurück, ${name}!`,
  (name: string) => `Bon retour, ${name}!`,
]

function randomWelcomeBack(name: string): string {
  const template = WELCOME_BACK_TEMPLATES[Math.floor(Math.random() * WELCOME_BACK_TEMPLATES.length)]
  return template(name)
}

function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return email
  if (local.length <= 4) return `${local[0] ?? ''}••••@${domain}`
  return `${local.slice(0, 2)}••••••${local.slice(-2)}@${domain}`
}

interface AuthModalProps {
  mode: AuthModalMode
  onClose: () => void
  onSwitchMode: (mode: AuthModalMode) => void
}

export function AuthModal({ mode, onClose, onSwitchMode }: AuthModalProps) {
  const isSignup = mode === 'signup'
  const { login, signup, loginWithGoogle, validateEmail } = useAuth()

  const [googleClientId, setGoogleClientId] = useState('')
  const [appleClientId, setAppleClientId] = useState('')
  useEffect(() => {
    fetchPublicConfig().then((config) => {
      setGoogleClientId(config.google_client_id)
      setAppleClientId(config.apple_client_id)
    })
  }, [])

  // Read once at mount regardless of the modal's initial mode - switching
  // from signup to login mid-session (the "Already a walker? Sign in"
  // link) should still find it. Only the login view ever renders it.
  const [lastUser, setLastUser] = useState<LastUser | null>(getLastUser)
  const [welcomeMessage] = useState(() => (lastUser ? randomWelcomeBack(lastUser.name) : ''))

  const [email, setEmail] = useState(() => lastUser?.email ?? '')
  const [password, setPassword] = useState('')
  const [emailFieldError, setEmailFieldError] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const showReturningUser = !isSignup && !!lastUser

  function notYou() {
    forgetLastUser()
    setLastUser(null)
    setEmail('')
  }

  // Real-time email validation (signup only) - same 600ms-debounced check
  // AuthPage.tsx's own form uses; never blocks submission itself, see
  // api/authApi.ts's validateEmail() docstring on why.
  useEffect(() => {
    if (!isSignup || !email.trim()) {
      setEmailFieldError(false)
      return
    }
    const timer = setTimeout(async () => {
      const valid = await validateEmail(email.trim())
      setEmailFieldError(!valid)
    }, 600)
    return () => clearTimeout(timer)
  }, [email, isSignup, validateEmail])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Switching Join/Sign in mid-popup shouldn't carry a stale error or a
  // half-typed password between the two forms.
  function switchMode(next: AuthModalMode) {
    setError('')
    setPassword('')
    onSwitchMode(next)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) return

    setSubmitting(true)
    try {
      if (isSignup) await signup(trimmedEmail, password)
      else await login(trimmedEmail, password, rememberMe)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong — try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleGoogleCredential(credential: string) {
    setError('')
    try {
      await loginWithGoogle(credential)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't sign in with Google — try again.")
    }
  }

  return (
    <div
      className="auth-modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
        <div className="auth-modal-header">
          {showReturningUser ? (
            <span className="auth-modal-avatar" aria-hidden="true">
              {lastUser!.profilePhoto ? <img src={lastUser!.profilePhoto} alt="" /> : lastUser!.name.charAt(0).toUpperCase()}
            </span>
          ) : (
            <span aria-hidden="true" />
          )}
          <button type="button" className="auth-modal-close" aria-label="Close" onClick={onClose}>
            <IconClose />
          </button>
        </div>

        <h2 id="auth-modal-title" className="auth-modal-title">
          {isSignup ? 'Join WorldWalker' : showReturningUser ? welcomeMessage : 'Welcome back'}
        </h2>
        <p className="auth-modal-subtitle">
          {isSignup
            ? 'Create a free account and turn your steps into a journey.'
            : showReturningUser
              ? (
                  <>
                    Log in to keep walking toward your next checkpoint.{' '}
                    <button type="button" className="auth-not-you" onClick={notYou}>
                      Not you?
                    </button>
                  </>
                )
              : 'Sign in to keep walking toward your next checkpoint.'}
        </p>

        <form className="auth-modal-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="auth-modal-email">Email</label>
            {showReturningUser ? (
              <input id="auth-modal-email" type="text" readOnly value={maskEmail(email)} />
            ) : (
              <input
                id="auth-modal-email"
                type="email"
                autoComplete="email"
                placeholder="Enter your email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            {isSignup && emailFieldError && <p className="field-error">Please enter a valid email address.</p>}
          </div>

          <div className="auth-field">
            <label htmlFor="auth-modal-password">Password</label>
            <PasswordField
              id="auth-modal-password"
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              placeholder={isSignup ? 'Create a password' : 'Your password'}
              value={password}
              onChange={setPassword}
              showStrengthMeter={isSignup}
            />
          </div>

          {!isSignup && (
            <>
              <Link to="/forgot-password" className="auth-forgot-password">
                Forgot password?
              </Link>
              <label className="auth-remember">
                <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} />
                Remember me
              </label>
            </>
          )}

          {error && <p className="auth-error">{error}</p>}

          <button type="submit" className="btn btn-start auth-modal-submit" disabled={submitting}>
            {isSignup ? 'Join for free' : 'Log in'}
          </button>
        </form>

        {(googleClientId || appleClientId) && (
          <>
            <div className="auth-modal-divider">
              <span>OR</span>
            </div>
            <div className="auth-modal-socials">
              <GoogleSignInButton clientId={googleClientId} mode={mode} onCredential={handleGoogleCredential} />
              {/* <AppleSignInButton clientId={appleClientId} mode={mode} /> */}
            </div>
          </>
        )}

        <p className="auth-modal-switch">
          {isSignup ? (
            <>
              Already a walker?{' '}
              <button type="button" className="auth-modal-switch-link" onClick={() => switchMode('login')}>
                Sign in
              </button>
            </>
          ) : (
            <>
              New to WorldWalker?{' '}
              <button type="button" className="auth-modal-switch-link" onClick={() => switchMode('signup')}>
                Join for free
              </button>
            </>
          )}
        </p>

        {isSignup ? (
          <p className="auth-modal-terms">
            By continuing, you are agreeing to our <Link to="/terms" className="auth-terms-link">Terms of Service</Link> and{' '}
            <Link to="/privacy" className="auth-terms-link">Privacy Policy</Link>.
          </p>
        ) : (
          <p className="auth-modal-terms">
            <Link to="/terms" className="auth-terms-link">Terms of Service</Link>
            {' · '}
            <Link to="/privacy" className="auth-terms-link">Privacy Policy</Link>
          </p>
        )}
      </div>
    </div>
  )
}
