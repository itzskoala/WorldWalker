// Port of web/static/js/profile.js, trimmed back to its original scope -
// identity (photo + username, via ProfileHero.tsx's useAuth()) and
// the handful of settings a user actually reaches for here. Badges,
// postcards, and favorite walks (components/profile/BadgeCase.tsx etc.)
// have no backend yet - see src/mock/profileMock.ts - and belong on a
// richer profile pass, not this one, so this screen leaves them out.

import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { journeyStats } from '../api/tripApi'
import { ProfileHero } from '../components/profile/ProfileHero'
import { useTheme } from '../hooks/useTheme'
import { IconLock } from '../components/icons'

interface ProfilePageProps {
  active: boolean
}

export function ProfilePage({ active }: ProfilePageProps) {
  const [lifetimeSteps, setLifetimeSteps] = useState(0)
  const { theme, toggleTheme } = useTheme()
  const { logout } = useAuth()

  useEffect(() => {
    if (!active) return
    journeyStats()
      .then((data) => setLifetimeSteps(data.lifetime_steps))
      .catch((err) => console.warn("Couldn't load your lifetime stats:", err))
  }, [active])

  return (
    <section className="screen" id="screen-profile" aria-label="Profile">
      <div className="screen-inner screen-inner-wide">
        <ProfileHero lifetimeSteps={lifetimeSteps} />

        <section className="surface-card settings-row">
          <div className="settings-row-text">
            <h2 className="settings-row-title">Appearance</h2>
            <p className="settings-row-body">Switch between light and dark.</p>
          </div>
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
        </section>

        <section className="surface-card settings-row">
          <div className="settings-row-text">
            <h2 className="settings-row-title">Sign out</h2>
            <p className="settings-row-body">Sign out of WorldWalker on this device.</p>
          </div>
          <button type="button" className="btn btn-outline" onClick={() => logout()}>
            <IconLock className="icon icon-sm" />
            Log out
          </button>
        </section>
      </div>
    </section>
  )
}
