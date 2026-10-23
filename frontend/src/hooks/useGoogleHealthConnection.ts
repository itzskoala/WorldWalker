// Single source of truth for the Google Health connection status/toggle -
// the existing backend (auth/router.py's /auth/google/start|status|
// disconnect, called through api/googleHealthApi.ts), not a new
// connection system. ConnectionsPage.tsx reads this one hook instance
// (AppShell owns it - see its own docstring) instead of fetching
// GET /auth/google/status independently.

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { disconnectGoogleHealth, googleHealthStatus, startGoogleHealthConnect } from '../api/googleHealthApi'

export function useGoogleHealthConnection() {
  const { status } = useAuth()
  const [connected, setConnected] = useState(false)
  const [checked, setChecked] = useState(false)
  const [connecting, setConnecting] = useState(false)
  // The real backend error text (parseErrorMessage, see api/googleHealthApi.ts)
  // for whichever action last failed - cleared at the start of the next
  // attempt so a stale error never lingers past a retry. Surfaced by
  // ConnectionsPage.tsx, the only place this toggle lives now.
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (status !== 'authenticated') return
    googleHealthStatus()
      .then((s) => {
        setConnected(s.connected)
        setChecked(true)
      })
      .catch((err) => {
        console.warn("Couldn't check Google Health connection status:", err)
        setError(err instanceof Error ? err.message : "Couldn't check your Google Health connection.")
      })
  }, [status])

  const toggle = useCallback(async () => {
    if (connected) {
      if (!window.confirm('Disconnect your Google Health account?')) return
      setConnecting(true)
      setError(null)
      try {
        const result = await disconnectGoogleHealth()
        if (result.ok) window.location.reload()
        else setError(result.message)
      } finally {
        setConnecting(false)
      }
      return
    }

    setConnecting(true)
    setError(null)
    try {
      const { auth_url } = await startGoogleHealthConnect()
      window.location.href = auth_url
    } catch (err) {
      console.warn("Couldn't start the Google Health connection:", err)
      setError(err instanceof Error ? err.message : "Couldn't start the Google Health connection.")
    } finally {
      setConnecting(false)
    }
  }, [connected])

  return { connected, checked, connecting, error, toggle }
}

export type GoogleHealthConnection = ReturnType<typeof useGoogleHealthConnection>
