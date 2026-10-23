// Port of web/templates/index.html's #screen-create + web/static/js/
// app.js's search/autocomplete/start-walking logic. The globe hero
// (WorldWindGlobe) is a separate component - see src/components/
// WorldWindGlobe.tsx.

import { useEffect, useRef, useState } from 'react'
import { CreateHero } from '../components/create/CreateHero'
import { TripTypeToggle, type TripType } from '../components/create/TripTypeToggle'
import { RouteFieldsRow } from '../components/create/RouteFieldsRow'
import { StartWalkingButton } from '../components/create/StartWalkingButton'
import { prewarmMapAssets } from '../components/tripMap'
import { validateRoute } from '../api/tripApi'
import type { ResolvedPlace } from '../types/trip'

// How long the pre-flight route check gets before Start Walking unblocks
// anyway - see the effect below for why this is a UI-only patience limit,
// not the same thing as OSRM's own (much longer, shared) request timeout.
const CHECK_SOFT_TIMEOUT_MS = 4000

interface CreatePageProps {
  // Fires immediately on click - AppShell owns the actual /api/journey/
  // start call and switches the POV to the Trip Detail map right away
  // (see AppShell.tsx's startWalking()), rather than this screen sitting
  // on a disabled button for however long that real geocoding/routing
  // call takes.
  onStartWalking: (from: ResolvedPlace, to: ResolvedPlace, roundTrip: boolean) => void
}

