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
// Real small renders of each style (same Golden Gate Bridge view, labels
// off) rather than flat CSS-gradient placeholders, so the Map Settings
// popover's swatches actually show what each style looks like.
import libertyThumb from '../assets/map-styles/liberty.png'
import brightThumb from '../assets/map-styles/bright.png'
import positronThumb from '../assets/map-styles/positron.png'

setWorkerUrl(maplibreWorkerUrl)

// Exported so CreatePage.tsx can warm the browser's HTTP cache with this
// exact URL while someone's still filling out the form - see its own
// comment for why.
export const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

// The default view's own starting zoom once a real start-coordinate hint
// lands (setStartHint()) - close enough to see the immediate area, not so
// close that the later fitBounds()-to-the-whole-route reads as a jarring
// second jump. Both moves are instant (jumpTo/fitBounds with
// animate:false) precisely so two snaps don't read as competing
// animations.
const START_HINT_ZOOM = 10

// The "locate me" button's close-up zoom - the trip-nav-control's locate
// icon (buildLocateControl below) jumps in to at least this level.
const LOCATE_ZOOM = 15

// A world map tile is 512px wide at zoom 0, doubling each zoom level - so
// this is the lowest zoom at which a single copy of the world is at
// least as wide as the given viewport. Below it, MapLibre would have to
// either tile a second copy into view (the "double countries" bug - two
// copies of the same coastline visible at once because the one copy
// doesn't fill the screen) or leave blank space past +/-180deg. Panning
// itself stays completely free at any zoom (renderWorldCopies defaults
// to true, so longitude just wraps, same as Google Maps) - this is only
// about never letting a second copy become simultaneously visible.
// Recomputed on resize (mount() below) since it depends on viewport
// width, not a fixed constant.
function minZoomForWidth(widthPx: number): number {
  return Math.log2(Math.max(1, widthPx) / 512) + 0.1
}

interface MapLibreStyleForPrewarm {
  sprite?: string
  glyphs?: string
  layers?: { layout?: { 'text-font'?: string[] } }[]
}

// Best-effort HTTP-cache warm-up for the trip map's style/sprite/glyph
// assets - callable before any real map exists (CreatePage.tsx calls this
// on mount, while someone's still filling out the form). These are the
// fixed, location-independent resources every trip map needs regardless
// of route, so warming them here means the real map (mounted once "Start
// Walking" opens TripDetailPage) finds them already in the browser's HTTP
// cache instead of being the first thing to ask for them. Deliberately
// NOT a real MapLibre instance - a plain fetch() of the same URLs the
// real map will request gets the same HTTP-cache benefit without the
// complexity/lifecycle risk of a second live WebGL context (its own
// worker, its own GL state) sitting around unused for however long
// someone stays on the Create screen.
//
// Doesn't touch tiles themselves - their URLs depend on where the route
// actually is, unknown until /api/journey/start resolves, so there's
// nothing location-specific to prefetch yet.
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
        // Range "0-255" (Basic Latin + Latin-1 Supplement) is what any
        // plain English place-name label needs - the one range every
        // font here is essentially guaranteed to request immediately.
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

// left/right/bottom are plain breathing-room margins - nothing overlaps
// those edges of the map today. 'top' is NOT included here on purpose: the
// start/destination pill stack (.trip-route-stack) sits top-left over the
// map and grows/shrinks with its own CSS (pill height, font-size, etc.),
// so a fixed top number silently goes stale the moment that CSS changes -
// it used to hide the start marker under the pills after the pills were
// made taller. currentFitPadding() below measures the real rendered
// .trip-route-stack every time instead, so resetView()/drawInitial() stay
// correct regardless of how big that overlay currently renders.
const FIT_BOUNDS_PADDING_SIDES = { bottom: 110, left: 50, right: 70 }
// Only used before .trip-route-stack exists in the DOM yet (there's
// nothing to measure) - immediately superseded by a real measurement on
// the very next fitBounds call.
const FIT_BOUNDS_TOP_FALLBACK = 120
// Extra breathing room below the measured pill stack so the start marker
// isn't just barely peeking out from under it.
const FIT_BOUNDS_TOP_MARGIN = 20

