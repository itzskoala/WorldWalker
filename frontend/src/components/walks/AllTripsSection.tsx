// Full-width "All Trips" list at the bottom of My Walks (HomePage.tsx) -
// every trip matching the filter bar above it, newest first.

import type { TripSummary } from '../../types/trip'
import { EmptyState } from './EmptyState'
import { TripOverviewCard } from './TripOverviewCard'

interface AllTripsSectionProps {
  trips: TripSummary[]
  // Unfiltered trip count - distinguishes "this user has zero trips,
  // period" (the rich EmptyState, with a CTA) from "this filter just
  // happens to match none" (the plain .walks-empty message below).
  totalCount: number
  favorites: Set<string>
  nameOverrides: Record<string, string>
  onToggleFavorite: (tripId: string) => void
  onRename: (tripId: string, name: string) => void
  onEditThumbnail: (tripId: string) => void
  onOpen: (tripId: string) => void
  onDelete: (tripId: string) => void
  onExplore: () => void
}

export function AllTripsSection({
  trips,
  totalCount,
  favorites,
  nameOverrides,
  onToggleFavorite,
  onRename,
  onEditThumbnail,
  onOpen,
  onDelete,
  onExplore,
}: AllTripsSectionProps) {
  if (totalCount === 0) {
    return <EmptyState title="Ready for your first adventure?" subtitle="Start a walk and it'll show up here with all your stats." ctaLabel="Explore Routes" onCta={onExplore} />
  }

  const sorted = [...trips].sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())

  return (
    <section className="walks-panel walks-all-trips">
      <h2 className="walks-panel-title">All Trips</h2>
      {sorted.length === 0 ? (
        <p className="walks-empty">No trips match this filter yet.</p>
      ) : (
        <ul className="walks-row-list">
          {sorted.map((trip) => (
            <TripOverviewCard
              key={trip.trip_id}
              trip={trip}
              displayName={nameOverrides[trip.trip_id] ?? trip.to_place}
              isFavorite={favorites.has(trip.trip_id)}
              onToggleFavorite={() => onToggleFavorite(trip.trip_id)}
              onRename={(name) => onRename(trip.trip_id, name)}
              onEditThumbnail={() => onEditThumbnail(trip.trip_id)}
              onOpen={() => onOpen(trip.trip_id)}
              onDelete={() => onDelete(trip.trip_id)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}
