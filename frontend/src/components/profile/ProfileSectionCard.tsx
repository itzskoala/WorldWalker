// Shared chrome for the three collection cards (Badge Case, Postcards
// Library, Favorite Walks) - same icon+title+chevron header on a
// surface-card shell, so each section only has to supply its own body
// and empty state instead of re-implementing the header three times.
//
// The header chevron is a bare icon (no "View all" label), matching the
// reference design - it's a real button only when onViewAll is passed
// (Postcards Library, which has a real destination); otherwise it's
// decorative, since Badge Case and Favorite Walks have nowhere to go yet.

import type { ReactNode } from 'react'
import { IconChevronRight } from '../icons'

interface ProfileSectionCardProps {
  icon: ReactNode
  title: string
  onViewAll?: () => void
  children: ReactNode
}

export function ProfileSectionCard({ icon, title, onViewAll, children }: ProfileSectionCardProps) {
  return (
    <section className="surface-card profile-section-card">
      <div className="profile-section-header">
        <h2 className="profile-section-title">
          <span className="profile-section-icon">{icon}</span>
          {title}
        </h2>
        {onViewAll ? (
          <button type="button" className="profile-section-chevron is-link" aria-label={`View all ${title.toLowerCase()}`} onClick={onViewAll}>
            <IconChevronRight className="icon icon-sm" />
          </button>
        ) : (
          <span className="profile-section-chevron" aria-hidden="true">
            <IconChevronRight className="icon icon-sm" />
          </span>
        )}
      </div>
      {children}
    </section>
  )
}
