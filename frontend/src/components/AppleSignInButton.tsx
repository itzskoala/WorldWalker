// Renders the real "Sign in with Apple" button via Apple's own JS SDK
// (loaded in index.html) - the same architecture as
// GoogleSignInButton.tsx, one step behind it: app.py has no
// APPLE_SIGNIN_CLIENT_ID configured yet (no Apple Developer Services ID,
// no backend callback route), so AppleID.auth.init() never runs. Unlike
// Google's button, which hides itself entirely when unconfigured, this
// one still renders a real-looking Apple button in that case (the
// fallback markup below) - the design needs a real Apple option sitting
// next to Google's, not a "coming soon" placeholder. It just can't
// complete a sign-in until a Services ID is configured.

import { useEffect, useRef } from 'react'

const APPLE_ICON_PATH =
  'M12.15 6.9c-.95 0-2.42-1.08-3.96-1.04-2.04.03-3.91 1.18-4.96 3.01-2.12 3.68-.55 9.1 1.52 12.09 1.01 1.45 2.2 3.09 3.79 3.04 1.52-.07 2.09-.99 3.93-.99 1.83 0 2.35.99 3.96.95 1.64-.03 2.68-1.48 3.68-2.95 1.15-1.69 1.63-3.33 1.66-3.41-.04-.02-3.18-1.22-3.22-4.86-.03-3.04 2.48-4.49 2.6-4.56-1.43-2.09-3.62-2.32-4.39-2.38-1.85-.14-3.51.99-4.61 1.09zm3.4-3.16c.83-1.01 1.4-2.43 1.24-3.83-1.2.05-2.66.8-3.53 1.82-.78.89-1.45 2.33-1.27 3.71 1.34.1 2.71-.68 3.56-1.7z'

declare global {
  interface Window {
    AppleID?: {
      auth: {
        init: (config: {
          clientId: string
          scope: string
          redirectURI: string
          usePopup: boolean
        }) => void
      }
    }
  }
}

interface AppleSignInButtonProps {
  clientId: string
  mode: 'login' | 'signup'
}

export function AppleSignInButton({ clientId, mode }: AppleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Real init - AppleID's SDK scans the DOM for #appleid-signin once
  // this runs and paints its own button graphic into it, replacing the
  // fallback markup below. Nothing to clean up: the SDK owns the element
  // from here on, same as Google's renderButton().
  useEffect(() => {
    if (!clientId) return
    window.AppleID?.auth.init({
      clientId,
      scope: 'name email',
      redirectURI: `${window.location.origin}/auth/apple/callback`,
      usePopup: true,
    })
  }, [clientId])

  return (
    <div
      ref={containerRef}
      id={clientId ? 'appleid-signin' : undefined}
      // Configured: a bare frame, same as .auth-option-google - Apple's
      // SDK paints its own bordered white box inside, so this wrapper
      // must not also draw one (that's exactly the double-box bug fixed
      // on the Google button). Unconfigured: the full box styling, since
      // this div is the button in that case (our own icon + label).
      className={clientId ? 'auth-option-apple' : 'auth-option-btn'}
      data-color="white"
      data-border="true"
      data-type={mode === 'signup' ? 'sign up' : 'sign in'}
    >
      {!clientId && (
        <>
          <svg className="icon" viewBox="0 0 24 24" fill="currentColor" stroke="none">
            <path d={APPLE_ICON_PATH} />
          </svg>
          {/* Sentence case, matching Google's own rendered button text
              exactly ("Sign up with Google") - Title Case here read as a
              different button style sitting right next to it. */}
          <span className="auth-option-label">{mode === 'signup' ? 'Sign up with Apple' : 'Sign in with Apple'}</span>
        </>
      )}
    </div>
  )
}