const MAP_STYLES = [
  { id: 'liberty', label: 'Standard', url: 'https://tiles.openfreemap.org/styles/liberty', thumb: libertyThumb },
  { id: 'bright', label: 'Bright', url: 'https://tiles.openfreemap.org/styles/bright', thumb: brightThumb },
  { id: 'positron', label: 'Light', url: 'https://tiles.openfreemap.org/styles/positron', thumb: positronThumb },
]

interface ColorOption {
  id: string
  label: string
  hex: string
}

// The ACTUAL route line ('trip-route-line') - the full planned path, drawn
// the same regardless of how much of it has been walked. 'slate' is first
// so it stays the default (addRouteLayers below seeds activeRouteLineColor
// from ROUTE_COLORS[0]) - the same quiet gray this line always rendered
// before this toggle existed (see the revert documented right on that
// layer's paint, below), so picking no color keeps today's look.
const ROUTE_COLORS: ColorOption[] = [
  { id: 'slate', label: 'Slate', hex: '#9aa0a6' },
  { id: 'sand', label: 'Sand', hex: '#c9a66b' },
  { id: 'mist', label: 'Mist', hex: '#8fa8c9' },
]

// The PROGRESS line ('trip-walked-line') - just the portion already
// walked, separate from the route colors above since this is the one that
// visibly grows/fills in as someone walks. 'moss' is first so it stays the
// default (activeProgressLineColor below) - the same green this line
// always rendered before this toggle existed.
const PROGRESS_COLORS: ColorOption[] = [
  { id: 'moss', label: 'Moss', hex: '#1e8e3e' },
  { id: 'canyon', label: 'Canyon', hex: '#c5572b' },
  { id: 'glacier', label: 'Glacier', hex: '#2f7dc9' },
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
  let updateZoomButtons: (() => void) | null = null

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

      // Greyed out (disabled) right at either limit, same affordance as
      // Google Maps' own +/- buttons - a small epsilon absorbs the
      // floating-point zoom values MapLibre's own easing leaves behind.
      const ZOOM_LIMIT_EPSILON = 0.001
      updateZoomButtons = () => {
        if (!map) return
        const zoom = map.getZoom()
        zoomInBtn.disabled = zoom >= map.getMaxZoom() - ZOOM_LIMIT_EPSILON
        zoomOutBtn.disabled = zoom <= map.getMinZoom() + ZOOM_LIMIT_EPSILON
      }
      // 'resize' too - the min zoom (and so which button should be
      // greyed out) depends on viewport width (see minZoomForWidth
      // below), which changes without a 'zoom' event of its own.
      mapInstance.on('zoom', updateZoomButtons)
      mapInstance.on('resize', updateZoomButtons)
      updateZoomButtons()

      container.append(resetBtn, zoomWrap)
      return container
    },
    onRemove() {
      if (map && updateZoomButtons) {
        map.off('zoom', updateZoomButtons)
        map.off('resize', updateZoomButtons)
      }
      container?.remove()
      map = null
      updateZoomButtons = null
    },
  }
}

