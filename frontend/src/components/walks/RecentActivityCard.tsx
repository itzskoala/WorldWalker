// "Recent Activity" card - the narrower right-hand column next to
// AdventuresMap.tsx (HomePage.tsx). Always the latest few trips,
// regardless of the All Trips filter bar below it.

import type { TripSummary } from '../../types/trip'
import { EmptyState } from './EmptyState'
import { TripRow } from './TripRow'

interface RecentActivityCardProps {
  trips: TripSummary[]
  favorites: Set<string>
  onToggleFavorite: (tripId: string) => void
  onOpen: (tripId: string) => void
  onDelete: (tripId: string) => void
  onExplore: () => void
}

export function RecentActivityCard({ trips, favorites, onToggleFavorite, onOpen, onDelete, onExplore }: RecentActivityCardProps) {
  if (trips.length === 0) {
    return <EmptyState title="No activity yet" subtitle="Your latest walks will show up here once you start one." ctaLabel="Explore Routes" onCta={onExplore} />
  }

  const recent = [...trips].sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime()).slice(0, 5)

  return (
    <section className="walks-panel walks-recent">
      <h2 className="walks-panel-title">Recent Activity</h2>
      <ul className="walks-row-list">
        {recent.map((trip) => (
          <TripRow
            key={trip.trip_id}
            trip={trip}
            isFavorite={favorites.has(trip.trip_id)}
            onToggleFavorite={() => onToggleFavorite(trip.trip_id)}
            onOpen={() => onOpen(trip.trip_id)}
            onDelete={() => onDelete(trip.trip_id)}
          />
        ))}
      </ul>
    </section>
  )
}
