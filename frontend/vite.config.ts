import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev-only: forwards everything the FastAPI backend owns (app.py's
// routers) to uvicorn on :8000, so `npm run dev` can call the same
// same-origin paths (/api/..., /auth/..., /notifications/...) the
// production build will hit once app.py serves this app's build output
// directly - no separate API base URL to configure per environment.
const BACKEND_URL = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  // MapLibre GL spins up its own web worker internally via a relative
  // `new Worker(new URL(...))` - Vite's dev-time dependency pre-bundling
  // (esbuild) rewrites that URL and breaks it ("Worker failed to load"),
  // confirmed live. Excluding it from optimizeDeps serves it unbundled in
  // dev, where that pattern works correctly; the production build
  // (Rollup, not esbuild) never hits this.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
  worker: {
    format: 'es',
  },
  server: {
    proxy: {
      '/api': BACKEND_URL,
      '/auth': BACKEND_URL,
      '/notifications': BACKEND_URL,
    },
  },
  // `vite preview` (serving the production build locally) needs its own
  // copy of the same proxy - it doesn't inherit `server.proxy`.
  preview: {
    proxy: {
      '/api': BACKEND_URL,
      '/auth': BACKEND_URL,
      '/notifications': BACKEND_URL,
    },
  },
})
