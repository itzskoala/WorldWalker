// Port of web/templates/index.html's #screen-create + web/static/js/
// app.js's search/autocomplete/start-walking logic. The globe hero
// (WorldWindGlobe) is a separate component - see src/components/
// WorldWindGlobe.tsx.

import { useEffect, useState } from 'react'
import { PlaceAutocomplete } from '../components/PlaceAutocomplete'
import { WorldWindGlobe } from '../components/WorldWindGlobe'
import { MAP_STYLE } from '../components/tripMap'

interface CreatePageProps {
  // Fires immediately on click - AppShell owns the actual /api/journey/
  // start call and switches the POV to the Trip Detail map right away
  // (see AppShell.tsx's startWalking()), rather than this screen sitting
  // on a disabled button for however long that real geocoding/routing
  // call takes.
  onStartWalking: (fromPlace: string, toPlace: string, roundTrip: boolean) => void
}

export function CreatePage({ onStartWalking }: CreatePageProps) {
  const [tripType, setTripType] = useState<'round' | 'one-way'>('round')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [swapping, setSwapping] = useState(false)
  const [starting, setStarting] = useState(false)

  // Warms the browser's HTTP cache with the trip map's style JSON while
  // someone's still filling out this form - by the time "Start Walking"
  // mounts the real map (TripDetailPage.tsx), the style fetch is often
  // already sitting in cache instead of being the first thing that map
  // has to wait on. Best-effort only: this is a fixed URL, not the actual
  // route (unknown until /api/journey/start resolves), so it can't warm
  // the route's own tiles - and a failure here (offline, blocked) is
  // silently fine, since the real map's own load path already handles
  // that the same way it always has.
  useEffect(() => {
    fetch(MAP_STYLE).catch(() => {})
  }, [])

  function swap() {
    setFrom(to)
    setTo(from)
    setSwapping(true)
    setTimeout(() => setSwapping(false), 260)
  }

  function startWalking() {
    // Silent by design: an incomplete form isn't an error, it's just not
    // done yet - nothing happens until both fields are filled.
    if (!from || !to) return

    // Only guards against a double-fire in the instant before AppShell's
    // own state update swaps this screen out - this component unmounts
    // once that happens, so there's no "stuck disabled forever" case to
    // reset from.
    setStarting(true)
    onStartWalking(from, to, tripType === 'round')
  }

  return (
    <section className="screen" id="screen-create" aria-label="Plan a walk">
      <section className="globe-header">
        <WorldWindGlobe />
        <div className="globe-header-scrim" aria-hidden="true" />
        <div className="globe-header-text">
          <h1 className="hero-title">Walk the World</h1>
          <p className="hero-sub">Turn your real, everyday steps into a journey across the globe.</p>
        </div>
      </section>

      <div className="screen-inner screen-inner-overlap">
        <section className="search-card" id="search-card" aria-label="Plan your walk">
          <div className="trip-toggle" role="radiogroup" aria-label="Trip type">
            <button
              type="button"
              className={`trip-pill${tripType === 'round' ? ' is-active' : ''}`}
              role="radio"
              aria-checked={tripType === 'round'}
              onClick={() => setTripType('round')}
            >
              Round trip
            </button>
            <button
              type="button"
              className={`trip-pill${tripType === 'one-way' ? ' is-active' : ''}`}
              role="radio"
              aria-checked={tripType === 'one-way'}
              onClick={() => setTripType('one-way')}
            >
              One way
            </button>
          </div>

          <div className="fields-row">
            <PlaceAutocomplete id="from" label="Where from?" placeholder="City or address" pinColor="green" value={from} onChange={setFrom} currentLocationButton />

            <button type="button" className={`swap-btn${swapping ? ' is-spinning' : ''}`} aria-label="Swap starting point and destination" onClick={swap}>
              <svg className="icon" viewBox="0 0 24 24" fill="none">
                <path d="M7 7h12m0 0-4-4m4 4-4 4M17 17H5m0 0 4 4m-4-4 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            <PlaceAutocomplete id="to" label="Where to?" placeholder="Oh the places you'll go!" pinColor="red" value={to} onChange={setTo} />
          </div>

          <button type="button" className="btn btn-start" id="start-btn" disabled={starting} onClick={startWalking}>
            <svg className="icon" viewBox="0 0 24 24" fill="none">
              <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
              <path d="m21 21-4.3-4.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            Start Walking
          </button>
        </section>
      </div>
    </section>
  )
}
