// Port of web/templates/index.html's <header class="topbar"> +
// web/static/js/app.js's theme-toggle/connect-button wiring.

import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../hooks/useTheme'
import { disconnectGoogleHealth, googleHealthStatus, startGoogleHealthConnect } from '../api/googleHealthApi'

interface TopbarProps {
  onOpenEmailAlerts: () => void
}

export function Topbar({ onOpenEmailAlerts }: TopbarProps) {
  const { user, status, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()

  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)

  // GET /auth/google/status is the only source of truth for whether the
  // connect button should show as connected - fetched once a real session
  // exists (there's nothing to ask about before that).
  useEffect(() => {
    if (status !== 'authenticated') return
    googleHealthStatus()
      .then((s) => setConnected(s.connected))
      .catch((err) => console.warn("Couldn't check Google Health connection status:", err))
  }, [status])

  async function handleConnectClick() {
    if (connected) {
      if (!window.confirm('Disconnect your Google Health account?')) return
      setConnecting(true)
      try {
        const ok = await disconnectGoogleHealth()
        if (ok) window.location.reload()
        else console.warn('Disconnect failed')
      } finally {
        setConnecting(false)
      }
      return
    }

    setConnecting(true)
    try {
      const { auth_url } = await startGoogleHealthConnect()
      window.location.href = auth_url
    } catch (err) {
      console.warn("Couldn't start the Google Health connection:", err)
    } finally {
      setConnecting(false)
    }
  }

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark">🌍</span>
        <span className="brand-name">WorldWalker</span>
      </div>

      <div className="topbar-actions">
        <button
          type="button"
          className="theme-toggle"
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
          aria-pressed={theme === 'light'}
          onClick={toggleTheme}
        >
          <span className="theme-toggle-track">
            <svg className="theme-toggle-icon theme-toggle-sun" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M12 2.5v2.4M12 19.1v2.4M4.2 4.2l1.7 1.7M18.1 18.1l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.2 19.8l1.7-1.7M18.1 5.9l1.7-1.7"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
            <svg className="theme-toggle-icon theme-toggle-moon" viewBox="0 0 24 24" fill="none">
              <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            </svg>
            <span className="theme-toggle-knob" />
          </span>
        </button>

        <button
          type="button"
          className={`btn btn-connect${connected ? ' is-connected' : ''}${connecting ? ' is-loading' : ''}`}
          title={connected ? 'Disconnect Google Health' : 'Connect Google Health'}
          onClick={handleConnectClick}
        >
          <svg className="icon" viewBox="0 0 24 24" fill="none">
            <path d="M12 2 4 5.5v6c0 5.05 3.4 9.77 8 11 4.6-1.23 8-5.95 8-11v-6L12 2Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{connected ? 'Connected' : 'Connect'}</span>
        </button>

        {user && (
          <div className="user-menu">
            <span className="user-email">{user.email}</span>
            <button type="button" className="icon-btn" aria-label="Email checkpoint alerts" title="Email checkpoint alerts" aria-haspopup="dialog" onClick={onOpenEmailAlerts}>
              <svg className="icon" viewBox="0 0 24 24" fill="none">
                <path d="M4 6h16v12H4z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
                <path d="m4 7 8 6 8-6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <button type="button" className="icon-btn" aria-label="Log out" title="Log out" onClick={logout}>
              <svg className="icon" viewBox="0 0 24 24" fill="none">
                <path d="M15 17v1a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                <path d="M9 12h11m0 0-3-3m3 3-3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
