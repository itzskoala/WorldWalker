// Port of web/static/js/profile.js - the logged-in user's email +
// "Member since" (already in AuthContext, no extra request) and lifetime
// steps across every trip they've ever run (GET /api/journey/stats).

import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { journeyStats } from '../api/tripApi'

function formatMemberSince(iso: string): string {
  const date = new Date(iso)
  return `Member since ${date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}`
}

interface ProfilePageProps {
  active: boolean
}

export function ProfilePage({ active }: ProfilePageProps) {
  const { user } = useAuth()
  const [lifetimeSteps, setLifetimeSteps] = useState(0)

  useEffect(() => {
    if (!active) return
    journeyStats()
      .then((data) => setLifetimeSteps(data.lifetime_steps))
      .catch((err) => console.warn("Couldn't load your lifetime stats:", err))
  }, [active])

  return (
    <section className="screen" id="screen-profile" aria-label="Profile">
      <div className="screen-inner">
        <div className="screen-header">
          <h1 className="screen-title">Profile</h1>
        </div>

        <section className="surface-card profile-card">
          <span className="profile-avatar" aria-hidden="true">
            🚶
          </span>
          <p className="profile-email">{user?.email ?? '—'}</p>
          <p className="profile-member-since">{user ? formatMemberSince(user.created_at) : 'Member since —'}</p>
        </section>

        <section className="surface-card profile-stats">
          <div className="metric">
            <span className="metric-value">{lifetimeSteps.toLocaleString()}</span>
            <span className="metric-label">Lifetime steps</span>
          </div>
        </section>
      </div>
    </section>
  )
}
