// The public, signed-out entry point - App.tsx renders this at "/" when
// no one is signed in (the rest of the app, AppShell, takes over once
// someone is). A real marketing page (hero, how-it-works), not just a
// bare login screen - MarketingHeader is the one piece shared with
// AuthPage.tsx, so the nav reads as the same page family across both.
//
// Hero CTAs open AuthModal.tsx - a real popup wired to the same native
// email/password + Google/Apple auth (auth/AuthContext.tsx) AuthPage.tsx's
// full-page /login and /signup already use, not a fake/separate one.
// RootRoute (App.tsx) swaps this whole page out for AppShell the instant
// AuthContext's status flips to 'authenticated', so closing the modal on
// a successful signup()/login() is enough - no explicit navigate needed
// here, unlike AuthPage.tsx's own form.

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { MarketingHeader } from '../components/MarketingHeader'
import { PhotoCollage } from '../components/PhotoCollage'
import { AuthModal, type AuthModalMode } from '../components/AuthModal'
import { IconCompass, IconFlag, IconRoute, IconTrophy } from '../components/icons'

const STEPS = [
  { icon: IconCompass, title: 'Choose a destination', body: 'Pick anywhere in the real world - across town or across an ocean.' },
  { icon: IconRoute, title: 'Start your journey', body: 'Your real steps move you along a real walking route, at your own pace.' },
  { icon: IconFlag, title: 'Discover checkpoints', body: 'Real places along the way surface as you reach them, each with its own story.' },
  { icon: IconTrophy, title: 'Build your collection', body: 'Postcards and badges from every finished journey, all in one place.' },
]

export function LandingPage() {
  const { hash } = useLocation()
  const [authModalMode, setAuthModalMode] = useState<AuthModalMode | null>(null)

  // MarketingHeader's nav links from /login or /signup arrive here as a
  // real navigation (hash included) rather than an in-page anchor click -
  // the browser doesn't auto-scroll for a client-side route change, so
  // this does it once the section actually exists in the DOM.
  useEffect(() => {
    if (!hash) return
    document.querySelector(hash)?.scrollIntoView({ block: 'start' })
  }, [hash])

  return (
    <>
      <MarketingHeader />

      <main className="landing">
        <section className="landing-hero" id="explore">
          <div className="landing-hero-copy">
            <h1 className="landing-hero-title">Walk wherever, from anywhere, with WorldWalker.</h1>

            <div className="landing-hero-ctas">
              <button type="button" className="btn btn-start landing-btn-primary" onClick={() => setAuthModalMode('signup')}>
                Join WorldWalker for free
              </button>
              <button type="button" className="btn btn-outline" onClick={() => setAuthModalMode('login')}>
                I&rsquo;m already a walker
              </button>
            </div>
          </div>

          <PhotoCollage className="landing-hero-illustration" />
        </section>

        <section className="landing-how" id="how-it-works">
          <h2 className="landing-section-title">How it works</h2>
          <div className="landing-how-grid">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <div className="surface-card landing-how-step" key={title}>
                <span className="landing-how-step-index">{i + 1}</span>
                <span className="landing-how-step-icon">
                  <Icon className="icon" />
                </span>
                <h3 className="landing-how-step-title">{title}</h3>
                <p className="landing-how-step-body">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Rendered inside .landing, not as a page-level sibling, so the
            modal's CSS (style.css's .auth-modal* rules) inherits this
            page's own scoped color tokens (--bg/--teal/--orange/...)
            through normal cascade instead of needing its own copy. */}
        {authModalMode && <AuthModal mode={authModalMode} onClose={() => setAuthModalMode(null)} onSwitchMode={setAuthModalMode} />}
      </main>
    </>
  )
}
