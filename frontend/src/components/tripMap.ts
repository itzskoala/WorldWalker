// TypeScript port of web/static/js/components/trip-map.js - kept as a
// plain MapLibre module (not "React-ified") on purpose, per the migration
// plan's "wrap, don't rewrite" call for this piece: src/hooks/useTripMap.ts
// is the thin React wrapper (mount on mount, destroy on unmount); this
// file is the same imperative component the vanilla app had, just typed.
// See the original file's header comment for the full design rationale
// (mount()/renderInitial() split, progressive checkpoint reveal, etc.) -
// not repeated here since none of it changed.

import { ErrorEvent as MapLibreErrorEvent, GeoJSONSource, LngLatBounds, Map as MapLibreMap, Marker, setWorkerUrl } from 'maplibre-gl'
import type { IControl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// MapLibre's own worker instantiation (a `new Worker(new URL(...))` deep
// inside the package) resolves to the wrong location once Vite/Rollup
// bundles this app - confirmed live, in both dev and the production
// build: the map's style never finishes loading (no "load" event, no
// error - a real "load" from a missing counterpart). Importing the
// worker file with Vite's own `?url` suffix gets a URL Vite guarantees is
// correct in both dev and prod, and setWorkerUrl() is MapLibre's own
// documented hook for exactly this bundler-compatibility case.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Coordinates, TripMapState } from '../types/trip'

setWorkerUrl(maplibreWorkerUrl)

// Exported so CreatePage.tsx can warm the browser's HTTP cache with this
// exact URL while someone's still filling out the form - see its own
// comment for why.
export const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'
const DEBUG = new URLSearchParams(window.location.search).has('debug')

const LOAD_STALL_TIMEOUT_MS = 15000

const FIT_BOUNDS_PADDING = { top: 120, bottom: 110, left: 50, right: 70 }

const MAP_STYLES = [
  { id: 'liberty', label: 'Standard', url: 'https://tiles.openfreemap.org/styles/liberty' },
  { id: 'bright', label: 'Bright', url: 'https://tiles.openfreemap.org/styles/bright' },
  { id: 'positron', label: 'Light', url: 'https://tiles.openfreemap.org/styles/positron' },
]

function toLngLat(coords: Coordinates): [number, number] {
  return [coords.lng, coords.lat]
}

function routeLineGeoJson(points: Coordinates[]): GeoJSON.Feature<GeoJSON.LineString> {
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'LineString', coordinates: points.map(toLngLat) },
  }
}

function boundsForRoute(routeGeometry: Coordinates[]): LngLatBounds {
  const bounds = new LngLatBounds()
  routeGeometry.forEach((point) => bounds.extend(toLngLat(point)))
  return bounds
}

function createMarkerElement(className: string): HTMLDivElement {
  const element = document.createElement('div')
  element.className = className
  return element
}

function svgEl<T extends HTMLElement>(markup: string): T {
  const wrap = document.createElement('div')
  wrap.innerHTML = markup.trim()
  return wrap.firstElementChild as T
}

function buildNavControl({ onResetView }: { onResetView: () => void }): IControl {
  let map: MapLibreMap | null = null
  let container: HTMLElement | null = null

  return {
    onAdd(mapInstance: MapLibreMap) {
      map = mapInstance
      container = document.createElement('div')
      container.className = 'maplibregl-ctrl trip-nav-control'

      const resetBtn = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-ctrl-btn trip-ctrl-reset" aria-label="Reset view to full route">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 9V5a1 1 0 0 1 1-1h4M20 9V5a1 1 0 0 0-1-1h-4M4 15v4a1 1 0 0 0 1 1h4M20 15v4a1 1 0 0 1-1 1h-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
      `)
      resetBtn.addEventListener('click', () => onResetView())

      const zoomWrap = svgEl<HTMLDivElement>(`
        <div class="trip-ctrl-zoom">
          <button type="button" aria-label="Zoom in">+</button>
          <button type="button" aria-label="Zoom out">&minus;</button>
        </div>
      `)
      const [zoomInBtn, zoomOutBtn] = Array.from(zoomWrap.querySelectorAll('button'))
      zoomInBtn.addEventListener('click', () => map?.zoomIn({ duration: 250 }))
      zoomOutBtn.addEventListener('click', () => map?.zoomOut({ duration: 250 }))

      container.append(resetBtn, zoomWrap)
      return container
    },
    onRemove() {
      container?.remove()
      map = null
    },
  }
}

function buildStyleControl({ onStyleChange }: { onStyleChange: (styleUrl: string) => void }): IControl {
  let activeId = MAP_STYLES[0].id
  let container: HTMLElement | null = null

  return {
    onAdd() {
      container = document.createElement('div')
      container.className = 'maplibregl-ctrl trip-style-control'

      const toggleBtn = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-style-btn" aria-haspopup="true" aria-expanded="false" aria-label="Change map style">
          <svg viewBox="0 0 24 24" fill="none" class="icon-sm"><path d="M12 4 3 9l9 5 9-5-9-5Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M3 14l9 5 9-5M3 9.5v0" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
          <span class="trip-style-btn-label">Map</span>
        </button>
      `)

      const menu = document.createElement('div')
      menu.className = 'trip-style-menu'
      menu.hidden = true
      menu.setAttribute('role', 'menu')

      function closeMenu() {
        menu.hidden = true
        toggleBtn.setAttribute('aria-expanded', 'false')
      }

      MAP_STYLES.forEach((style) => {
        const option = svgEl<HTMLButtonElement>(`
          <button type="button" class="trip-style-option" role="menuitemradio" data-style="${style.id}">
            <span class="trip-style-swatch trip-style-swatch--${style.id}" aria-hidden="true"></span>
            <span>${style.label}</span>
          </button>
        `)
        option.classList.toggle('is-active', style.id === activeId)
        option.setAttribute('aria-checked', String(style.id === activeId))
        option.addEventListener('click', () => {
          if (style.id === activeId) {
            closeMenu()
            return
          }
          activeId = style.id
          menu.querySelectorAll('.trip-style-option').forEach((el) => {
            const isActive = (el as HTMLElement).dataset.style === activeId
            el.classList.toggle('is-active', isActive)
            el.setAttribute('aria-checked', String(isActive))
          })
          closeMenu()
          onStyleChange(style.url)
        })
        menu.appendChild(option)
      })

      toggleBtn.addEventListener('click', () => {
        const willOpen = menu.hidden
        menu.hidden = !willOpen
        toggleBtn.setAttribute('aria-expanded', String(willOpen))
      })

      container.append(menu, toggleBtn)
      return container
    },
    onRemove() {
      container?.remove()
    },
  }
}

