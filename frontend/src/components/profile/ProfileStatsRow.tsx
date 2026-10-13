// The four headline numbers for this profile. Steps come from the real
// /api/journey/stats call (see ProfilePage.tsx); the rest are counts of
// the mock collections until badges/favorites/postcards have a backend.
// Sits in its own bordered band (.profile-stats-band) so the row reads as
// one separated shelf between the identity block and the collections
// below, rather than floating cards.

import type { ReactNode } from 'react'
import { IconImages, IconMap, IconMedal, IconShoe } from '../icons'

interface ProfileStatsRowProps {
  lifetimeSteps: number
  badgesEarned: number
  favoriteWalksCount: number
  postcardsCount: number
}

function StatPill({ icon, value, label }: { icon: ReactNode; value: string; label: string }) {
  return (
    <div className="profile-stat-pill">
      <span className="profile-stat-pill-icon">{icon}</span>
      <span className="profile-stat-pill-text">
        <span className="profile-stat-pill-value">{value}</span>
        <span className="profile-stat-pill-label">{label}</span>
      </span>
    </div>
  )
}

export function ProfileStatsRow({ lifetimeSteps, badgesEarned, favoriteWalksCount, postcardsCount }: ProfileStatsRowProps) {
  return (
    <div className="profile-stats-band">
      <div className="profile-stats-row">
        <StatPill icon={<IconShoe className="icon" />} value={lifetimeSteps.toLocaleString()} label="Lifetime Steps" />
        <StatPill icon={<IconMedal className="icon" />} value={String(badgesEarned)} label="Badges Earned" />
        <StatPill icon={<IconMap className="icon" />} value={String(favoriteWalksCount)} label="Favorite Walks" />
        <StatPill icon={<IconImages className="icon" />} value={String(postcardsCount)} label="Postcards" />
      </div>
    </div>
  )
}
