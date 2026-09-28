// Port of web/static/js/trip.js - the full-bleed map screen. Mount this
// with `key={session.sessionId}` at the call site (see AppShell.tsx) so a
// new walk or a different opened trip always gets a fresh instance,
// matching trip.js's own "every open trip gets its own fresh map" rule -
// enforced there by hand with a requestId counter; here it falls out of
// React's mount/unmount lifecycle instead.

import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useTripMap } from '../hooks/useTripMap'
import { getJourneyState, pauseJourney, resumeJourney, subscribeToTripCheckpoints } from '../api/tripApi'
import type { TripCheckpointEvent } from '../api/tripApi'
import type { TripMapState, TripSession } from '../types/trip'

const POLL_INTERVAL_MS = 20000
const METERS_PER_MILE = 1609.344
const METERS_PER_KM = 1000
const UNITS_STORAGE_KEY = 'ww-trip-units'

function readSavedUnit(): 'mi' | 'km' {
  try {
    return localStorage.getItem(UNITS_STORAGE_KEY) === 'km' ? 'km' : 'mi'
  } catch {
    return 'mi'
  }
}

function metersToUnit(meters: number, unit: 'mi' | 'km'): number {
  return unit === 'km' ? meters / METERS_PER_KM : meters / METERS_PER_MILE
}

function formatDistance(meters: number, unit: 'mi' | 'km', decimals = 1): string {
  return `${metersToUnit(meters, unit).toFixed(decimals)} ${unit}`
}

