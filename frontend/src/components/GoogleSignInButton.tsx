// Renders one real Google Identity Services button into a container -
// a port of web/static/js/auth-page.js's initGoogleSignIn()/
// renderGoogleButton(). Hidden entirely if clientId is empty (Google
// sign-in not configured for this deployment) or the GIS script (loaded
// via index.html's own <script src="https://accounts.google.com/gsi/client">)
// never becomes available - the email/password form works either way.

import { useEffect, useRef } from 'react'

interface GoogleSignInButtonProps {
  clientId: string
  mode: 'login' | 'signup'
  onCredential: (credential: string) => void
}

export function GoogleSignInButton({ clientId, mode, onCredential }: GoogleSignInButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // AuthPage passes an inline arrow function, so `onCredential` is a new
  // reference on every one of its re-renders (every keystroke in the
  // email/password fields, for instance). A ref keeps this effect's own
  // dependency array to [clientId, mode] - the only things that should
  // actually re-initialize GIS - instead of re-running
  // google.accounts.id.initialize() on every parent render, which was
  // confirmed live to spam GIS_LOGGER's "initialize() called multiple
  // times" warning while typing and could plausibly break an in-flight
  // sign-in (the button gets torn down and re-rendered mid-click).
  const onCredentialRef = useRef(onCredential)
  onCredentialRef.current = onCredential

  useEffect(() => {
    if (!clientId) return

    let cancelled = false
    let attemptsLeft = 20

    function tryInit() {
      if (cancelled) return
      const container = containerRef.current
      if (!container) return

      if (!window.google?.accounts?.id) {
        if (attemptsLeft <= 0) return
        attemptsLeft -= 1
        setTimeout(tryInit, 250)
        return
      }

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => onCredentialRef.current(response.credential),
        // We only ever call renderButton(), never prompt() (no One Tap) -
        // the one FedCM flag that actually applies here.
        use_fedcm_for_button: true,
      })

      container.innerHTML = ''
      window.google.accounts.id.renderButton(container, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        shape: 'rectangular',
        text: mode === 'signup' ? 'signup_with' : 'signin_with',
        // 400 is GIS's own max - clamp rather than let a value above it
        // be silently ignored/misrendered.
        width: Math.min(400, Math.round(container.getBoundingClientRect().width) || 352),
      })
    }

    tryInit()
    return () => {
      cancelled = true
    }
  }, [clientId, mode])

  if (!clientId) return null

  return <div className="auth-option-google" ref={containerRef} />
}
