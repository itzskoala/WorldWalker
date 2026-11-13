// index.ts
import { ErrorEvent as MapLibreErrorEvent, GeoJSONSource, LngLatBounds, Map as MapLibreMap, Marker, ScaleControl, setWorkerUrl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Coordinates, TripMapState } from '../../types/trip'
import { MAP_STYLES, ROUTE_COLORS, PROGRESS_COLORS } from './mapStyles'
import { buildNavControl, buildLocateControl } from './navControls'
import { buildStyleSwitcherControl } from './styleSwitcherControl'

setWorkerUrl(maplibreWorkerUrl)

export const MAP_STYLE = MAP_STYLES[0].url

const START_HINT_ZOOM = 10
const LOCATE_ZOOM = 15

function minZoomForWidth(widthPx: number): number {
  return Math.log2(Math.max(1, widthPx) / 512) + 0.1
}

interface MapLibreStyleForPrewarm {
  sprite?: string
  glyphs?: string
  layers?: { layout?: { 'text-font'?: string[] } }[]
}

export function prewarmMapAssets(): void {
  fetch(MAP_STYLE)
    .then((res) => (res.ok ? (res.json() as Promise<MapLibreStyleForPrewarm>) : null))
    .then((style) => {
      if (!style) return

      if (style.sprite) {
        for (const suffix of ['.json', '.png', '@2x.json', '@2x.png']) {
          fetch(`${style.sprite}${suffix}`).catch(() => {})
        }
      }

      if (style.glyphs) {
        const fonts = new Set<string>()
        for (const layer of style.layers ?? []) {
          layer.layout?.['text-font']?.forEach((font) => fonts.add(font))
        }
        for (const font of fonts) {
          const url = style.glyphs.replace('{fontstack}', encodeURIComponent(font)).replace('{range}', '0-255')
          fetch(url).catch(() => {})
        }
      }
    })
    .catch(() => {})
}

const DEBUG = new URLSearchParams(window.location.search).has('debug')
const LOAD_STALL_TIMEOUT_MS = 15000

const FIT_BOUNDS_PADDING_SIDES = { bottom: 110, left: 50, right: 70 }
const FIT_BOUNDS_TOP_FALLBACK = 120
const FIT_BOUNDS_TOP_MARGIN = 20

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

const CHECKPOINT_PIN_PATH = 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z'

function createCheckpointMarkerElement(className: string): HTMLDivElement {
  const element = document.createElement('div')
  element.className = className
  element.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${CHECKPOINT_PIN_PATH}" /></svg>`
  return element
}

export interface TripMapCallbacks {
  onReady?: () => void
  onError?: (err: Error) => void
}

export interface TripMapController {
  mount: () => void
  setStartHint: (coords: Coordinates) => void
  renderInitial: (state: TripMapState) => void
  update: (state: TripMapState) => void
  destroy: () => void
}

type CheckpointMarkerKind = 'hit' | 'generating' | 'next' | 'upcoming' | 'ghost'

interface CheckpointMarkerEntry {
  marker: Marker
  kind: CheckpointMarkerKind
}