export interface TripMapCallbacks {
  onReady?: () => void
  onError?: (err: Error) => void
}

export interface TripMapController {
  mount: () => void
  renderInitial: (state: TripMapState) => void
  update: (state: TripMapState) => void
  destroy: () => void
}

// 'hit': the walker has actually reached it - the vivid, solid marker.
// 'generating': found (its city/coordinates are known) but its AI
// description hasn't finished yet - a checkpoint sits here for however
// long its own model call takes (core/facade.py's generate_checkpoints_
// for_trip() runs these off a small thread pool, independently per
// checkpoint, not blocking on each other).
// 'upcoming': found and described, but not reached yet - a dimmer solid
// marker than 'hit', so reaching it later still reads as a real change.
// 'ghost': the old ?debug=1-only look for a not-yet-hit checkpoint -
// unrelated to the two states above, unchanged from before.
type CheckpointMarkerKind = 'hit' | 'generating' | 'upcoming' | 'ghost'

interface CheckpointMarkerEntry {
  marker: Marker
  kind: CheckpointMarkerKind
}

export function createTripMap(containerId: string, { onReady, onError }: TripMapCallbacks = {}): TripMapController {
  let map: MapLibreMap | null = null
  let loaded = false
  let failed = false
  // Guards drawInitial() itself, not just its caller - renderInitial()
  // can legitimately be asked to draw the same state more than once (the
  // caller doesn't track whether it already drew), and re-running
  // addSource('trip-route', ...) a second time throws ("Source already
  // exists"), crashing the whole page. Reset on destroy() since remount()
  // (useTripMap.ts) always builds a brand-new createTripMap() closure
  // anyway, but cheap insurance against this flag ever leaking across
  // instances.
  let hasDrawnInitial = false
  let stallTimeoutId: number | null = null
  let pendingInitialState: TripMapState | null = null
  let youAreHereMarker: Marker | null = null
  let currentState: TripMapState | null = null
  const checkpointMarkersByNumber = new Map<number, CheckpointMarkerEntry>()

  function armStallTimeout() {
    if (document.hidden) return
    stallTimeoutId = window.setTimeout(() => {
      if (loaded || failed) return
      failed = true
      onError?.(new Error('Map took too long to load'))
    }, LOAD_STALL_TIMEOUT_MS)
  }

  function disarmStallTimeout() {
    if (stallTimeoutId !== null) {
      window.clearTimeout(stallTimeoutId)
      stallTimeoutId = null
    }
  }

  function onVisibilityChange() {
    if (loaded || failed) return
    if (document.hidden) disarmStallTimeout()
    else armStallTimeout()
  }

  function destroy() {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    disarmStallTimeout()
    if (map) {
      map.remove()
      map = null
    }
    youAreHereMarker = null
    currentState = null
    hasDrawnInitial = false
    checkpointMarkersByNumber.clear()
  }

  const CHECKPOINT_MARKER_CLASS: Record<CheckpointMarkerKind, string> = {
    hit: 'trip-marker-checkpoint',
    upcoming: 'trip-marker-checkpoint is-upcoming',
    generating: 'trip-marker-checkpoint is-generating',
    ghost: 'trip-marker-checkpoint is-ghost',
  }

  // Every checkpoint gets a marker the moment it exists - not just once
  // hit - so the progressive reveal (core/facade.py's
  // generate_checkpoints_for_trip(), streamed in over GET /api/journey/
  // {trip_id}/events) is visible on the map as it happens, generating vs.
  // described distinguished visually (kind, above) until the walker
  // actually reaches one. ?debug=1's old dashed-ghost look for a
  // not-yet-hit checkpoint is unchanged, just no longer the only way to
  // see one before it's hit.
  function applyCheckpoints(checkpoints: TripMapState['checkpoints']) {
    if (!map) return
    checkpoints.forEach((checkpoint) => {
      const existing = checkpointMarkersByNumber.get(checkpoint.checkpoint_number)
      const kind: CheckpointMarkerKind = checkpoint.hit
        ? 'hit'
        : DEBUG
          ? 'ghost'
          : checkpoint.description_status === 'ready'
            ? 'upcoming'
            : 'generating'

      if (existing && existing.kind === kind) return

      existing?.marker.remove()
      const marker = new Marker({ element: createMarkerElement(CHECKPOINT_MARKER_CLASS[kind]) })
        .setLngLat(toLngLat(checkpoint.coords))
        .addTo(map as MapLibreMap)
      checkpointMarkersByNumber.set(checkpoint.checkpoint_number, { marker, kind })
    })
  }

  function addRouteLayers(state: TripMapState) {
    if (!map) return
    map.addSource('trip-route', { type: 'geojson', data: routeLineGeoJson(state.route_geometry) })
    map.addLayer({
      id: 'trip-route-line',
      type: 'line',
      source: 'trip-route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#9aa0a6', 'line-width': 3, 'line-dasharray': [2, 2] },
    })

    map.addSource('trip-walked', { type: 'geojson', data: routeLineGeoJson(state.walked_geometry) })
    map.addLayer({
      id: 'trip-walked-line',
      type: 'line',
      source: 'trip-walked',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#1e8e3e', 'line-width': 5 },
    })
  }

  function resetView() {
    if (!map || !currentState) return
    map.fitBounds(boundsForRoute(currentState.route_geometry), {
      padding: FIT_BOUNDS_PADDING,
      bearing: 0,
      pitch: 0,
      duration: 500,
    })
  }

  function switchStyle(styleUrl: string) {
    if (!map) return
    map.setStyle(styleUrl)
    map.once('style.load', () => {
      if (currentState) addRouteLayers(currentState)
    })
  }

  function drawInitial(state: TripMapState) {
    if (!map || hasDrawnInitial) return
    hasDrawnInitial = true
    currentState = state
    map.fitBounds(boundsForRoute(state.route_geometry), { padding: FIT_BOUNDS_PADDING, animate: false })

    addRouteLayers(state)

    new Marker({ element: createMarkerElement('trip-marker-pin trip-marker-start') }).setLngLat(toLngLat(state.start)).addTo(map)
    new Marker({ element: createMarkerElement('trip-marker-pin trip-marker-end') }).setLngLat(toLngLat(state.end)).addTo(map)

    youAreHereMarker = new Marker({ element: createMarkerElement('trip-marker-you') }).setLngLat(toLngLat(state.current_position)).addTo(map)

    applyCheckpoints(state.checkpoints)
    onReady?.()
  }

  function mount() {
    map = new MapLibreMap({
      container: containerId,
      style: MAP_STYLE,
      center: [0, 20],
      zoom: 1,
      pitchWithRotate: false,
      touchPitch: false,
      dragPan: { linearity: 0.3, maxSpeed: 1400, deceleration: 3500 },
    })

    map.addControl(buildNavControl({ onResetView: resetView }), 'bottom-right')
    map.addControl(buildStyleControl({ onStyleChange: switchStyle }), 'bottom-right')

    armStallTimeout()
    document.addEventListener('visibilitychange', onVisibilityChange)

    map.on('error', (e: MapLibreErrorEvent) => {
      if (loaded || failed) return
      failed = true
      disarmStallTimeout()
      onError?.(e.error instanceof Error ? e.error : new Error('Map failed to load'))
    })

    map.on('load', () => {
      if (failed) return
      loaded = true
      disarmStallTimeout()
      document.removeEventListener('visibilitychange', onVisibilityChange)
      if (pendingInitialState) {
        drawInitial(pendingInitialState)
        pendingInitialState = null
      }
    })
  }

  function renderInitial(state: TripMapState) {
    if (!map || failed) return
    if (loaded) drawInitial(state)
    else pendingInitialState = state
  }

  function update(state: TripMapState) {
    if (!map || !loaded) return
    currentState = state
    const walkedSource = map.getSource('trip-walked') as GeoJSONSource | undefined
    walkedSource?.setData(routeLineGeoJson(state.walked_geometry))
    youAreHereMarker?.setLngLat(toLngLat(state.current_position))
    applyCheckpoints(state.checkpoints)
  }

  return { mount, renderInitial, update, destroy }
}
