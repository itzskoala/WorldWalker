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
  'while you mow the lawn',
  'in your house',
  'on your lunch break',
  'on your way to class',
  'while running errands',
  'on your evening stroll',
  'during your morning walk',
  'on your way to the store',
  'while waiting for your laundry',
  'between meetings',
  'while pacing around your room',
  'on your way home',

  // At home
  'from your couch',
  'from your bedroom',
  'while cleaning your room',
  'while cooking dinner',
  'while doing the dishes',
  'during your next treadmill session',
  'while pacing on a phone call',
  'while procrastinating',
  'from your living room',

  // Fitness
  'on your daily run',
  'between gym sets',
  'while warming up',
  'on your recovery walk',
  'while training for a 5K',
  'on your next hike',
  'during your cooldown',
  'while hitting your step goal',
  'one step at a time',
  'while chasing a new PR',

  // Social life
  'on your way to meet friends',
  'while waiting for your date',
  'before the night begins',
  'on your way to the bar',
  'from the club',
  'before your next adventure',
  'while exploring with friends',
  'on your way to the party',
  'during a late-night stroll',

  // Travel & adventure
  'without leaving your city',
  'without booking a flight',
  'from wherever you are',
  'one country at a time',
  'one city at a time',
  'across the seven seas',
  'from your own backyard',
  'beyond your neighborhood',
  'without packing a suitcase',
  'on your next great adventure',
  'without leaving home',
  'wherever your feet take you',

  // Funny / unexpected
  'while avoiding your responsibilities',
  'instead of doomscrolling',
  'while pretending to be productive',
  'during your existential crisis',
  'while your food is in the oven',
  'while waiting for your game to load',
  'instead of touching grass',
  'while stalking your step count',
  'when you have nowhere to be',
  'while escaping your group chat',
  'during your daily side quest',
  'while your coffee brews',
  'while the GPS does its thing',
  'because sitting is overrated',
  'while mindlessly pacing',
  'during your main character moment',

  // Short & punchy
  'anywhere, anytime',
  'at your own pace',
  'from anywhere',
  'wherever life takes you',
  'with every step',
  'at home or abroad',
  'one step at a time',
  'without going anywhere',
  'whenever you feel like it',
  'every step counts',
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
            <TypewriterHeadline prefix="Explore the World… " variants={HERO_VARIANTS} />

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
