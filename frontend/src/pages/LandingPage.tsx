// The public, signed-out entry point - App.tsx renders this at "/" when
// no one is signed in (the rest of the app, AppShell, takes over once
// someone is). A real marketing page (animated hero + photo collage,
// stats, footer), not just a bare login screen - MarketingHeader/
// MarketingFooter are shared with the Explore/About Us/Pricing
// placeholders and /login, /signup, so the whole page family reads as
// one. Deliberately compact (small fonts/padding throughout - see
// style.css) so the whole page fits one typical viewport without
// scrolling.
//
// The hero's "Get started" opens AuthModal.tsx - a real popup wired to
// the same native email/password + Google/Apple auth (auth/AuthContext.tsx)
// AuthPage.tsx's full-page /login and /signup already use, not a fake/
// separate one. RootRoute (App.tsx) swaps this whole page out for
// AppShell the instant AuthContext's status flips to 'authenticated', so
// closing the modal on a successful signup() is enough - no explicit
// navigate needed here, unlike AuthPage.tsx's own form.

import { useState } from 'react'
import { MarketingHeader } from '../components/MarketingHeader'
import { MarketingFooter } from '../components/MarketingFooter'
import { AuthModal, type AuthModalMode } from '../components/AuthModal'
import { TypewriterHeadline } from '../components/landing/TypewriterHeadline'
import { LandingStats } from '../components/landing/LandingStats'

const HERO_VARIANTS = [
  // Everyday adventures
  'on your commute to work',
  'while you walk the dog',
  'from your treadmill',
  'on your lunch break',
  'on your way to class',
  'while running errands',
  'during your morning walk',
  'on your way home',
  'between meetings',
  'around your neighborhood',

  // At home
  'without leaving your house',
  'from your living room',
  'from your couch',
  'while doing the dishes',
  'while cooking dinner',
  'while pacing around your room',
  'while your coffee brews',

  // Fitness
  'while hitting your step goal',
  'on your daily run',
  'between gym sets',
  'on your recovery walk',
  'while training for a 5K',
  'one step at a time',
  'while chasing a new PR',
  'during your next treadmill session',

  // Social life
  'on your way to meet friends',
  'before the night begins',
  'from the club',
  'while exploring with friends',
  'during a late-night stroll',
  'on your next date night',

  // Travel & exploration
  'one country at a time',
  'one city at a time',
  'without booking a flight',
  'without packing a suitcase',
  'from wherever you are',
  'beyond your neighborhood',
  'across the seven seas',
  'from your own backyard',
  'without leaving home',
  'to places you have never been',
  'through streets around the globe',
  'across continents and cultures',

  // Funny / unexpected
  'instead of doomscrolling',
  'while avoiding your responsibilities',
  'during your daily side quest',
  'while pretending to be productive',
  'instead of touching grass',
  'during your main character moment',
  'because sitting is overrated',
  'while escaping your group chat',
  'when you have nowhere to be',
  'while your game is loading',
  'during your next existential crisis',
  'while stalking your step count',
];
export function LandingPage() {
  const [authModalMode, setAuthModalMode] = useState<AuthModalMode | null>(null)

  return (
    <div className="landing-page">
      <MarketingHeader onSignIn={() => setAuthModalMode('login')} onSignUp={() => setAuthModalMode('signup')} />

      <main className="landing">
        {/* Two even halves, left to right: headline + CTA + stats on the
            left, the photo collage on the right - see .landing-hero's own
            note in style.css for why stats live here now instead of their
            own full-width section below. */}
        <section className="landing-hero">
          <div className="landing-hero-copy">
            <TypewriterHeadline prefix="Walk the World… " variants={HERO_VARIANTS} />

            <p className="landing-hero-mission">
              Turn everyday movement into extraordinary journeys. See the world one step at a
              time, discover new places and stories, and earn postcards along the way.
            </p>

            <button type="button" className="landing-cta" onClick={() => setAuthModalMode('signup')}>
              Get started
            </button>

            <LandingStats />
          </div>

          <img
            src="/hero/collage.jpg"
            alt="A collage of travel moments: the Eiffel Tower, a hiker silhouetted at sunset, international flags, white sneakers against a blue sky, heels, a penguin in the snow, footprints in the sand, and a mountain range"
            className="landing-hero-illustration"
          />
        </section>

        {/* Rendered inside .landing, not as a page-level sibling, so the
            modal's CSS (style.css's .auth-modal* rules) inherits this
            page's own scoped color tokens (--bg/--teal/--orange/...)
            through normal cascade instead of needing its own copy. */}
        {authModalMode && <AuthModal mode={authModalMode} onClose={() => setAuthModalMode(null)} onSwitchMode={setAuthModalMode} />}
      </main>

      <MarketingFooter />
    </div>
  )
}
