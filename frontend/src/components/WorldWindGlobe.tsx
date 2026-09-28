// Port of web/static/js/globe.js - a real NASA WebWorldWind globe used as
// a hero illustration (Google Flights uses a static drawing for the same
// spot; this is the animated equivalent). Pulled back and gently tilted
// like a title-card, not a navigable map - the canvas is pointer-events:
// none in CSS, so it never needs to react to dragging, just spins.

import { useEffect, useRef } from 'react'

export function WorldWindGlobe() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    if (!window.WorldWind) {
      console.warn('WorldWind library unavailable — header stays a plain dark band.')
      return
    }
    const WorldWind = window.WorldWind

    let frameId: number | null = null
    let wwd: ReturnType<typeof buildGlobe> | null = null

    function buildGlobe() {
      WorldWind!.Logger.setLoggingLevel(WorldWind!.Logger.LEVEL_WARNING)

      const instance = new WorldWind!.WorldWindow('globe-canvas')
      instance.addLayer(new WorldWind!.BMNGLayer())
      instance.addLayer(new WorldWind!.BMNGLandsatLayer())
      instance.addLayer(new WorldWind!.AtmosphereLayer())
      instance.addLayer(new WorldWind!.StarFieldLayer())

      instance.navigator.range = 2.4e7
      instance.navigator.tilt = 8
      instance.navigator.lookAtLocation.latitude = 18
      instance.navigator.lookAtLocation.longitude = -40
      return instance
    }

    function spin() {
      if (!wwd) return
      wwd.navigator.lookAtLocation.longitude -= 0.03
      if (wwd.navigator.lookAtLocation.longitude < -180) {
        wwd.navigator.lookAtLocation.longitude += 360
      }
      wwd.redraw()
      frameId = requestAnimationFrame(spin)
    }

    // This screen (Create) isn't necessarily the active tab when it first
    // mounts - AppShell keeps all three screens mounted and just toggles
    // `hidden` (see AppShell.tsx), so the canvas can easily be 0x0 at this
    // exact moment. WorldWindow reads the canvas's size once, at
    // construction, to pick its internal render resolution - build it
    // against a 0x0 (or otherwise wrong) canvas and CSS later stretches
    // that undersized render to fill the wide, short hero banner, which
    // is exactly what a squashed-looking globe is. A ResizeObserver
    // starts the globe the moment the canvas actually has a real size
    // (immediately, if Create already happens to be the active tab), and
    // keeps forcing a redraw on every real size change after that (a
    // window resize, or the sidebar/layout changing).
    const resizeObserver = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect
      if (width === 0 || height === 0) return
      if (!wwd) {
        wwd = buildGlobe()
        frameId = requestAnimationFrame(spin)
      } else {
        wwd.redraw()
      }
    })
    resizeObserver.observe(canvas)

    return () => {
      if (frameId !== null) cancelAnimationFrame(frameId)
      resizeObserver.disconnect()
    }
  }, [])

  return <canvas id="globe-canvas" className="globe-canvas" ref={canvasRef} aria-hidden="true" />
}
