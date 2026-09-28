// Minimal ambient types for the parts of NASA WebWorldWind
// (worldwind.min.js, loaded via a plain <script> tag - no npm package)
// that src/components/WorldWindGlobe.tsx actually uses.

interface WorldWindNavigator {
  range: number
  tilt: number
  lookAtLocation: { latitude: number; longitude: number }
}

interface WorldWindWindow {
  navigator: WorldWindNavigator
  addLayer: (layer: unknown) => void
  redraw: () => void
}

interface Window {
  WorldWind?: {
    Logger: { setLoggingLevel: (level: unknown) => void; LEVEL_WARNING: unknown }
    WorldWindow: new (canvasId: string) => WorldWindWindow
    BMNGLayer: new () => unknown
    BMNGLandsatLayer: new () => unknown
    AtmosphereLayer: new () => unknown
    StarFieldLayer: new () => unknown
  }
}