// "2h 15m", "3d 4h", "45m" - elapsed_seconds is already "time actually
// walking" (core/facade.py's _elapsed_seconds excludes paused time).
function formatDuration(totalSeconds: number): string {
  const totalMinutes = Math.max(0, Math.round(totalSeconds / 60))
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60

  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

interface TripDetailPageProps {
  session: TripSession
  onExit: () => void
  onExitToProfile: () => void
  onSessionUpdate: (patch: Partial<TripSession>) => void
}

export function TripDetailPage({ session, onExit, onExitToProfile, onSessionUpdate }: TripDetailPageProps) {
  const { user } = useAuth()
  const unit = readSavedUnit()

  const [state, setState] = useState<TripMapState | null>(session.initialState ?? null)
  const [mapReady, setMapReady] = useState(false)
  const [mapError, setMapError] = useState<string | null>(null)
  const stateRef = useRef<TripMapState | null>(state)
  stateRef.current = state

  const { controllerRef, remount } = useTripMap({
    containerId: 'trip-map',
    onReady: () => setMapReady(true),
    onError: () => setMapError('This map is taking too long to load. Tap to try again.'),
  })

  // Fetch full trip state when opened by id without data already in hand
  // (Home's "open a trip" path) - the map itself mounts in parallel via
  // useTripMap above, same "don't wait for the fetch before loading tiles"
  // idea as trip.js's ensureMapMounted().
  useEffect(() => {
    if (session.initialState || !session.tripId) return
    let cancelled = false
    getJourneyState(session.tripId)
      .then((fetched) => {
        if (cancelled) return
        setState(fetched)
        onSessionUpdate({ status: 'ready' })
      })
      .catch((err) => {
        if (cancelled) return
        console.warn("Couldn't open that trip:", err)
        onSessionUpdate({ status: 'error', errorMessage: "Couldn't load this trip. Tap to try again." })
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.tripId])

  // Starting a brand-new walk (AppShell.tsx's startWalking()): `state`
  // above is seeded from session.initialState at mount, but that's still
  // undefined at that point - the real value only lands later, as a prop
  // update, once /api/journey/start resolves. useState's initializer
  // doesn't re-run on a prop change, so without this the map would just
  // sit on the loading overlay forever despite AppShell having the data.
  useEffect(() => {
    if (session.initialState) setState(session.initialState)
  }, [session.initialState])

  // Progressive checkpoints: as soon as a trip_id exists and its
  // checkpoints aren't already fully generated (a brand-new walk always
  // starts checkpoints_ready: false - core/facade.py's start_journey()),
  // listen for checkpoint_added/checkpoint_updated/checkpoints_ready over
  // GET /api/journey/{trip_id}/events instead of waiting for the next
  // 20s poll below. Reads/writes stateRef.current rather than closing
  // over `state` so this effect only needs to re-run when trip_id or
  // checkpoints_ready actually change, not on every unrelated state
  // update (a pause, a poll tick, ...).
  useEffect(() => {
    if (!state || state.checkpoints_ready) return
    const tripId = state.trip_id

    function applyCheckpointEvent(event: TripCheckpointEvent) {
      const prev = stateRef.current
      if (!prev) return

      let next: TripMapState
      if (event.type === 'checkpoint_added') {
        const alreadyKnown = prev.checkpoints.some((c) => c.checkpoint_number === event.checkpoint.checkpoint_number)
        const checkpoints = alreadyKnown
          ? prev.checkpoints
          : [...prev.checkpoints, event.checkpoint].sort((a, b) => a.checkpoint_number - b.checkpoint_number)
        next = { ...prev, checkpoints }
      } else if (event.type === 'checkpoint_updated') {
        next = {
          ...prev,
          checkpoints: prev.checkpoints.map((c) => (c.checkpoint_number === event.checkpoint.checkpoint_number ? event.checkpoint : c)),
        }
      } else {
        next = { ...prev, checkpoints_ready: true }
      }

      setState(next)
      controllerRef.current?.update(next)
    }

    return subscribeToTripCheckpoints(tripId, applyCheckpointEvent)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.trip_id, state?.checkpoints_ready])

  // Draw the moment both the map is ready AND real state exists - either
  // order works, useTripMap/renderInitial() itself queues if the map
  // isn't loaded yet.
  useEffect(() => {
    if (state) controllerRef.current?.renderInitial(state)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state === session.initialState ? 'initial' : state?.trip_id])

  // Polling - not for a completed trip (it can't change), not while still
  // loading/errored.
  useEffect(() => {
    if (!state || state.status === 'completed' || session.status !== 'ready') return
    const tripId = state.trip_id

    const timer = window.setInterval(async () => {
      try {
        const fresh = await getJourneyState(tripId)
        setState(fresh)
        controllerRef.current?.update(fresh)
        if (fresh.percent_complete >= 100) {
          window.clearInterval(timer)
          window.setTimeout(onExit, 2000) // a beat to let the user see the 100% state
        }
      } catch (err) {
        console.warn('Trip state poll failed:', err) // keep polling - likely just a network blip
      }
    }, POLL_INTERVAL_MS)

    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.trip_id, state?.status, session.status])

  const [pausing, setPausing] = useState(false)
  async function handlePauseResume() {
    if (!state) return
    const action = state.status === 'paused' ? 'resume' : 'pause'
    setPausing(true)
    try {
      const fresh = action === 'resume' ? await resumeJourney(state.trip_id) : await pauseJourney(state.trip_id)
      setState(fresh)
      controllerRef.current?.update(fresh)
    } catch (err) {
      console.warn(`Couldn't ${action} this trip:`, err)
    } finally {
      setPausing(false)
    }
  }

  function retryMapLoad() {
    setMapError(null)
    remount()
    if (stateRef.current) controllerRef.current?.renderInitial(stateRef.current)
  }

  const overlayError = mapError ?? (session.status === 'error' ? session.errorMessage ?? "Couldn't load this trip. Tap to try again." : null)
  // Covers only the actual map-tile load (fast) and real errors - NOT
  // the wait for a brand-new walk's route (session.tripId starts null,
  // set only once /api/journey/start resolves - AppShell.tsx's
  // startWalking()), which can take the better part of a minute. Rather
  // than block the screen behind a spinner for that whole stretch, the
  // base map is left visible and loading/rendering underneath (the
  // world view MapLibre boots into) the moment tiles are ready; the
  // still-planning state below shows inline in the route card instead,
  // and drawInitial() zooms into the real route the instant it lands.
  const showLoadingOverlay = !mapReady || overlayError
  const avatarInitial = user?.email ? user.email[0].toUpperCase() : 'W'

  const from = state?.from_place ?? session.fromPlace
  const to = state?.to_place ?? session.toPlace
  const pct = state ? Math.min(100, state.percent_complete) : 0
  const isPaused = state?.status === 'paused'
  const hitCount = state?.checkpoints.filter((c) => c.hit).length ?? 0
  const daysLeft = state?.estimated_days_remaining
  const showDaysLeft = !!state && state.status !== 'completed' && daysLeft !== null && daysLeft !== undefined && Number.isFinite(daysLeft)

  return (
    <section className="trip-view" aria-label="Your walk">
      <div className="trip-map-full" id="trip-map" />

      <div className={`trip-map-loading${overlayError ? ' is-error' : ''}`} hidden={!showLoadingOverlay} onClick={overlayError ? retryMapLoad : undefined}>
        {overlayError ? (
          <svg className="trip-map-loading-error-icon" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
            <path d="M12 8v5M12 16h.01" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        ) : (
          <span className="spinner" aria-hidden="true" />
        )}
        <p>{overlayError ?? (!session.tripId && !state ? 'Planning your route — this can take a minute…' : 'Loading your walk…')}</p>
      </div>

      <div className="trip-overlay-top">
        <div className="trip-overlay-row">
        <div className="trip-overlay-row-scroll">
          <button type="button" className="trip-map-btn trip-map-btn-dark trip-back-btn" aria-label="Back to My Journeys" onClick={onExit}>
            <svg className="icon" viewBox="0 0 24 24" fill="none">
              <path d="M19 12H5M11 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          <div className="trip-route-card">
            <div className="trip-route-card-top">
              <h2 className="trip-route-card-title">
                <span>{from || '—'}</span>
                <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none">
                  <path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>{to || '—'}</span>
              </h2>
              <span className="trip-status-badge" hidden={!isPaused}>
                Paused
              </span>
            </div>
            <div className="trip-route-card-progress-row">
              {state ? (
                <>
                  <span className="trip-card-progress trip-route-card-progress-bar">
                    <span className="trip-card-progress-fill" style={{ width: `${pct.toFixed(0)}%` }} />
                  </span>
                  <span className="trip-route-card-pct">{pct.toFixed(0)}%</span>
                </>
              ) : (
                // The route itself (real geocoding/routing server-side)
                // is still in flight - a 0%-filled progress bar here
                // would look identical to a real just-started walk, so
                // this stands in for it instead of the bar.
                <span className="trip-route-card-planning">
                  <span className="spinner spinner-sm" aria-hidden="true" />
                  Planning your route…
                </span>
              )}
            </div>
          </div>

          {state?.status !== 'completed' && (
            <button
              type="button"
              className={`trip-map-btn trip-map-btn-dark btn-pause${isPaused ? ' is-paused' : ''}`}
              aria-label={isPaused ? 'Resume' : 'Pause'}
              disabled={pausing || !state}
              onClick={handlePauseResume}
            >
              {isPaused ? (
                <svg className="icon icon-resume" viewBox="0 0 24 24" fill="none">
                  <path d="M7 5v14l12-7-12-7Z" fill="currentColor" />
                </svg>
              ) : (
                <svg className="icon icon-pause" viewBox="0 0 24 24" fill="none">
                  <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
                  <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
                </svg>
              )}
            </button>
          )}

          {state && (
            <>
              <div className="trip-pill-chip">
                <span className="trip-pill-emoji" aria-hidden="true">
                  👣
                </span>
                <span>{state.total_steps.toLocaleString()}</span>
              </div>
              <div className="trip-pill-chip">
                <span className="trip-pill-emoji" aria-hidden="true">
                  ⏱️
                </span>
                <span>{formatDuration(state.elapsed_seconds)}</span>
              </div>
              <div className="trip-pill-chip">
                <span className="trip-pill-emoji" aria-hidden="true">
                  🛣️
                </span>
                <span>
                  {formatDistance(state.distance_walked_m, unit)} / {formatDistance(state.total_distance_m, unit)}
                </span>
              </div>
              <div className="trip-pill-chip">
                <span className="trip-pill-emoji" aria-hidden="true">
                  🚩
                </span>
                <span>
                  {hitCount} / {state.checkpoints.length}
                </span>
              </div>
              {showDaysLeft && (
                <div className="trip-pill-chip">
                  <span className="trip-pill-emoji" aria-hidden="true">
                    ⏳
                  </span>
                  <span>{daysLeft! < 1 ? '<1' : Math.ceil(daysLeft!).toString()}</span>
                </div>
              )}
            </>
          )}
        </div>

        <div className="trip-overlay-row-end">
          <button type="button" className="trip-map-btn trip-map-btn-dark trip-menu-btn" aria-label="Menu" onClick={onExit}>
            <svg className="icon" viewBox="0 0 24 24" fill="none">
              <circle cx="6" cy="6" r="1.7" fill="currentColor" />
              <circle cx="12" cy="6" r="1.7" fill="currentColor" />
              <circle cx="18" cy="6" r="1.7" fill="currentColor" />
              <circle cx="6" cy="12" r="1.7" fill="currentColor" />
              <circle cx="12" cy="12" r="1.7" fill="currentColor" />
              <circle cx="18" cy="12" r="1.7" fill="currentColor" />
              <circle cx="6" cy="18" r="1.7" fill="currentColor" />
              <circle cx="12" cy="18" r="1.7" fill="currentColor" />
              <circle cx="18" cy="18" r="1.7" fill="currentColor" />
            </svg>
          </button>
          <button type="button" className="trip-avatar-btn" aria-label="Your profile" onClick={onExitToProfile}>
            <span>{avatarInitial}</span>
          </button>
        </div>
        </div>
      </div>
    </section>
  )
}