export function CreatePage({ onStartWalking }: CreatePageProps) {
  const [tripType, setTripType] = useState<TripType>('round')
  const [from, setFromText] = useState('')
  const [to, setToText] = useState('')
  // The coordinates behind `from`/`to`, once a suggestion (or "Use current
  // location") has actually resolved one - cleared back to null the
  // moment the matching text is hand-edited again, since it no longer
  // necessarily names that place. Read by the route-validation effect
  // below, which only fires once both are set.
  const [fromLocation, setFromLocation] = useState<ResolvedPlace | null>(null)
  const [toLocation, setToLocation] = useState<ResolvedPlace | null>(null)
  // Which of the two was resolved most recently - so that if the pair
  // turns out unwalkable, validation can clear the *other*, now-stale one
  // and keep what the user just picked. Not touched by swap(): swapping
  // doesn't change which side was "just selected," it just exchanges
  // where each already-resolved location sits.
  const [lastSelectedField, setLastSelectedField] = useState<'from' | 'to' | null>(null)
  // Whether each field is actively resolving something right now (a
  // debounced search in flight, or "Use current location" mid-lookup) -
  // Start Walking stays disabled through that window even if a *previous*
  // resolution is technically still sitting in fromLocation/toLocation,
  // since it's about to be replaced (or cleared) by whatever's in flight.
  const [fromResolving, setFromResolving] = useState(false)
  const [toResolving, setToResolving] = useState(false)
  // The (unordered) coordinate pair validation last confirmed walkable -
  // so swap(), which puts the same two already-valid locations on the
  // opposite sides, doesn't re-fire an identical OSRM check it already
  // knows the answer to. Not state: changing it should never itself
  // trigger a re-render.
  const lastValidPairRef = useRef<string | null>(null)
  // Start Walking's real gate, alongside fromLocation/toLocation below -
  // 'valid' only once the route-validation effect has actually confirmed
  // this exact pair is walkable. Both fields resolving is necessary but
  // NOT sufficient: without this, the button went clickable the instant
  // fromLocation/toLocation were both set, racing the validation fetch
  // below - for an obviously-unwalkable pair (two continents apart) OSRM
  // takes a bit longer to give up than for a normal route, which was
  // plenty of time for a real click to land before the silent-clear ran
  // and reach /api/journey/start with no route at all. 'uncertain' (the
  // check itself failed - network hiccup, OSRM unreachable) deliberately
  // still allows Start Walking, matching this effect's existing "couldn't
  // check" philosophy below: a validator outage shouldn't be able to
  // block someone from walking a perfectly fine route.
  const [routeStatus, setRouteStatus] = useState<'unknown' | 'checking' | 'valid' | 'invalid' | 'uncertain'>('unknown')
  const [activeField, setActiveField] = useState<'from' | 'to' | null>(null)
  const [swapping, setSwapping] = useState(false)
  const [starting, setStarting] = useState(false)

  function setFrom(value: string) {
    setFromText(value)
    setFromLocation(null)
  }

  function setTo(value: string) {
    setToText(value)
    setToLocation(null)
  }

  function selectFrom(place: ResolvedPlace) {
    setFromText(place.label)
    setFromLocation(place)
    setLastSelectedField('from')
    setRouteStatus('unknown') // a newly-picked location is never pre-validated, even if the old pair was
  }

  function selectTo(place: ResolvedPlace) {
    setToText(place.label)
    setToLocation(place)
    setLastSelectedField('to')
    setRouteStatus('unknown')
  }

  // Immediate walking-route validation, once both fields have resolved to
  // real coordinates - not on every keystroke (this only depends on the
  // *resolved* locations, not the free-typed `from`/`to` text), and never
  // by creating a trip (POST /api/route/validate does the same OSRM call
  // "Start Walking" eventually does, but persists nothing - see
  // app.py's docstring on that route). An unwalkable pair (same spot, too
  // close together, or genuinely no walking route) silently clears
  // whichever field wasn't just selected - the field that caused the
  // invalid combination, not the one the user is actively choosing - with
  // no error message, per the design here. A validation that couldn't be
  // completed at all (network hiccup, OSRM down) leaves both fields
  // untouched instead: `result.valid === false` is a real "no" from the
  // routing provider, distinct from `null` ("couldn't check"), and only a
  // real `false` clears anything.
  //
  // The AbortController below is the staleness guard: selecting a new
  // location while an earlier check is still in flight re-runs this
  // effect, whose cleanup aborts that earlier fetch before it can resolve
  // - so an old validation can never clear a field a newer selection just
  // set. Same pattern as PlaceAutocomplete.tsx's debounced search.
  //
  // CHECK_SOFT_TIMEOUT_MS below is separate from that: OSRM's own
  // foot-routing search genuinely takes longer to give up on an
  // obviously-unwalkable pair (two continents apart, say) than to find a
  // real route, so a worst-case "no route" answer can take several
  // seconds - confirmed live. Rather than lowering the shared OSRM
  // timeout in travel_logic/route_service.py (that one also guards the
  // real /api/journey/start call, where cutting it short could wrongly
  // reject a genuinely slow-to-compute but valid long route), this is a
  // UI-only patience limit: past it, Start Walking unblocks (routeStatus
  // 'uncertain', same as a real network failure below) while the actual
  // check keeps running in the background. A late "no route" answer no
  // longer clears a field at that point - the user may already be past
  // this screen - but /api/journey/start's own fail-soft handling (see
  // app.py) still catches a genuinely-submitted impossible pair.
  useEffect(() => {
    if (!fromLocation || !toLocation) return

    const [a, b] = [`${fromLocation.lat},${fromLocation.lng}`, `${toLocation.lat},${toLocation.lng}`].sort()
    const pairKey = `${a}|${b}`
    if (lastValidPairRef.current === pairKey) {
      setRouteStatus('valid') // e.g. swap() putting the same known-good pair on the other side
      return
    }

    setRouteStatus('checking')
    let timedOut = false
    const timeoutId = window.setTimeout(() => {
      timedOut = true
      setRouteStatus('uncertain')
    }, CHECK_SOFT_TIMEOUT_MS)

    const controller = new AbortController()
    validateRoute(fromLocation, toLocation, controller.signal)
      .then((result) => {
        window.clearTimeout(timeoutId)
        if (result.valid === true) {
          lastValidPairRef.current = pairKey
          setRouteStatus('valid')
          return
        }
        if (result.valid !== false) {
          if (!timedOut) setRouteStatus('uncertain') // couldn't check at all - don't block Start Walking on our own validator's outage
          return
        }
        if (timedOut) return // already let the user past this - see comment above
        setRouteStatus('invalid')
        if (lastSelectedField === 'to') {
          setFromText('')
          setFromLocation(null)
        } else {
          setToText('')
          setToLocation(null)
        }
      })
      .catch((err) => {
        window.clearTimeout(timeoutId)
        if ((err as Error).name === 'AbortError') return
        console.warn("Couldn't validate that route:", err)
        if (!timedOut) setRouteStatus('uncertain')
      })

    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [fromLocation, toLocation, lastSelectedField])

  // Warms the browser's HTTP cache with the trip map's style/sprite/glyph
  // assets while someone's still filling out this form - by the time
  // "Start Walking" mounts the real map (TripDetailPage.tsx), those
  // requests are often already sitting in cache instead of being the
  // first things that map has to wait on. See tripMap.ts's
  // prewarmMapAssets() for exactly what this fetches and why it can't
  // reach the route's own tiles (unknown until /api/journey/start
  // resolves) - best-effort only, a failure here is silently fine since
  // the real map's own load path already handles that the same way it
  // always has.
  useEffect(() => {
    prewarmMapAssets()
  }, [])

  function swap() {
    setFromText(to)
    setToText(from)
    setFromLocation(toLocation)
    setToLocation(fromLocation)
    setSwapping(true)
    setTimeout(() => setSwapping(false), 260)
  }

  const routeConfirmed = routeStatus === 'valid' || routeStatus === 'uncertain'

  function startWalking() {
    // Silent by design: an unresolved form isn't an error, it's just not
    // done yet - nothing happens until both fields hold a real resolved
    // location, not just typed text, AND route validation has actually
    // had its say (the start-btn's disabled state below already prevents
    // reaching this - this is the same guard as defense-in-depth).
    if (!fromLocation || !toLocation || fromResolving || toResolving || !routeConfirmed) return

    // Only guards against a double-fire in the instant before AppShell's
    // own state update swaps this screen out - this component unmounts
    // once that happens, so there's no "stuck disabled forever" case to
    // reset from.
    setStarting(true)
    onStartWalking(fromLocation, toLocation, tripType === 'round')
  }

  return (
    <section className="screen" id="screen-create" aria-label="Plan a walk">
      <CreateHero />

      <div className="screen-inner screen-inner-overlap">
        <section className="search-card" id="search-card" aria-label="Plan your walk">
          <TripTypeToggle value={tripType} onChange={setTripType} />

          <RouteFieldsRow
            activeField={activeField}
            onActiveFieldChange={setActiveField}
            from={from}
            onFromChange={setFrom}
            onFromSelect={selectFrom}
            onFromResolvingChange={setFromResolving}
            fromResolved={fromLocation !== null}
            to={to}
            onToChange={setTo}
            onToSelect={selectTo}
            onToResolvingChange={setToResolving}
            toResolved={toLocation !== null}
            swapping={swapping}
            onSwap={swap}
          />

          <StartWalkingButton
            disabled={starting || !fromLocation || !toLocation || fromResolving || toResolving || !routeConfirmed}
            checking={routeStatus === 'checking'}
            onClick={startWalking}
          />
        </section>
      </div>
    </section>
  )
}
