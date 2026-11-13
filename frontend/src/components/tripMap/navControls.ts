// navControls.ts
import type { IControl, Map as MapLibreMap } from 'maplibre-gl'
import { svgEl } from './domHelpers'

export function buildNavControl({ onResetView }: { onResetView: () => void }): IControl {
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

      const ZOOM_LIMIT_EPSILON = 0.001
      updateZoomButtons = () => {
        if (!map) return
        const zoom = map.getZoom()
        zoomInBtn.disabled = zoom >= map.getMaxZoom() - ZOOM_LIMIT_EPSILON
        zoomOutBtn.disabled = zoom <= map.getMinZoom() + ZOOM_LIMIT_EPSILON
      }
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

export function buildLocateControl({ onLocate }: { onLocate: () => void }): IControl {
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
