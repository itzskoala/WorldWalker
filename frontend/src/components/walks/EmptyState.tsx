// Shared "nothing logged yet" state for Recent Activity and All Trips
// (RecentActivityCard.tsx, AllTripsSection.tsx) - shown only when the
// user has zero trips at all. A filter just narrowing All Trips down to
// zero rows (e.g. "Favorites" with none picked yet) uses a plainer
// inline message instead (see AllTripsSection.tsx's own .walks-empty) -
// "go explore" isn't the right prompt when they already have trips,
// just none matching that filter.

import type { ReactNode } from 'react'
import { IconCompass } from '../icons'

interface EmptyStateProps {
  title: string
  subtitle: string
  ctaLabel: string
  onCta: () => void
  icon?: ReactNode
}

export function EmptyState({ title, subtitle, ctaLabel, onCta, icon }: EmptyStateProps) {
  return (
    <div className="walks-empty-state">
      <span className="walks-empty-state-icon">{icon ?? <IconCompass className="icon" />}</span>
      <h3 className="walks-empty-state-title">{title}</h3>
      <p className="walks-empty-state-subtitle">{subtitle}</p>
      <button type="button" className="walks-empty-state-cta" onClick={onCta}>
        {ctaLabel}
      </button>
    </div>
  )
}
