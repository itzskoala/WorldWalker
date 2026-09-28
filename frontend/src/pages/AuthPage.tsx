// Shared by LoginPage/SignupPage. Split-image layout (a header up top,
// a photo on each side, the actual form in the middle) modeled on
// Strava's own signup/login page. Both login and signup are one step:
// submit -> redirect to /.
//
// TODO(otp): signup used to be three steps (pick a method -> submit
// email/password -> a 6-digit code is emailed -> submit the code) - see
// the commented-out OTP panel/handlers below, and accounts/service.py's
// start_email_signup()/verify_email_signup() (also disabled) for why it
// was split that way. Disabled for now in favor of direct signup
// (accounts/service.py's signup()).

import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { fetchPublicConfig } from '../api/configApi'
import { GoogleSignInButton } from '../components/GoogleSignInButton'
import { AppleSignInButton } from '../components/AppleSignInButton'
import { MarketingHeader } from '../components/MarketingHeader'
import { PasswordStrengthMeter } from '../components/PasswordStrengthMeter'

interface AuthPageProps {
  mode: 'login' | 'signup'
}

export function AuthPage({ mode }: AuthPageProps) {
  const isSignup = mode === 'signup'
  const navigate = useNavigate()
  const { status, login, signup, loginWithGoogle, validateEmail } = useAuth()

  // Already signed in (a bookmarked /login, or the back button after
  // logging in elsewhere) - skip straight to the app instead of showing
  // the form again.
  useEffect(() => {
    if (status === 'authenticated') navigate('/', { replace: true })
  }, [status, navigate])

  const [googleClientId, setGoogleClientId] = useState('')
  const [appleClientId, setAppleClientId] = useState('')
  useEffect(() => {
    fetchPublicConfig().then((config) => {
      setGoogleClientId(config.google_client_id)
      setAppleClientId(config.apple_client_id)
    })
  }, [])

  // The Google/Apple buttons are the default view - email/password only
  // appear once "Sign Up/In With Email" is clicked, same collapse Strava
  // uses instead of showing every option at once.
  const [emailStep, setEmailStep] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailFieldError, setEmailFieldError] = useState(false)
  const [rememberMe, setRememberMe] = useState(true)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Real-time email validation (signup only) - never blocks submission by
  // itself (accounts/service.py's signup() reruns the same check
  // server-side, which is what actually decides, including the
  // already-registered-email case); this is just an earlier, friendlier
  // version of the same answer.
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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) return

    setSubmitting(true)
    try {
      if (isSignup) {
        await signup(trimmedEmail, password)
      } else {
        await login(trimmedEmail, password, rememberMe)
      }
      navigate('/')
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
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't sign in with Google — try again.")
    }
  }

  return (
    <>
      <MarketingHeader />
      <main className="auth-hero">
        <div className="auth-hero-image auth-hero-image--left" style={{ backgroundImage: 'url(/images/auth-hero-left.jpg)' }} />

        <div className="auth-hero-content">
          <div className="auth-hero-panel">
            <h1>{isSignup ? 'Turn Every Step Into a Journey' : 'Welcome Back'}</h1>
            <p className="auth-hero-subtext">
              {isSignup
                ? 'Track your progress across the real world. Join WorldWalker and turn your everyday steps into a journey - one checkpoint at a time.'
                : 'Log back in to keep tracking your journey across the real world.'}
            </p>

            <p className="auth-switch-line">
              {isSignup ? (
                <>
                  Already a Member? <Link className="auth-switch-cta" to="/login">Log In</Link>
                </>
              ) : (
                <>
                  New to WorldWalker? <Link className="auth-switch-cta" to="/signup">Create a new account</Link>
                </>
              )}
            </p>

            {!emailStep ? (
              <div className="auth-options">
                <GoogleSignInButton clientId={googleClientId} mode={mode} onCredential={handleGoogleCredential} />
                <AppleSignInButton clientId={appleClientId} mode={mode} />
                <button type="button" className="btn-square-primary" onClick={() => setEmailStep(true)}>
                  {isSignup ? 'Sign Up With Email' : 'Sign In With Email'}
                </button>
              </div>
            ) : (
              <form onSubmit={handleSubmit} noValidate>
                <div className="auth-field">
                  <label htmlFor="auth-email">Email</label>
                  <input
                    id="auth-email"
                    type="email"
                    autoComplete="email"
                    placeholder={isSignup ? 'Enter Email' : 'Your Email'}
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  {isSignup && emailFieldError && <p className="field-error">Please enter a valid email address.</p>}
                </div>

                <div className="auth-field">
                  <label htmlFor="auth-password">Password</label>
                  <input
                    id="auth-password"
                    type="password"
                    autoComplete={isSignup ? 'new-password' : 'current-password'}
                    placeholder={isSignup ? 'Create a Password' : 'Your Password'}
                    minLength={8}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  {isSignup && <PasswordStrengthMeter password={password} />}
                </div>

                {!isSignup && (
                  <label className="auth-remember">
                    <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} />
                    Remember me
                  </label>
                )}

                <button type="submit" className="btn-square-primary" disabled={submitting}>
                  {isSignup ? 'Sign Up' : 'Log In'}
                </button>

                <button type="button" className="auth-switch-link auth-back-link" onClick={() => setEmailStep(false)}>
                  ‹ Use Google or Apple instead
                </button>
              </form>
            )}

            {error && <p className="auth-error">{error}</p>}

            <p className="auth-terms">
              By continuing, you are agreeing to our <span className="auth-terms-link">Terms of Service</span> and{' '}
              <span className="auth-terms-link">Privacy Policy</span>.
            </p>
          </div>
        </div>

        <div className="auth-hero-image auth-hero-image--right" style={{ backgroundImage: 'url(/images/auth-hero-right.jpg)' }} />
      </main>
    </>
  )
}

/* TODO(otp): the OTP step - shown instead of the panel above once
   startSignup() succeeded, before verifySignup() actually created the
   account. Needs otpStep/otpCode/otpError/otpStatus/otpSubmitting state
   and handleOtpSubmit()/handleResend() handlers (removed above) alongside
   this JSX to come back:

  <div className="auth-hero-panel">
    <p className="auth-otp-heading">We sent you a code</p>
    <p className="auth-otp-subtext">
      Please enter the 6-digit code we sent to <strong>{email}</strong>
    </p>

    <form onSubmit={handleOtpSubmit} noValidate>
      <div className="auth-field">
        <label htmlFor="otp-code">Verification code</label>
        <input
          id="otp-code"
          className="auth-otp-input"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={6}
          autoComplete="one-time-code"
          placeholder="123456"
          required
          value={otpCode}
          onChange={(e) => setOtpCode(e.target.value)}
        />
      </div>

      {otpError && <p className="auth-error">{otpError}</p>}
      {otpStatus && <p className="auth-status">{otpStatus}</p>}

      <button type="submit" className="btn-square-primary" disabled={otpSubmitting}>
        Verify
      </button>
    </form>

    <p className="auth-switch">
      <button type="button" className="auth-switch-link" onClick={handleResend}>
        Resend code
      </button>
      {' · '}
      <button
        type="button"
        className="auth-switch-link"
        onClick={() => {
          setOtpStep(false)
          setOtpCode('')
          setOtpError('')
          setOtpStatus('')
        }}
      >
        Use a different email
      </button>
    </p>
  </div>
*/
