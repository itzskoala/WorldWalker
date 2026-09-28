// Port of web/templates/index.html's #app-shell + web/static/js/nav.js -
// the topbar, the three tab screens (all three stay mounted, only
// visibility toggles, so switching tabs never loses in-progress state
// like a half-filled search form - same as the vanilla version), and the
// Trip Detail overlay, which replaces all of that (not toggled via
// `hidden`, genuinely swapped in) exactly like trip.js's
// enterTripView()/hide() did.

import { useState } from 'react'
import { Topbar } from './components/Topbar'
import { TabBar, type ScreenName } from './components/TabBar'
import { EmailAlertsPanel } from './components/EmailAlertsPanel'
import { HomePage } from './pages/HomePage'
import { CreatePage } from './pages/CreatePage'
import { ProfilePage } from './pages/ProfilePage'
import { TripDetailPage } from './pages/TripDetailPage'
import { startJourney } from './api/tripApi'
import type { TripSession } from './types/trip'

let nextSessionId = 1

export function AppShell() {
  const [screen, setScreen] = useState<ScreenName>('home')
  const [emailAlertsOpen, setEmailAlertsOpen] = useState(false)
  const [tripSession, setTripSession] = useState<TripSession | null>(null)

  function updateSession(patch: Partial<TripSession>) {
    setTripSession((prev) => (prev ? { ...prev, ...patch } : prev))
  }

  function exitTrip(nextScreen: ScreenName = 'home') {
    setTripSession(null)
    setScreen(nextScreen)
  }

  // Switches the POV to the Trip Detail map immediately, in a 'loading'
  // session with no tripId/initialState yet - the same state HomePage's
  // onOpenTrip below puts things in. /api/journey/start genuinely can
  // take the better part of a minute (real geocoding/routing/per-
  // checkpoint AI descriptions server-side, no way around that here), so
  // CreatePage used to sit on its own screen showing just a disabled
  // button for that whole stretch - indistinguishable from broken, and
  // easy to "fix" by reloading, which only lost the in-flight request
  // (the trip had often already been created server-side by then, so it
  // then showed up on Home instead). Navigating first and resolving this
  // request in the background means the exact same "Loading your walk…"
  // overlay TripDetailPage already has for opening an existing trip now
  // covers this wait too, and the map fills in on its own the moment the
  // response lands - no reload needed.
  function startWalking(fromPlace: string, toPlace: string, roundTrip: boolean) {
    const sessionId = nextSessionId++
    setTripSession({ sessionId, tripId: null, fromPlace, toPlace, status: 'loading' })

    startJourney({ from_place: fromPlace, to_place: toPlace, round_trip: roundTrip })
      .then((result) => {
        setTripSession((prev) => {
          // The user may have already exited back out (or started a
          // different walk) while this was in flight - don't let a
          // late response clobber whatever's on screen now.
          if (!prev || prev.sessionId !== sessionId) return prev
          if (!result.coming_soon) return { ...prev, tripId: result.trip_id, status: 'ready', initialState: result }
          // A real external dependency (geocoding/routing) hiccuped -
          // app.py fails soft here rather than a 500.
          return { ...prev, status: 'error', errorMessage: "Couldn't plan that route — try again in a moment." }
        })
      })
      .catch((err) => {
        setTripSession((prev) =>
          prev && prev.sessionId === sessionId
            ? { ...prev, status: 'error', errorMessage: err instanceof Error ? err.message : "Couldn't start that walk — try again." }
            : prev,
        )
      })
  }

  if (tripSession) {
    return (
      <TripDetailPage
        key={tripSession.sessionId}
        session={tripSession}
        onExit={() => exitTrip('home')}
        onExitToProfile={() => exitTrip('profile')}
        onSessionUpdate={updateSession}
      />
    )
  }

  return (
    <div className="app">
      <Topbar onOpenEmailAlerts={() => setEmailAlertsOpen(true)} />

      <div className="screens">
        <div hidden={screen !== 'home'}>
          <HomePage active={screen === 'home'} onOpenTrip={(tripId) => setTripSession({ sessionId: nextSessionId++, tripId, fromPlace: '', toPlace: '', status: 'loading' })} />
        </div>
        <div hidden={screen !== 'create'}>
          <CreatePage onStartWalking={startWalking} />
        </div>
        <div hidden={screen !== 'profile'}>
          <ProfilePage active={screen === 'profile'} />
        </div>
      </div>

      <TabBar active={screen} onChange={setScreen} />

      <EmailAlertsPanel open={emailAlertsOpen} onClose={() => setEmailAlertsOpen(false)} />
    </div>
  )
}
