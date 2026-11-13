// styleSwitcherControl.ts
import type { IControl } from 'maplibre-gl'
import { onActivate, svgEl } from './domHelpers'
import { MAP_STYLES, ROUTE_COLORS, PROGRESS_COLORS } from './mapStyles'
import type { ColorOption } from './mapStyles'

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

export function buildStyleSwitcherControl({
  onStyleChange,
  onRouteColorChange,
  onProgressColorChange,
  onGlobeToggle,
  onTiltToggle,
}: {
  onStyleChange: (styleId: string) => void
  onRouteColorChange: (hex: string) => void
  onProgressColorChange: (hex: string) => void
  onGlobeToggle: (enabled: boolean) => void
  onTiltToggle: (enabled: boolean) => void
}): IControl {
  let activeId = MAP_STYLES[0].id
  const routeColorState = { activeId: ROUTE_COLORS[0].id }
  const progressColorState = { activeId: PROGRESS_COLORS[0].id }
  let globeEnabled = false
  let tiltEnabled = false
  let container: HTMLElement | null = null
  let thumbBtnEl: HTMLElement | null = null
  let thumbImg: HTMLImageElement | null = null
  let thumbCaption: HTMLElement | null = null
  let strip: HTMLElement | null = null
  let backdrop: HTMLElement | null = null
  let lastCycleAt = 0

  function closeStrip() {
    strip?.classList.remove('is-open')
  }

  function openStrip() {
    strip?.classList.add('is-open')
  }

  function closeSheet() {
    if (!backdrop) return
    backdrop.remove()
    backdrop = null
    document.removeEventListener('keydown', onKeydown)
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape') return
    closeSheet()
    closeStrip()
  }

  function openSheet() {
    if (backdrop || !thumbBtnEl) return

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
            <h3 class="trip-map-settings-subheading">Route Color</h3>
            <div class="trip-map-settings-colors trip-map-settings-route-colors"></div>
          </div>
          <div class="trip-map-settings-divider"></div>
          <div class="trip-map-settings-body">
            <h3 class="trip-map-settings-subheading">Progress Color</h3>
            <div class="trip-map-settings-colors trip-map-settings-progress-colors"></div>
          </div>
          <div class="trip-map-settings-divider"></div>
          <div class="trip-map-settings-body trip-map-settings-toggles">
            <label class="trip-map-settings-globe">
              <input type="checkbox" class="trip-map-settings-globe-input" ${globeEnabled ? 'checked' : ''} />
              Globe View
            </label>
            <label class="trip-map-settings-globe">
              <input type="checkbox" class="trip-map-settings-tilt-input" ${tiltEnabled ? 'checked' : ''} />
              3D
            </label>
          </div>
        </div>
      </div>
    `)

    const sheet = backdrop.querySelector('.trip-map-settings-sheet') as HTMLElement
    const thumbRect = thumbBtnEl.getBoundingClientRect()
    sheet.style.position = 'fixed'
    sheet.style.bottom = `${window.innerHeight - thumbRect.top + 12}px`
    sheet.style.left = `${thumbRect.left}px`

    const routeColorsRow = backdrop.querySelector('.trip-map-settings-route-colors') as HTMLElement
    renderColorOptions(routeColorsRow, ROUTE_COLORS, routeColorState, onRouteColorChange)

    const progressColorsRow = backdrop.querySelector('.trip-map-settings-progress-colors') as HTMLElement
    renderColorOptions(progressColorsRow, PROGRESS_COLORS, progressColorState, onProgressColorChange)

    const tiltCheckbox = backdrop.querySelector('.trip-map-settings-tilt-input') as HTMLInputElement
    tiltCheckbox.addEventListener('change', () => {
      tiltEnabled = tiltCheckbox.checked
      onTiltToggle(tiltEnabled)
    })

    const globeCheckbox = backdrop.querySelector('.trip-map-settings-globe-input') as HTMLInputElement
    globeCheckbox.addEventListener('change', () => {
      globeEnabled = globeCheckbox.checked
      onGlobeToggle(globeEnabled)
    })

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeSheet()
    })
    backdrop.querySelector('.trip-map-settings-close')?.addEventListener('click', closeSheet)
    document.addEventListener('keydown', onKeydown)
    document.body.appendChild(backdrop)
  }

  function renderStrip() {
    if (!strip) return
    strip.innerHTML = ''

    MAP_STYLES.filter((style) => style.id !== activeId).forEach((style) => {
      const item = svgEl<HTMLDivElement>(`
        <div class="trip-style-strip-item" role="button" tabindex="0" aria-label="Switch to ${style.label}">
          <img src="${style.thumb}" alt="" width="48" height="48" />
          <span class="trip-map-style-label">${style.label}</span>
        </div>
      `)
      onActivate(item, () => {
        activeId = style.id
        if (thumbImg) thumbImg.src = style.thumb
        if (thumbCaption) thumbCaption.textContent = style.label
        onStyleChange(style.id)
        renderStrip()
        closeStrip()
      })
      strip?.appendChild(item)
    })

    const moreBtn = svgEl<HTMLDivElement>(`
      <div class="trip-style-strip-more" role="button" tabindex="0" aria-haspopup="dialog" aria-label="More map options">
        <span class="trip-style-more-icon">
          <svg viewBox="0 0 24 24" fill="none"><path d="M3 7.5 9 5l6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5V7.5Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><path d="M9 5v13.5M15 7.5V21" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>
        </span>
        <span class="trip-map-style-label">More</span>
      </div>
    `)
    onActivate(moreBtn, openSheet)
    strip.appendChild(moreBtn)
  }

  return {
    onAdd() {
      container = document.createElement('div')
      container.className = 'maplibregl-ctrl trip-style-control'

      const thumbBtn = svgEl<HTMLDivElement>(`
        <div class="trip-style-thumb-btn" role="button" tabindex="0" aria-label="Switch map style">
          <img src="${MAP_STYLES[0].thumb}" alt="" />
          <span class="trip-style-thumb-caption">${MAP_STYLES[0].label}</span>
        </div>
      `)
      thumbBtnEl = thumbBtn
      thumbImg = thumbBtn.querySelector('img')
      thumbCaption = thumbBtn.querySelector('.trip-style-thumb-caption')
      onActivate(thumbBtn, () => {
        const now = Date.now()
        if (now - lastCycleAt < 400) return
        lastCycleAt = now
        const currentIndex = MAP_STYLES.findIndex((style) => style.id === activeId)
        const next = MAP_STYLES[(currentIndex + 1) % MAP_STYLES.length]
        activeId = next.id
        if (thumbImg) thumbImg.src = next.thumb
        if (thumbCaption) thumbCaption.textContent = next.label
        onStyleChange(next.id)
        renderStrip()
      })

      strip = svgEl<HTMLDivElement>('<div class="trip-style-strip"></div>')
      renderStrip()

      container.append(thumbBtn, strip)
      container.addEventListener('mouseenter', openStrip)
      container.addEventListener('mouseleave', closeStrip)

      return container
    },
    onRemove() {
      container?.remove()
      closeSheet()
    },
  }
}