// A single round button - "where am I right now" - sitting between the
// map-settings icon and the reset-view/zoom stack (mount() below controls
// that ordering). Its own tiny IControl since it doesn't share any state
// with either of those.
function buildLocateControl({ onLocate }: { onLocate: () => void }): IControl {
  let container: HTMLElement | null = null

  return {
    onAdd() {
      container = document.createElement('div')
      container.className = 'maplibregl-ctrl trip-locate-control'

      const btn = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-ctrl-btn trip-locate-btn" aria-label="Center on my location">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3.2" fill="currentColor" />
            <path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
          </svg>
        </button>
      `)
      btn.addEventListener('click', () => onLocate())

      container.append(btn)
      return container
    },
    onRemove() {
      container?.remove()
    },
  }
}

// The "Map Settings" popover lives on document.body, not inside the
// small maplibregl-ctrl container that holds its toggle button - it
// needs to sit above the entire app (back/pause/stat-pill overlay
// included), not just clipped/stacked within the map's own
// corner-control box. Content modeled on Strava's own "Map Settings"
// panel (header + close, a divider, then a "Map Styles" heading with one
// swatch per style) - scoped down to just the one section we actually
// have real styles for - but anchored as a card popping up right above
// the toggle button itself, not a full-width sheet sliding up from the
// bottom of the screen.
function buildStyleControl({
  onStyleChange,
  onRouteColorChange,
  onProgressColorChange,
}: {
  onStyleChange: (styleUrl: string) => void
  onRouteColorChange: (hex: string) => void
  onProgressColorChange: (hex: string) => void
}): IControl {
  let activeId = MAP_STYLES[0].id
  // Each color section tracks its own selection independently - a plain
  // mutable holder (rather than a local variable) so the shared
  // renderColorOptions() helper below can read/write it by reference.
  const routeColorState = { activeId: ROUTE_COLORS[0].id }
  const progressColorState = { activeId: PROGRESS_COLORS[0].id }
  let container: HTMLElement | null = null
  let toggleBtn: HTMLButtonElement | null = null
  let backdrop: HTMLElement | null = null

  function closeSheet() {
    if (!backdrop) return
    backdrop.remove()
    backdrop = null
    document.removeEventListener('keydown', onKeydown)
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') closeSheet()
  }

  // Shared by both the "Route Color" and "Progress Color" sections below -
  // same swatch-button markup/active-state bookkeeping, just pointed at a
  // different color list, state holder, and change callback.
  function renderColorOptions(
    row: HTMLElement,
    colors: ColorOption[],
    state: { activeId: string },
    onChange: (hex: string) => void,
  ) {
    colors.forEach((color) => {
      const option = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-map-color-option" data-color="${color.id}" aria-pressed="${color.id === state.activeId}">
          <span class="trip-color-swatch" style="background:${color.hex}" aria-hidden="true"></span>
          <span class="trip-map-style-label">${color.label}</span>
        </button>
      `)
      option.classList.toggle('is-active', color.id === state.activeId)
      option.addEventListener('click', () => {
        if (color.id === state.activeId) return
        state.activeId = color.id
        row.querySelectorAll('.trip-map-color-option').forEach((el) => {
          const isActive = (el as HTMLElement).dataset.color === state.activeId
          el.classList.toggle('is-active', isActive)
          el.setAttribute('aria-pressed', String(isActive))
        })
        onChange(color.hex)
      })
      row.appendChild(option)
    })
  }

  function openSheet() {
    if (backdrop || !toggleBtn) return

    backdrop = svgEl<HTMLDivElement>(`
      <div class="trip-map-settings-backdrop">
        <div class="trip-map-settings-sheet" role="dialog" aria-modal="true" aria-label="Map Settings">
          <div class="trip-map-settings-header">
            <h2>Map Settings</h2>
            <button type="button" class="trip-map-settings-close" aria-label="Close">
              <svg viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            </button>
          </div>
          <div class="trip-map-settings-divider"></div>
          <div class="trip-map-settings-body">
            <h3 class="trip-map-settings-subheading">Map Styles</h3>
            <div class="trip-map-settings-styles"></div>
          </div>
          <div class="trip-map-settings-divider"></div>
          <div class="trip-map-settings-body">
            <h3 class="trip-map-settings-subheading">Route Color</h3>
            <div class="trip-map-settings-colors trip-map-settings-route-colors"></div>
          </div>
          <div class="trip-map-settings-divider"></div>
          <div class="trip-map-settings-body">
            <h3 class="trip-map-settings-subheading">Progress Color</h3>
            <div class="trip-map-settings-colors trip-map-settings-progress-colors"></div>
          </div>
        </div>
      </div>
    `)

    // Anchor the card just above-right-aligned to the toggle button
    // (fixed positioning, computed from its live rect since this card
    // lives on document.body, outside the map's own corner-control box)
    // - "pops up from the map icon" instead of sliding up from the
    // bottom of the screen.
    const sheet = backdrop.querySelector('.trip-map-settings-sheet') as HTMLElement
    const btnRect = toggleBtn.getBoundingClientRect()
    sheet.style.position = 'fixed'
    sheet.style.bottom = `${window.innerHeight - btnRect.top + 12}px`
    sheet.style.right = `${window.innerWidth - btnRect.right}px`

    const stylesRow = backdrop.querySelector('.trip-map-settings-styles') as HTMLElement
    MAP_STYLES.forEach((style) => {
      const option = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-map-style-option" data-style="${style.id}" aria-pressed="${style.id === activeId}">
          <img class="trip-style-swatch" src="${style.thumb}" alt="" aria-hidden="true" width="56" height="56" />
          <span class="trip-map-style-label">${style.label}</span>
        </button>
      `)
      option.classList.toggle('is-active', style.id === activeId)
      option.addEventListener('click', () => {
        if (style.id === activeId) return
        activeId = style.id
        stylesRow.querySelectorAll('.trip-map-style-option').forEach((el) => {
          const isActive = (el as HTMLElement).dataset.style === activeId
          el.classList.toggle('is-active', isActive)
          el.setAttribute('aria-pressed', String(isActive))
        })
        onStyleChange(style.url)
      })
      stylesRow.appendChild(option)
    })

    const routeColorsRow = backdrop.querySelector('.trip-map-settings-route-colors') as HTMLElement
    renderColorOptions(routeColorsRow, ROUTE_COLORS, routeColorState, onRouteColorChange)

    const progressColorsRow = backdrop.querySelector('.trip-map-settings-progress-colors') as HTMLElement
    renderColorOptions(progressColorsRow, PROGRESS_COLORS, progressColorState, onProgressColorChange)

    // Click anywhere outside the card itself (i.e. the backdrop) closes
    // it - the old small dropdown had no such handler at all, so the only
    // way to dismiss it was clicking its own toggle button a second time.
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeSheet()
    })
    backdrop.querySelector('.trip-map-settings-close')?.addEventListener('click', closeSheet)
    document.addEventListener('keydown', onKeydown)
    document.body.appendChild(backdrop)
  }

  return {
    onAdd() {
      container = document.createElement('div')
      container.className = 'maplibregl-ctrl trip-style-control'

      toggleBtn = svgEl<HTMLButtonElement>(`
        <button type="button" class="trip-ctrl-btn trip-style-btn" aria-haspopup="dialog" aria-label="Map settings">
          <svg viewBox="0 0 24 24" fill="none"><path d="M3 7.5 9 5l6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5V7.5Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><path d="M9 5v13.5M15 7.5V21" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>
        </button>
      `)
      toggleBtn.addEventListener('click', openSheet)

      container.append(toggleBtn)
      return container
    },
    onRemove() {
      container?.remove()
      closeSheet()
    },
  }
}

export interface TripMapCallbacks {
  onReady?: () => void
  onError?: (err: Error) => void
}

export interface TripMapController {
  mount: () => void
  // An instant, unanimated camera move to roughly where the trip starts -
  // safe to call the moment start coordinates are known (route data lands
  // well before the style/tiles do), regardless of load state. See
  // renderInitial() below, which calls this itself; exposed separately in
  // case a caller ever has the start coordinate before the rest of the
  // state (it doesn't today).
  setStartHint: (coords: Coordinates) => void
  renderInitial: (state: TripMapState) => void
  update: (state: TripMapState) => void
  destroy: () => void
}

// 'hit': the walker has actually reached it - a solid green marker (the
// same hue as the walked line, so the trail of hit checkpoints reads as
// part of the completed path rather than competing with what's ahead).
// 'generating': found (its city/coordinates are known) but its AI
// description hasn't finished yet - a checkpoint sits here for however
// long its own model call takes (core/facade.py's generate_checkpoints_
// for_trip() runs these off a small thread pool, independently per
// checkpoint, not blocking on each other).
// 'next': the single closest not-yet-reached checkpoint - the only one
// that gets the full saturated "look here" yellow pop. A route with a
// dozen upcoming checkpoints used to render a dozen equally-loud yellow
// dots; only the immediate next stop earns that now.
// 'upcoming': found and described, further out than 'next' - a small,
// muted, desaturated tick instead of a competing marker, so the string
// of them reads as a quiet trail rather than clutter.
// 'ghost': the old ?debug=1-only look for a not-yet-hit checkpoint -
// unrelated to the states above, unchanged from before.
type CheckpointMarkerKind = 'hit' | 'generating' | 'next' | 'upcoming' | 'ghost'

interface CheckpointMarkerEntry {
  marker: Marker
  kind: CheckpointMarkerKind
}

export function createTripMap(containerId: string, { onReady, onError }: TripMapCallbacks = {}): TripMapController {
  let map: MapLibreMap | null = null
  // True once MapLibre's 'style.load' fires - the style JSON is parsed,
  // sprite/sources are registered, and addSource()/addLayer() are safe to
  // call. Deliberately NOT the same as the full 'load' event (which
  // additionally waits for every tile in the current viewport to finish
  // downloading) - gating route-drawing on 'load' was the main reason the
  // map used to sit blank for several extra seconds after the style
  // itself was already usable. Tiles keep loading/painting on their own
  // after this either way; nothing here waits on them.
  let styleLoaded = false
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
  // Both survive a base-map style switch (map.setStyle() wipes every
  // custom layer, so switchStyle() below re-runs addRouteLayers() from
  // scratch) - addRouteLayers() reads these instead of hardcoded hex
  // values, so a chosen color sticks across a style change instead of
  // resetting to the default.
  let activeRouteLineColor = ROUTE_COLORS[0].hex
  let activeProgressLineColor = PROGRESS_COLORS[0].hex
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

  // A checkpoint only gets a marker once the walker has actually come
  // within this trip's own reveal radius of it (checkpoint.revealed -
  // core/facade.py's proximity-reveal, independent of whether its name/
  // description have resolved yet) - every checkpoint's *position*
  // exists from the moment the trip was created, but showing all of
  // them immediately would spoil the gradual-reveal effect the radius is
  // for. Once revealed, a checkpoint's marker stays up for the rest of
  // the trip - revealed is never un-set server-side, and nothing here
  // ever removes a marker for a checkpoint still reporting revealed, so
  // walking away from one doesn't make it disappear again. generating
  // vs. described (kind, below) is distinguished visually until the
  // walker actually reaches one. ?debug=1's old dashed-ghost look for a
  // not-yet-hit checkpoint is unchanged, just only shown for ones
  // already revealed.
  function applyCheckpoints(checkpoints: TripMapState['checkpoints']) {
    if (!map) return

    // The lowest checkpoint_number not yet hit - the single marker that
    // gets to be the loud "next stop" one. Found by scanning rather than
    // trusting incoming order, since applyCheckpoints() is also called
    // from checkpoint_added/checkpoint_updated events that can arrive in
    // any order.
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
      const marker = new Marker({ element: createMarkerElement(CHECKPOINT_MARKER_CLASS[kind]) })
        .setLngLat(toLngLat(checkpoint.coords))
        .addTo(map as MapLibreMap)
      checkpointMarkersByNumber.set(checkpoint.checkpoint_number, { marker, kind })
    })
  }

  // Shrinks checkpoint markers at country-wide zoom (where a dozen
  // full-size dots strung along the route would read as a texture, not
  // a path) and lets them grow back in as someone zooms into a region.
  // Driven through a CSS custom property on the map container rather
  // than a `transform: scale()` on the marker element itself, since
  // MapLibre's own Marker positioning already owns that element's
  // `transform` (translate) - a competing transform would just get
  // clobbered. See .trip-marker-checkpoint's `calc(... * var(...))`
  // width/height for the consuming side.
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

  // Re-measures .trip-route-stack's actual rendered bottom edge every
  // call, rather than trusting a remembered pixel value - so resetView()
  // and drawInitial() always leave enough room for whatever that overlay
  // currently renders at (pill height, font-size, a future redesign, a
  // narrower viewport that wraps it taller, etc.), not just whatever its
  // size happened to be when this constant was last tuned by hand.
  // Scoped to this map's own .trip-view ancestor (not a bare
  // document-wide query) so this stays correct once multiple trip maps
  // can exist on the page at once.
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

  // A close-up "where am I right now" jump - same 500ms easing as
  // resetView() above, just a single point instead of fitBounds()-ing the
  // whole route. Zooms IN to at least LOCATE_ZOOM but never back out past
  // whatever the walker was already zoomed to - re-centering shouldn't
  // also yank someone's deliberate zoom-out back in.
  function locateToMe() {
    if (!map || !currentState) return
    map.easeTo({
      center: toLngLat(currentState.current_position),
      zoom: Math.max(map.getZoom(), LOCATE_ZOOM),
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

  // Most paint changes just need setPaintProperty() on the live layer -
  // addRouteLayers() only has to be re-run (from scratch, via switchStyle
  // above) when the base style itself changes out from under the layer.
  // 'trip-route-line' is the full planned path, drawn the same regardless
  // of progress - this recolors the whole thing, not just what's ahead.
  function setRouteLineColor(hex: string) {
    activeRouteLineColor = hex
    if (map?.getLayer('trip-route-line')) {
      map.setPaintProperty('trip-route-line', 'line-color', hex)
    }
  }

  // 'trip-walked-line' is only the portion already walked - this is the
  // one that visibly grows/fills in as progress is made.
  function setProgressLineColor(hex: string) {
    activeProgressLineColor = hex
    if (map?.getLayer('trip-walked-line')) {
      map.setPaintProperty('trip-walked-line', 'line-color', hex)
    }
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
    // Instant (no animate option = jumpTo's default, unanimated) - the
    // map may still be on its generic default view (mount()'s center/zoom
    // below) or mid-style-load; either way this is safe to call any time
    // after mount(), and drawInitial()'s later fitBounds (also
    // unanimated) is the only other camera move, so this never competes
    // with a second in-flight animation.
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

    // minZoomForWidth depends on viewport width, so it's wrong the moment
    // the window/orientation changes - keep it current. MapLibre's own
    // 'resize' event (it watches the container with a ResizeObserver)
    // covers rotation/split-view as well as a plain window resize. No
    // manual cleanup needed - map.remove() (destroy() below) tears down
    // every listener on this map instance along with it.
    map.on('resize', () => {
      if (!map) return
      map.setMinZoom(minZoomForWidth(map.getContainer().clientWidth))
    })

    map.on('zoom', updateCheckpointScale)

    // Order matters: MapLibre stacks each newly-added bottom-right control
    // above the previous ones, so last-added ends up visually topmost -
    // this order puts the locate button right below the map-settings
    // icon, above the reset-view/zoom stack, matching how it was asked
    // for (confirmed against the actual bug this same quirk caused for
    // the map-settings button - see .trip-style-control's own comment).
    map.addControl(buildNavControl({ onResetView: resetView }), 'bottom-right')
    map.addControl(buildLocateControl({ onLocate: locateToMe }), 'bottom-right')
    map.addControl(
      buildStyleControl({ onStyleChange: switchStyle, onRouteColorChange: setRouteLineColor, onProgressColorChange: setProgressLineColor }),
      'bottom-right',
    )

    armStallTimeout()
    document.addEventListener('visibilitychange', onVisibilityChange)

    map.on('error', (e: MapLibreErrorEvent) => {
      if (styleLoaded || failed) return
      failed = true
      disarmStallTimeout()
      onError?.(e.error instanceof Error ? e.error : new Error('Map failed to load'))
    })

    // 'style.load' (not 'load' - see styleLoaded's own comment above)
    // fires once the style/sprite/sources are parsed and ready, well
    // before every tile in view has finished downloading - the earliest
    // point drawInitial() can safely add the route/markers.
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
