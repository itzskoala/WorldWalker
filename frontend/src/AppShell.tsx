// Port of web/templates/index.html's #app-shell + web/static/js/nav.js -
// the topbar, the sidebar, the four nav screens (all four stay mounted,
// only visibility toggles, so switching screens never loses in-progress
// state like a half-filled search form - same as the vanilla version),
// and the Trip Detail overlay, which replaces all of that (not toggled
// via `hidden`, genuinely swapped in) exactly like trip.js's
// enterTripView()/hide() did.

import { useEffect, useState } from 'react'
import { Topbar } from './components/Topbar'
import { Sidebar, type ScreenName } from './components/Sidebar'
import { EmailAlertsPanel } from './components/EmailAlertsPanel'
import { HomePage } from './pages/HomePage'
import { CreatePage } from './pages/CreatePage'
import { ProfilePage } from './pages/ProfilePage'
import { PostcardsPage } from './pages/PostcardsPage'
import { SettingsPage } from './pages/SettingsPage'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { TripDetailPage } from './pages/TripDetailPage'
import { startJourney } from './api/tripApi'
import { useGoogleHealthConnection } from './hooks/useGoogleHealthConnection'
import type { ResolvedPlace, TripSession } from './types/trip'

let nextSessionId = 1

// Persists which trip is on screen (nothing else - no fetched state) so a
// page reload restores it instead of dropping back to the dashboard. The
// trip itself is re-fetched on restore via TripDetailPage.tsx's existing
// "open an existing trip by id" path (session.initialState absent,
// session.tripId present) - the same path HomePage's own onOpenTrip
// already uses, nothing new there.
const SESSION_STORAGE_KEY = 'ww-active-trip-session'

interface StoredTripSession {
  tripId: string
  fromPlace: string
  toPlace: string
}

function readStoredSession(): StoredTripSession | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<StoredTripSession>
    if (typeof parsed.tripId !== 'string') return null
    return { tripId: parsed.tripId, fromPlace: parsed.fromPlace ?? '', toPlace: parsed.toPlace ?? '' }
  } catch {
    return null
  }
}

function writeStoredSession(session: StoredTripSession | null) {
  try {
    if (session) localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session))
    else localStorage.removeItem(SESSION_STORAGE_KEY)
  } catch {
    // Private window / blocked storage - worst case, a reload drops back
    // to the dashboard the way it always has, nothing crashes over it.
  }
}

export function AppShell() {
  const [screen, setScreen] = useState<ScreenName>('home')
  const [emailAlertsOpen, setEmailAlertsOpen] = useState(false)
  // Owned here and passed down to ConnectionsPage.tsx - see the hook's
  // own docstring.
  const connection = useGoogleHealthConnection()
  // Lazily seeded from localStorage: a trip session with a real tripId but
  // no initialState, same shape HomePage's onOpenTrip puts together -
  // TripDetailPage.tsx fetches the rest itself, same as opening any other
  // existing trip.
  const [tripSession, setTripSession] = useState<TripSession | null>(() => {
    const stored = readStoredSession()
    if (!stored) return null
    return { sessionId: nextSessionId++, tripId: stored.tripId, fromPlace: stored.fromPlace, toPlace: stored.toPlace, status: 'loading' }
  })

  // Keeps localStorage in sync with whatever's actually on screen.
  // Deliberately does nothing while tripSession.tripId is still null
  // (startWalking() below, waiting on POST /api/journey/start) - there's
  // no id yet to resume from, so a reload during that narrow window still
  // falls back to the dashboard (the in-flight request isn't resumable
  // either way); once it resolves, this effect runs again with a real id
  // and persists it then.
  useEffect(() => {
    if (!tripSession) {
      writeStoredSession(null)
      return
    }
    if (tripSession.tripId) {
      writeStoredSession({ tripId: tripSession.tripId, fromPlace: tripSession.fromPlace, toPlace: tripSession.toPlace })
    }
  }, [tripSession])

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
  function startWalking(from: ResolvedPlace, to: ResolvedPlace, roundTrip: boolean) {
    const sessionId = nextSessionId++
    setTripSession({ sessionId, tripId: null, fromPlace: from.label, toPlace: to.label, status: 'loading' })

    startJourney({
      from_place: from.label,
      to_place: to.label,
      round_trip: roundTrip,
      from_lat: from.lat,
      from_lng: from.lng,
      to_lat: to.lat,
      to_lng: to.lng,
    })
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
      <Topbar />

      <div className="app-body">
        <Sidebar active={screen} onChange={setScreen} />

        <div className="screens">
          <div hidden={screen !== 'home'}>
            <HomePage
              active={screen === 'home'}
              onOpenTrip={(tripId) => setTripSession({ sessionId: nextSessionId++, tripId, fromPlace: '', toPlace: '', status: 'loading' })}
              onExplore={() => setScreen('create')}
            />
          </div>
          <div hidden={screen !== 'create'}>
            <CreatePage onStartWalking={startWalking} />
          </div>
          <div hidden={screen !== 'postcards'}>
            <PostcardsPage />
          </div>
          <div className="profile-screen-wrap" hidden={screen !== 'profile'}>
            <ProfilePage active={screen === 'profile'} />
          </div>
          <div hidden={screen !== 'connections'}>
            <ConnectionsPage connection={connection} />
          </div>
          <div hidden={screen !== 'settings'}>
            <SettingsPage onOpenEmailAlerts={() => setEmailAlertsOpen(true)} />
          </div>
        </div>
      </div>

      <EmailAlertsPanel open={emailAlertsOpen} onClose={() => setEmailAlertsOpen(false)} />
    </div>
  )
}
