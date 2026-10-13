// Collectible achievements, shown as a hexagon grid of illustrated badge
// art (see BadgeArt.tsx) rather than a gamified "progress bar to next
// level" treatment - badges should read as mementos of walks taken, not
// a score. Category picks which illustration a badge gets.

import type { ComponentType } from 'react'
import { IconLock, IconTrophy } from '../icons'
import { BadgeCityWanderer, BadgeCoastalWalker, BadgeFirstSteps, BadgeTrailblazer } from './BadgeArt'
import { ProfileSectionCard } from './ProfileSectionCard'
import { EARNED_BADGES, TOTAL_BADGES_EARNED, type Badge, type BadgeCategory } from '../../mock/profileMock'

const CATEGORY_ART: Record<BadgeCategory, ComponentType<{ className?: string }>> = {
  milestone: BadgeFirstSteps,
  nature: BadgeTrailblazer,
  city: BadgeCityWanderer,
  coastal: BadgeCoastalWalker,
}

function BadgeHex({ badge }: { badge: Badge }) {
  const Art = CATEGORY_ART[badge.category]
  return (
    <div className="badge-tile">
      <Art className="badge-art" />
      <span className="badge-tile-label">{badge.name}</span>
    </div>
  )
}

function MoreBadgesTile({ count }: { count: number }) {
  return (
    <div className="badge-tile">
      <div className="badge-hex badge-hex-more">
        <IconLock className="icon badge-hex-icon" />
      </div>
      <span className="badge-tile-label">+{count} more</span>
    </div>
  )
}

export function BadgeCase() {
  const moreCount = TOTAL_BADGES_EARNED - EARNED_BADGES.length

  return (
    <ProfileSectionCard icon={<IconTrophy className="icon icon-sm" />} title="Badge Case">
      {EARNED_BADGES.length === 0 ? (
        <p className="profile-empty">No badges yet — finish your first walk to start your collection.</p>
      ) : (
        <div className="badge-grid">
          {EARNED_BADGES.map((badge) => (
            <BadgeHex key={badge.id} badge={badge} />
          ))}
          {moreCount > 0 && <MoreBadgesTile count={moreCount} />}
        </div>
      )}
    </ProfileSectionCard>
  )
}
