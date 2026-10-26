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

      // GIS's size:'large' always renders a fixed 40px-tall button -
      // there's no height option, confirmed live via its own rendered
      // DOM. .auth-modal-submit (Log in/Join for free) is 52px, so a
      // plain render here reads as a visibly smaller, less-round pill
      // sitting in a taller box. Rendering into an inner div pre-sized
      // for GIS's 40px and scaling that div up to 52px (uniformly, so
      // its border-radius scales with it and stays a true pill) is the
      // only way to actually match the two buttons' shape.
      const GOOGLE_BUTTON_HEIGHT = 40
      const TARGET_HEIGHT = 52
      const scale = TARGET_HEIGHT / GOOGLE_BUTTON_HEIGHT
      // offsetWidth, not getBoundingClientRect().width - the modal's own
      // CSS entrance animation (.auth-modal's scale(0.9) -> scale(1))
      // means this can run mid-transform, and getBoundingClientRect
      // returns the painted/transformed box, not the laid-out one -
      // offsetWidth is the real layout width regardless of any ancestor
      // transform, confirmed live (a stale ~90%-scale rect was what made
      // this button render narrower than the rest of the row).
      const containerWidth = Math.round(container.offsetWidth) || 352
      // 400 is GIS's own max width - clamp rather than let a value above
      // it be silently ignored/misrendered.
      const renderWidth = Math.min(400, Math.round(containerWidth / scale))

      container.innerHTML = ''
      const inner = document.createElement('div')
      inner.style.transform = `scale(${scale})`
      container.appendChild(inner)

      window.google.accounts.id.renderButton(inner, {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        shape: 'pill',
        text: mode === 'signup' ? 'signup_with' : 'signin_with',
        width: renderWidth,
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