export function createTripMap(containerId: string, { onReady, onError }: TripMapCallbacks = {}): TripMapController {
  let map: MapLibreMap | null = null
  let styleLoaded = false
  let failed = false
  let hasDrawnInitial = false
  let stallTimeoutId: number | null = null
  let pendingInitialState: TripMapState | null = null
  let youAreHereMarker: Marker | null = null
  let currentState: TripMapState | null = null
  let activeRouteLineColor = ROUTE_COLORS[0].hex
  let activeProgressLineColor = PROGRESS_COLORS[0].hex
  let globeEnabled = false
  const checkpointMarkersByNumber = new Map<number, CheckpointMarkerEntry>()

  function armStallTimeout() {
    if (document.hidden) return
    stallTimeoutId = window.setTimeout(() => {
      if (styleLoaded || failed) return
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
    if (styleLoaded || failed) return
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
    styleLoaded = false
    checkpointMarkersByNumber.clear()
  }

  const CHECKPOINT_MARKER_CLASS: Record<CheckpointMarkerKind, string> = {
    hit: 'trip-marker-checkpoint',
    next: 'trip-marker-checkpoint is-next',
    upcoming: 'trip-marker-checkpoint is-upcoming',
    generating: 'trip-marker-checkpoint is-generating',
    ghost: 'trip-marker-checkpoint is-ghost',
  }

  function applyCheckpoints(checkpoints: TripMapState['checkpoints']) {
    if (!map) return

    let nextCheckpointNumber: number | null = null
    for (const c of checkpoints) {
      if (!c.hit && (nextCheckpointNumber === null || c.checkpoint_number < nextCheckpointNumber)) {
        nextCheckpointNumber = c.checkpoint_number
      }
    }

    checkpoints.forEach((checkpoint) => {
      if (!checkpoint.revealed) return

      const existing = checkpointMarkersByNumber.get(checkpoint.checkpoint_number)
      const kind: CheckpointMarkerKind = checkpoint.hit
        ? 'hit'
        : DEBUG
          ? 'ghost'
          : checkpoint.description_status !== 'ready'
            ? 'generating'
            : checkpoint.checkpoint_number === nextCheckpointNumber
              ? 'next'
              : 'upcoming'

      if (existing && existing.kind === kind) return

      existing?.marker.remove()
      const marker = new Marker({ element: createCheckpointMarkerElement(CHECKPOINT_MARKER_CLASS[kind]), anchor: 'bottom' })
        .setLngLat(toLngLat(checkpoint.coords))
        .addTo(map as MapLibreMap)
      checkpointMarkersByNumber.set(checkpoint.checkpoint_number, { marker, kind })
    })
  }

  function updateCheckpointScale() {
    if (!map) return
    const el = document.getElementById(containerId)
    if (!el) return
    const zoom = map.getZoom()
    const t = Math.min(1, Math.max(0, (zoom - 3) / (9 - 3)))
    const scale = 0.55 + t * (1 - 0.55)
    el.style.setProperty('--checkpoint-scale', scale.toFixed(2))
  }

  function addRouteLayers(state: TripMapState) {
    if (!map) return
    map.addSource('trip-route', { type: 'geojson', data: routeLineGeoJson(state.route_geometry) })
    map.addLayer({
      id: 'trip-route-line',
      type: 'line',
      source: 'trip-route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': activeRouteLineColor, 'line-width': 3, 'line-dasharray': [2, 2] },
    })

    map.addSource('trip-walked', { type: 'geojson', data: routeLineGeoJson(state.walked_geometry) })
    map.addLayer({
      id: 'trip-walked-line',
      type: 'line',
      source: 'trip-walked',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': activeProgressLineColor, 'line-width': 5 },
    })
  }

  function currentFitPadding(): { top: number; bottom: number; left: number; right: number } {
    if (!map) return { ...FIT_BOUNDS_PADDING_SIDES, top: FIT_BOUNDS_TOP_FALLBACK }
    const mapRect = map.getContainer().getBoundingClientRect()
    const scope = map.getContainer().closest('.trip-view') ?? document
    const stackRect = scope.querySelector('.trip-route-stack')?.getBoundingClientRect()
    const top = stackRect ? stackRect.bottom - mapRect.top + FIT_BOUNDS_TOP_MARGIN : FIT_BOUNDS_TOP_FALLBACK
    return { ...FIT_BOUNDS_PADDING_SIDES, top }
  }

  function resetView() {
    if (!map || !currentState) return
    map.fitBounds(boundsForRoute(currentState.route_geometry), {
      padding: currentFitPadding(),
      bearing: 0,
      pitch: 0,
      duration: 500,
    })
  }

  function locateToMe() {
    if (!map || !currentState) return
    map.easeTo({
      center: toLngLat(currentState.current_position),
      zoom: Math.max(map.getZoom(), LOCATE_ZOOM),
      duration: 500,
    })
  }

  function switchStyle(styleId: string) {
    if (!map) return
    const entry = MAP_STYLES.find((s) => s.id === styleId)
    if (!entry) return
    map.setStyle(entry.url)
    map.once('style.load', () => {
      if (currentState) addRouteLayers(currentState)
      map?.setProjection({ type: globeEnabled ? 'globe' : 'mercator' })
    })
  }

  function setRouteLineColor(hex: string) {
    activeRouteLineColor = hex
    if (map?.getLayer('trip-route-line')) {
      map.setPaintProperty('trip-route-line', 'line-color', hex)
    }
  }

  function setProgressLineColor(hex: string) {
    activeProgressLineColor = hex
    if (map?.getLayer('trip-walked-line')) {
      map.setPaintProperty('trip-walked-line', 'line-color', hex)
    }
  }

  function setGlobeEnabled(enabled: boolean) {
    globeEnabled = enabled
    map?.setProjection({ type: enabled ? 'globe' : 'mercator' })
  }

  function setTiltEnabled(enabled: boolean) {
    map?.easeTo({ pitch: enabled ? 60 : 0, duration: 400 })
  }

  function drawInitial(state: TripMapState) {
    if (!map || hasDrawnInitial) return
    hasDrawnInitial = true
    currentState = state
    map.fitBounds(boundsForRoute(state.route_geometry), { padding: currentFitPadding(), animate: false })
    updateCheckpointScale()

    addRouteLayers(state)

    new Marker({ element: createMarkerElement('trip-marker-pin trip-marker-start') }).setLngLat(toLngLat(state.start)).addTo(map)
    new Marker({ element: createMarkerElement('trip-marker-pin trip-marker-end') }).setLngLat(toLngLat(state.end)).addTo(map)

    youAreHereMarker = new Marker({ element: createMarkerElement('trip-marker-you') }).setLngLat(toLngLat(state.current_position)).addTo(map)

    applyCheckpoints(state.checkpoints)
    onReady?.()
  }

  function setStartHint(coords: Coordinates) {
    if (!map) return
    map.jumpTo({ center: toLngLat(coords), zoom: START_HINT_ZOOM })
  }

  function mount() {
    const containerEl = document.getElementById(containerId)
    const initialMinZoom = minZoomForWidth(containerEl?.clientWidth ?? 512)

    map = new MapLibreMap({
      container: containerId,
      style: MAP_STYLE,
      center: [0, 20],
      zoom: initialMinZoom,
      minZoom: initialMinZoom,
      pitchWithRotate: false,
      touchPitch: false,
      dragPan: { linearity: 0.3, maxSpeed: 1400, deceleration: 3500 },
    })

    map.on('resize', () => {
      if (!map) return
      map.setMinZoom(minZoomForWidth(map.getContainer().clientWidth))
    })

    map.on('zoom', updateCheckpointScale)

    map.addControl(buildNavControl({ onResetView: resetView }), 'bottom-right')
    map.addControl(buildLocateControl({ onLocate: locateToMe }), 'bottom-right')
    map.addControl(new ScaleControl({ maxWidth: 100, unit: 'metric' }), 'bottom-left')
    map.addControl(
      buildStyleSwitcherControl({
        onStyleChange: switchStyle,
        onRouteColorChange: setRouteLineColor,
        onProgressColorChange: setProgressLineColor,
        onGlobeToggle: setGlobeEnabled,
        onTiltToggle: setTiltEnabled,
      }),
      'bottom-left',
    )

    armStallTimeout()
    document.addEventListener('visibilitychange', onVisibilityChange)

    map.on('error', (e: MapLibreErrorEvent) => {
      if (styleLoaded || failed) return
      failed = true
      disarmStallTimeout()
      onError?.(e.error instanceof Error ? e.error : new Error('Map failed to load'))
    })

    map.once('style.load', () => {
      if (failed) return
      styleLoaded = true
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
    setStartHint(state.start)
    if (styleLoaded) drawInitial(state)
    else pendingInitialState = state
  }

  function update(state: TripMapState) {
    if (!map || !styleLoaded) return
    currentState = state
    const walkedSource = map.getSource('trip-walked') as GeoJSONSource | undefined
    walkedSource?.setData(routeLineGeoJson(state.walked_geometry))
    youAreHereMarker?.setLngLat(toLngLat(state.current_position))
    applyCheckpoints(state.checkpoints)
  }

  return { mount, setStartHint, renderInitial, update, destroy }
}
